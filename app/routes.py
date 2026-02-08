from datetime import date, datetime, timedelta

from flask import (
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .config_loader import find_local_user, is_allowed_email, verify_local_password
from .external_recipes import get_external_ai_recipes
from .db import (
    create_custom_meal,
    delete_custom_meals,
    get_day,
    get_days_between,
    get_user_allergies,
    get_user_likes,
    get_user_menu_mode,
    list_custom_meals,
    set_day_cook,
    set_day_meal,
    set_user_allergies,
    set_user_likes,
    set_user_menu_mode,
    update_custom_meal,
    upsert_user,
)
from .meal_engine import generate_plan, recipes_by_id, select_best_recipe


def _require_auth():
    user = session.get("user")
    if not user:
        abort(401)
    return user


def _parse_bool(value):
    return str(value).lower() in {"1", "true", "yes", "on"}


def _parse_int(value, default, min_value=1, max_value=12):
    try:
        n = int(value)
    except Exception:
        n = default
    return max(min_value, min(max_value, n))


def _normalize_allergies(values):
    out = []
    for value in values or []:
        token = str(value).strip().lower()
        if token and token not in out:
            out.append(token)
    return out


def _effective_allergies(user_email, settings):
    family_allergies = settings["family"].get("allergies", [])
    personal_allergies = get_user_allergies(user_email)
    return _normalize_allergies([*family_allergies, *personal_allergies])


def _effective_likes(user_email, settings):
    family_likes = settings["family"].get("likes", [])
    personal_likes = get_user_likes(user_email)
    return _normalize_allergies([*family_likes, *personal_likes])


def _settings_for_user(user_email, settings):
    likes = _effective_likes(user_email, settings)
    family = dict(settings.get("family", {}))
    family["likes"] = likes
    merged = dict(settings)
    merged["family"] = family
    return merged


def _normalize_menu_mode(value):
    token = str(value or "").strip().lower()
    allowed = {"ai_only", "ai_and_custom", "custom_only"}
    return token if token in allowed else "ai_only"


def _effective_menu_mode(user_email):
    requested = _normalize_menu_mode(get_user_menu_mode(user_email))
    count = len(list_custom_meals(user_email))
    if requested == "custom_only" and count < 8:
        return ("ai_and_custom" if count >= 1 else "ai_only"), count
    if requested == "ai_and_custom" and count < 1:
        return "ai_only", count
    return requested, count


def _custom_recipes_for_mode(user_email):
    mode, _ = _effective_menu_mode(user_email)
    if mode == "ai_only":
        return []
    return _custom_recipes_for_user(user_email)


def _external_ai_recipes_for_mode(user_email):
    mode, _ = _effective_menu_mode(user_email)
    if mode == "custom_only":
        return []
    return get_external_ai_recipes(limit=16)


def _extra_recipes_for_mode(user_email):
    mode, _ = _effective_menu_mode(user_email)
    custom = [] if mode == "ai_only" else _custom_recipes_for_user(user_email)
    external = [] if mode == "custom_only" else _external_ai_recipes_for_mode(user_email)
    return custom + external


def _include_base_recipes_for_mode(user_email):
    mode, _ = _effective_menu_mode(user_email)
    return mode != "custom_only"


def _date_range(start, end):
    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()
    if end_date < start_date:
        start_date, end_date = end_date, start_date
    current = start_date
    while current <= end_date:
        yield current.isoformat()
        current += timedelta(days=1)


def _shift_iso(day_iso, delta_days):
    return (datetime.strptime(day_iso, "%Y-%m-%d").date() + timedelta(days=delta_days)).isoformat()


def _meal_explanation(recipe, options, person_count):
    nutrition = recipe.get("nutrition", {})
    protein = nutrition.get("protein", 0)
    carbs = nutrition.get("carbs", 0)

    notes = []
    notes.append(f"{protein}g proteine")
    notes.append(f"{carbs}g koolhydraten")

    if options.get("low_carb") and carbs <= 22:
        notes.append("past binnen low-carb focus")
    if options.get("high_protein") and protein >= 35:
        notes.append("sterke eiwitbron")
    if "fish" in recipe.get("tags", []):
        notes.append("vismoment in je weekmenu")

    return f"Voor {person_count} personen: " + ", ".join(notes) + "."


def _preparation_steps(recipe):
    explicit = recipe.get("preparation")
    if isinstance(explicit, list):
        cleaned = [str(step).strip() for step in explicit if str(step).strip()]
        if cleaned:
            return cleaned

    name = (recipe.get("name") or "dit gerecht").lower()
    tags = set(recipe.get("tags", []))
    steps = [
        "Bereid alle ingredienten voor: was, snij en meet alles af.",
    ]

    if "pasta" in tags or "spaghetti" in name:
        steps.append("Kook de pasta in gezouten water volgens de verpakking en giet af.")
        steps.append("Bak de eiwitbron met kruiden in een aparte pan en voeg saus of groenten toe.")
        steps.append("Meng alles, proef af en serveer warm.")
    elif "fish" in tags:
        steps.append("Kruid de vis licht met peper, zout en wat citroen.")
        steps.append("Bak of oven-gaar de vis en bereid intussen de groenten en/of bijgerecht.")
        steps.append("Serveer alles samen en werk af met verse kruiden of olijfolie.")
    elif "soup" in tags or "soep" in name:
        steps.append("Fruit de basisgroenten kort aan in een kookpot met wat olie.")
        steps.append("Voeg overige ingredienten en bouillon toe en laat zacht garen.")
        steps.append("Proef af met kruiden en serveer warm.")
    else:
        steps.append("Bak de eiwitbron in een pan met een beetje olie.")
        steps.append("Bereid groenten en eventuele koolhydraatbron tot alles gaar is.")
        steps.append("Breng op smaak, dresseer en serveer.")

    return steps


def _meal_image_for_detail(recipe):
    fallback = "https://images.unsplash.com/photo-1498837167922-ddd27525d352?auto=format&fit=crop&w=1200&q=80"
    explicit = (recipe.get("image_url") or "").strip()
    if explicit:
        return explicit

    haystack_parts = [(recipe.get("name") or "").lower()]
    for ing in recipe.get("ingredients", []):
        haystack_parts.append(str(ing.get("name", "")).lower())
    haystack = " ".join(haystack_parts)

    if "kabeljauw" in haystack or "cod" in haystack:
        return "https://images.unsplash.com/photo-1519708227418-c8fd9a32b7a2?auto=format&fit=crop&w=1200&q=80"
    if "zalm" in haystack or "salmon" in haystack:
        return "https://images.unsplash.com/photo-1467003909585-2f8a72700288?auto=format&fit=crop&w=1200&q=80"
    if "spaghetti" in haystack or "pasta" in haystack:
        return "https://images.unsplash.com/photo-1621996346565-e3dbc353d2e5?auto=format&fit=crop&w=1200&q=80"
    if "kip" in haystack or "chicken" in haystack:
        return "https://images.unsplash.com/photo-1546793665-c74683f339c1?auto=format&fit=crop&w=1200&q=80"
    if "rund" in haystack or "beef" in haystack:
        return "https://images.unsplash.com/photo-1473093295043-cdd812d0e601?auto=format&fit=crop&w=1200&q=80"
    if "rijst" in haystack or "rice" in haystack:
        return "https://images.unsplash.com/photo-1512058564366-18510be2db19?auto=format&fit=crop&w=1200&q=80"
    if "aardappel" in haystack or "krieltjes" in haystack:
        return "https://images.unsplash.com/photo-1604503468506-a8da13d82791?auto=format&fit=crop&w=1200&q=80"
    if "linzen" in haystack or "soep" in haystack:
        return "https://images.unsplash.com/photo-1547592180-85f173990554?auto=format&fit=crop&w=1200&q=80"
    return fallback


def _normalize_custom_meal_payload(payload):
    name = (payload.get("name") or "").strip()
    if not name:
        return None, "name is required"

    def norm_list(values):
        out = []
        for value in values or []:
            token = str(value).strip().lower()
            if token and token not in out:
                out.append(token)
        return out

    ingredients = payload.get("ingredients") or []
    normalized_ingredients = []
    for ing in ingredients:
        name_value = str(ing.get("name", "")).strip()
        if not name_value:
            continue
        normalized_ingredients.append(
            {
                "name": name_value,
                "quantity": float(ing.get("quantity") or 0),
                "unit": str(ing.get("unit", "")).strip(),
            }
        )

    preparation = payload.get("preparation") or []
    normalized_preparation = []
    for step in preparation:
        token = str(step).strip()
        if token:
            normalized_preparation.append(token)

    rotation_limit = str(payload.get("rotation_limit") or "1_per_week").strip().lower()
    allowed_rotation_limits = {"2_per_week", "1_per_week", "1_per_month"}
    if rotation_limit not in allowed_rotation_limits:
        rotation_limit = "1_per_week"

    normalized = {
        "name": name,
        "description": payload.get("description", ""),
        "image_url": payload.get("image_url", ""),
        "tags": norm_list(payload.get("tags", [])),
        "allergens": norm_list(payload.get("allergens", [])),
        "ingredients": normalized_ingredients,
        "preparation": normalized_preparation,
        "rotation_limit": rotation_limit,
        "protein": float(payload.get("protein") or 0),
        "carbs": float(payload.get("carbs") or 0),
        "calories": float(payload.get("calories") or 0),
    }
    return normalized, None


def _custom_recipes_for_user(user_email):
    custom_meals = list_custom_meals(user_email)
    out = []
    for item in custom_meals:
        out.append(
            {
                "id": f"custom_{item['id']}",
                "name": item["name"],
                "description": item.get("description", ""),
                "image_url": item.get("image_url", ""),
                "tags": item.get("tags", []),
                "allergens": item.get("allergens", []),
                "ingredients": item.get("ingredients", []),
                "preparation": item.get("preparation", []),
                "nutrition": item.get("nutrition", {}),
                "rotation_limit": item.get("rotation_limit", "1_per_week"),
            }
        )
    return out


def _recipe_map_for_user(user_email):
    combined = list(recipes_by_id().values()) + _custom_recipes_for_user(user_email) + get_external_ai_recipes(limit=24)
    return {r["id"]: r for r in combined}


def register_routes(app):
    @app.get("/meal/<meal_id>")
    def meal_detail(meal_id):
        user = _require_auth()
        recipe = _recipe_map_for_user(user["email"]).get(meal_id)
        if not recipe:
            abort(404)

        return render_template(
            "meal_detail.html",
            user=user,
            recipe=recipe,
            meal_id=meal_id,
            editable=meal_id.startswith("custom_"),
            meal_image=_meal_image_for_detail(recipe),
            date_label=request.args.get("date", ""),
            person_count=_parse_int(request.args.get("person_count"), default=2, min_value=1, max_value=8),
            steps=_preparation_steps(recipe),
        )

    @app.get("/")
    def index():
        if not session.get("user"):
            return redirect(url_for("login"))
        return render_template("index.html", settings=app.config["SETTINGS"])

    @app.get("/login")
    def login():
        return render_template(
            "login.html",
            dev_login=app.config["SETTINGS"]["auth"].get("allow_dev_login", False),
            login_error=request.args.get("error", ""),
        )

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.post("/auth/login")
    def auth_login():
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        settings = app.config["SETTINGS"]
        user_cfg = find_local_user(email, settings)
        if not user_cfg:
            return redirect(url_for("login", error="Onbekend account"))
        if not verify_local_password(user_cfg, password):
            return redirect(url_for("login", error="Verkeerd wachtwoord"))

        admin_email = settings["auth"].get("admin_email", "").lower().strip()
        is_admin = email == admin_email
        user = {"email": email, "name": user_cfg.get("name", email), "is_admin": is_admin}
        session["user"] = user
        upsert_user(email, user["name"], is_admin)
        return redirect(url_for("index"))

    @app.get("/auth/dev")
    def auth_dev():
        if not app.config["SETTINGS"]["auth"].get("allow_dev_login", False):
            return "Dev login disabled", 403

        email = request.args.get("email", "").strip().lower()
        if not email:
            return "Missing email", 400

        settings = app.config["SETTINGS"]
        if not is_allowed_email(email, settings):
            return "Je account heeft geen toegang", 403

        admin_email = settings["auth"].get("admin_email", "").lower().strip()
        is_admin = email == admin_email
        user = {"email": email, "name": email.split("@")[0], "is_admin": is_admin}
        session["user"] = user
        upsert_user(email, user["name"], is_admin)
        return redirect(url_for("index"))

    @app.get("/api/session")
    def api_session():
        user = session.get("user")
        return jsonify({"user": user})

    @app.get("/api/profile")
    def api_profile_get():
        user = _require_auth()
        allergies = get_user_allergies(user["email"])
        likes = get_user_likes(user["email"])
        mode, count = _effective_menu_mode(user["email"])
        return jsonify({"allergies": allergies, "likes": likes, "menu_mode": mode, "custom_meals_count": count})

    @app.put("/api/profile")
    def api_profile_put():
        user = _require_auth()
        payload = request.get_json(force=True, silent=True) or {}
        allergies = payload.get("allergies", [])
        likes = payload.get("likes", [])
        menu_mode = _normalize_menu_mode(payload.get("menu_mode", "ai_only"))

        if isinstance(allergies, str):
            allergies = [part.strip() for part in allergies.split(",")]
        if isinstance(likes, str):
            likes = [part.strip() for part in likes.split(",")]

        allergies = _normalize_allergies(allergies)
        likes = _normalize_allergies(likes)
        custom_count = len(list_custom_meals(user["email"]))
        if menu_mode == "ai_and_custom" and custom_count < 1:
            return jsonify({"error": "Voor deze optie heb je minstens 1 eigen maaltijd nodig."}), 400
        if menu_mode == "custom_only" and custom_count < 8:
            return jsonify({"error": "Voor deze optie heb je minstens 8 eigen maaltijden nodig."}), 400

        set_user_allergies(user["email"], allergies)
        set_user_likes(user["email"], likes)
        set_user_menu_mode(user["email"], menu_mode)
        return jsonify(
            {
                "ok": True,
                "allergies": allergies,
                "likes": likes,
                "menu_mode": menu_mode,
                "custom_meals_count": custom_count,
            }
        )

    @app.get("/api/calendar")
    def api_calendar():
        user = _require_auth()
        start = request.args.get("start")
        end = request.args.get("end")

        if not start or not end:
            today = date.today()
            start = today.replace(day=1).isoformat()
            end = (today + timedelta(days=45)).isoformat()

        rows = get_days_between(start, end)
        by_day = {row["day_date"]: row for row in rows}
        recipe_map = _recipe_map_for_user(user["email"])

        result = []
        for day in _date_range(start, end):
            row = by_day.get(day)
            result.append(
                {
                    "date": day,
                    "cook": bool(row["cook"]) if row else True,
                    "meal_id": row["meal_id"] if row else None,
                    "meal_name": recipe_map.get(row["meal_id"], {}).get("name") if row and row["meal_id"] else None,
                    "meal_image": recipe_map.get(row["meal_id"], {}).get("image_url") if row and row["meal_id"] else None,
                }
            )

        return jsonify({"days": result})

    @app.put("/api/calendar/<day>")
    def api_calendar_day(day):
        _require_auth()
        payload = request.get_json(force=True, silent=True) or {}
        cook = payload.get("cook", True)
        set_day_cook(day, _parse_bool(cook))
        return jsonify({"ok": True})

    @app.post("/api/calendar/<day>/retry")
    def api_calendar_retry(day):
        user = _require_auth()
        payload = request.get_json(force=True, silent=True) or {}
        options = payload.get("options", {})
        person_count = _parse_int(payload.get("person_count"), default=2, min_value=1, max_value=8)

        current = get_day(day) or {}
        current_meal_id = current.get("meal_id")
        user_settings = _settings_for_user(user["email"], app.config["SETTINGS"])
        effective_allergies = _effective_allergies(user["email"], user_settings)
        recipe_map = _recipe_map_for_user(user["email"])
        prev_day = get_day(_shift_iso(day, -1)) or {}
        next_day = get_day(_shift_iso(day, 1)) or {}
        prev_recipe = recipe_map.get(prev_day.get("meal_id")) if prev_day.get("meal_id") else None
        next_recipe = recipe_map.get(next_day.get("meal_id")) if next_day.get("meal_id") else None

        recipe = select_best_recipe(
            user_settings,
            options,
            day_iso=day,
            prev_recipe=prev_recipe,
            next_recipe=next_recipe,
            allergies_override=effective_allergies,
            excluded_ids=[current_meal_id] if current_meal_id else [],
            custom_recipes=_extra_recipes_for_mode(user["email"]),
            include_base_recipes=_include_base_recipes_for_mode(user["email"]),
        )
        if not recipe:
            return jsonify({"error": "Geen alternatief gerecht beschikbaar"}), 400

        set_day_meal(day, recipe["id"])
        return jsonify(
            {
                "ok": True,
                "item": {
                    "date": day,
                    "meal_id": recipe["id"],
                    "meal_name": recipe["name"],
                    "person_count": person_count,
                    "nutrition": recipe.get("nutrition", {}),
                    "image_url": recipe.get("image_url", ""),
                    "explanation": _meal_explanation(recipe, options, person_count),
                },
            }
        )

    @app.get("/api/custom-meals")
    def api_custom_meals_get():
        user = _require_auth()
        return jsonify({"items": _custom_recipes_for_user(user["email"])})

    @app.post("/api/custom-meals")
    def api_custom_meals_post():
        user = _require_auth()
        payload = request.get_json(force=True, silent=True) or {}
        normalized, error = _normalize_custom_meal_payload(payload)
        if error:
            return jsonify({"error": error}), 400

        meal_id = create_custom_meal(
            user["email"],
            normalized,
        )
        return jsonify({"ok": True, "id": meal_id})

    @app.post("/api/custom-meals/bulk")
    def api_custom_meals_bulk_post():
        user = _require_auth()
        payload = request.get_json(force=True, silent=True) or {}
        items = payload.get("items", [])
        if not isinstance(items, list) or not items:
            return jsonify({"error": "items must be a non-empty list"}), 400

        created = 0
        errors = []
        for idx, item in enumerate(items, start=1):
            normalized, error = _normalize_custom_meal_payload(item or {})
            if error:
                errors.append({"index": idx, "error": error})
                continue
            create_custom_meal(user["email"], normalized)
            created += 1

        return jsonify({"ok": True, "created": created, "errors": errors})

    @app.put("/api/custom-meals/<meal_id>")
    def api_custom_meals_put(meal_id):
        user = _require_auth()
        payload = request.get_json(force=True, silent=True) or {}

        meal_token = str(meal_id).strip()
        if meal_token.startswith("custom_"):
            meal_token = meal_token[len("custom_") :]
        if not meal_token.isdigit():
            return jsonify({"error": "invalid meal id"}), 400

        normalized, error = _normalize_custom_meal_payload(payload)
        if error:
            return jsonify({"error": error}), 400

        ok = update_custom_meal(user["email"], meal_token, normalized)
        if not ok:
            return jsonify({"error": "meal not found"}), 404
        return jsonify({"ok": True})

    @app.delete("/api/custom-meals")
    def api_custom_meals_delete():
        user = _require_auth()
        payload = request.get_json(force=True, silent=True) or {}
        raw_ids = payload.get("meal_ids", [])
        if not isinstance(raw_ids, list):
            return jsonify({"error": "meal_ids must be a list"}), 400

        normalized_ids = []
        for raw in raw_ids:
            token = str(raw).strip()
            if token.startswith("custom_"):
                token = token[len("custom_") :]
            if token.isdigit():
                normalized_ids.append(int(token))

        deleted = delete_custom_meals(user["email"], normalized_ids)
        return jsonify({"ok": True, "deleted": deleted})

    @app.post("/api/generate")
    def api_generate():
        user = _require_auth()
        payload = request.get_json(force=True, silent=True) or {}

        start = payload.get("start")
        end = payload.get("end")
        options = payload.get("options", {})

        if not start or not end:
            return jsonify({"error": "start and end are required"}), 400

        person_count = _parse_int(options.get("person_count"), default=2, min_value=1, max_value=8)
        user_settings = _settings_for_user(user["email"], app.config["SETTINGS"])
        effective_allergies = _effective_allergies(user["email"], user_settings)

        days = get_days_between(start, end)
        cook_days = [d["day_date"] for d in days if d["cook"]]

        known = set(d["day_date"] for d in days)
        for d in _date_range(start, end):
            if d not in known:
                cook_days.append(d)

        cook_days = sorted(set(cook_days))

        plan = generate_plan(
            cook_days,
            user_settings,
            options,
            allergies_override=effective_allergies,
            custom_recipes=_extra_recipes_for_mode(user["email"]),
            include_base_recipes=_include_base_recipes_for_mode(user["email"]),
        )

        recipe_map = _recipe_map_for_user(user["email"])
        enriched = []
        for item in plan:
            set_day_meal(item["date"], item["meal_id"])
            recipe = recipe_map.get(item["meal_id"], {})
            enriched.append(
                {
                    **item,
                    "person_count": person_count,
                    "nutrition": recipe.get("nutrition", {}),
                    "image_url": recipe.get("image_url", ""),
                    "explanation": _meal_explanation(recipe, options, person_count),
                }
            )

        return jsonify({"plan": enriched})

    @app.post("/api/shopping-list")
    def api_shopping_list():
        user = _require_auth()
        payload = request.get_json(force=True, silent=True) or {}
        dates = payload.get("dates", [])
        person_count = _parse_int(payload.get("person_count"), default=2, min_value=1, max_value=8)
        base_servings = _parse_int(
            app.config["SETTINGS"].get("app", {}).get("base_servings", 2),
            default=2,
            min_value=1,
            max_value=8,
        )
        scale = person_count / base_servings

        if not dates:
            start = payload.get("start")
            end = payload.get("end")
            if not start or not end:
                return jsonify({"error": "dates or start/end are required"}), 400
            dates = list(_date_range(start, end))

        recipe_map = _recipe_map_for_user(user["email"])
        ingredients = {}

        for day in dates:
            row = get_day(day)
            if not row or not row.get("meal_id"):
                continue

            recipe = recipe_map.get(row["meal_id"])
            if not recipe:
                continue

            for ing in recipe.get("ingredients", []):
                key = (ing["name"], ing.get("unit", ""))
                ingredients[key] = ingredients.get(key, 0) + (float(ing.get("quantity", 0)) * scale)

        output = [
            {"name": key[0], "quantity": qty, "unit": key[1]}
            for key, qty in sorted(ingredients.items(), key=lambda item: item[0][0])
        ]
        return jsonify({"items": output, "person_count": person_count})

    @app.get("/api/settings")
    def api_settings():
        user = _require_auth()
        settings = app.config["SETTINGS"]
        user_allergies = get_user_allergies(user["email"])
        user_likes = get_user_likes(user["email"])
        mode, count = _effective_menu_mode(user["email"])
        public = {
            "nutrition": settings["nutrition"],
            "family": {
                "allergies": settings["family"].get("allergies", []),
                "likes": settings["family"].get("likes", []),
            },
            "auth": {
                "admin_email": settings["auth"].get("admin_email"),
                "allowed_emails": settings["auth"].get("allowed_emails", []),
            },
            "app": {
                "base_servings": settings.get("app", {}).get("base_servings", 2),
            },
            "profile": {
                "allergies": user_allergies,
                "likes": user_likes,
                "menu_mode": mode,
                "custom_meals_count": count,
            },
            "is_admin": user.get("is_admin", False),
        }
        return jsonify(public)
