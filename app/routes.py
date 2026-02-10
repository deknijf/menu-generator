from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from flask import (
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from .external_recipes import get_external_ai_recipes
from .db import (
    add_shopping_item,
    clear_day_meals_between,
    clear_shopping_items,
    complete_shopping_items,
    get_auth_user,
    get_runtime_settings,
    create_custom_meal,
    delete_shopping_item,
    delete_shopping_history_entry,
    delete_custom_meals,
    get_custom_meal,
    get_day,
    get_days_between,
    get_shopping_history_counts_between,
    list_shopping_history_for_day,
    get_user_allergies,
    get_user_dislikes,
    get_user_likes,
    get_user_menu_mode,
    list_custom_meals,
    list_shopping_items,
    replace_shopping_items,
    set_shopping_items_order,
    set_shopping_item_checked,
    set_day_cook,
    set_day_meal,
    set_user_allergies,
    set_user_dislikes,
    set_user_likes,
    set_user_menu_mode,
    set_app_setting,
    set_auth_config,
    update_auth_password,
    update_custom_meal,
    update_custom_meal_image,
    update_custom_meal_rating,
    upsert_user,
    upsert_auth_user,
    verify_auth_password,
)
from .meal_engine import generate_plan, recipes_by_id, select_best_recipe


def _require_auth():
    user = session.get("user")
    if not user:
        abort(401)
    auth_user = get_auth_user(user.get("email", ""))
    if auth_user:
        user["name"] = auth_user.get("name", user.get("name"))
        user["is_admin"] = bool(auth_user.get("is_admin"))
    else:
        settings = get_runtime_settings(current_app.config.get("SETTINGS", {}))
        admin_email = settings.get("auth", {}).get("admin_email", "")
        user["is_admin"] = user.get("email") == admin_email
    session["user"] = user
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


def _pictures_dir():
    return Path(current_app.root_path).parent / "data" / "pictures"


def _runtime_settings(app):
    return get_runtime_settings(app.config.get("SETTINGS", {}))


def _timezone_from_settings(settings):
    app_settings = (settings or {}).get("app", {}) if isinstance(settings, dict) else {}
    token = str(app_settings.get("time_zone") or "UTC").strip()
    aliases = {
        "CEST": "Europe/Brussels",
        "CET": "Europe/Brussels",
        "UTC": "UTC",
    }
    zone_name = aliases.get(token.upper(), token)
    try:
        return ZoneInfo(zone_name)
    except Exception:
        return ZoneInfo("UTC")


def _normalize_email_values(values):
    return _normalize_allergies(values)


def _to_float(value, default):
    try:
        return float(value)
    except Exception:
        return float(default)


def _effective_allergies(user_email, settings):
    family_allergies = settings["family"].get("allergies", [])
    personal_allergies = get_user_allergies(user_email)
    return _normalize_allergies([*family_allergies, *personal_allergies])


def _effective_likes(user_email, settings):
    family_likes = settings["family"].get("likes", [])
    personal_likes = get_user_likes(user_email)
    return _normalize_allergies([*family_likes, *personal_likes])


def _effective_dislikes(user_email, settings):
    family_dislikes = settings["family"].get("dislikes", [])
    personal_dislikes = get_user_dislikes(user_email)
    return _normalize_allergies([*family_dislikes, *personal_dislikes])


def _settings_for_user(user_email, settings):
    likes = _effective_likes(user_email, settings)
    dislikes = _effective_dislikes(user_email, settings)
    family = dict(settings.get("family", {}))
    family["likes"] = likes
    family["dislikes"] = dislikes
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


def _format_day_long_nl(day_iso):
    d = datetime.strptime(day_iso, "%Y-%m-%d").date()
    weekdays = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
    months = [
        "januari",
        "februari",
        "maart",
        "april",
        "mei",
        "juni",
        "juli",
        "augustus",
        "september",
        "oktober",
        "november",
        "december",
    ]
    return f"{weekdays[d.weekday()]} {d.day} {months[d.month - 1]} {d.year}"


def _normalize_token(value):
    return " ".join(str(value or "").strip().lower().split())


def _normalize_ingredient_name(name):
    token = _normalize_token(name)
    aliases = {
        "look": "knoflook",
        "garlic": "knoflook",
        "clove garlic": "knoflook",
        "olive oil": "olijfolie",
        "olijf olie": "olijfolie",
        "bay leaf": "laurierblad",
        "bay leaves": "laurierblad",
        "carrot": "wortel",
        "carrots": "wortelen",
        "onion": "ui",
        "red onion": "rode ui",
        "white onion": "witte ui",
        "potato": "aardappel",
        "potatoes": "aardappelen",
        "tomato": "tomaat",
        "tomatoes": "tomaten",
        "cherry tomatoes": "cherrytomaten",
        "bell pepper": "paprika",
        "cucumber": "komkommer",
        "zucchini": "courgette",
        "spinach": "spinazie",
        "broccoli": "broccoli",
        "mushroom": "champignon",
        "mushrooms": "champignons",
        "parsley": "peterselie",
        "coriander": "koriander",
        "basil": "basilicum",
        "oregano": "oregano",
        "thyme": "tijm",
        "rosemary": "rozemarijn",
        "mint": "munt",
        "cumin": "komijn",
        "paprika": "paprikapoeder",
        "chili powder": "chilipoeder",
        "black pepper": "zwarte peper",
        "pepper": "peper",
        "salt": "zout",
        "rice": "rijst",
        "pasta": "pasta",
        "spaghetti": "spaghetti",
        "noodles": "noedels",
        "couscous": "couscous",
        "bread": "brood",
        "flour": "bloem",
        "chickpeas": "kikkererwten",
        "lentils": "linzen",
        "beans": "bonen",
        "chicken stock": "kippenbouillon",
        "vegetable stock": "groentebouillon",
        "beef stock": "runderbouillon",
        "milk": "melk",
        "cream": "room",
        "butter": "boter",
        "cheese": "kaas",
        "egg": "ei",
        "eggs": "eieren",
        "salmon": "zalm",
        "cod": "kabeljauw",
        "tuna": "tonijn",
        "prawns": "garnalen",
        "shrimp": "garnalen",
        "beef": "rundvlees",
        "ground beef": "rundergehakt",
        "minced beef": "rundergehakt",
        "turkey": "kalkoen",
        "chicken": "kipfilet",
        "chicken breast": "kipfilet",
        "kip": "kipfilet",
        "lemon": "citroen",
        "lemon juice": "citroensap",
        "lime": "limoen",
        "lime juice": "limoensap",
    }
    return aliases.get(token, token)


def _normalize_unit(quantity, unit):
    qty = float(quantity or 0)
    raw = _normalize_token(unit)

    # normalize to a compact canonical unit set
    if any(marker in raw for marker in ("kilogram", "kilograms", "kilo", "kg")):
        return qty * 1000.0, "g"
    if any(marker in raw for marker in ("gram", "grams", "g")):
        return qty, "g"
    if any(marker in raw for marker in ("liter", "litre", "liters", "litres", " l")) or raw == "l":
        return qty * 1000.0, "ml"
    if any(marker in raw for marker in ("milliliter", "millilitre", "ml")):
        return qty, "ml"
    if any(marker in raw for marker in ("clove", "cloves", "teen", "teentje", "teentjes")):
        return qty, "teentje"
    if any(marker in raw for marker in ("stuk", "stuks", "piece", "pieces", "pc", "pcs")):
        return qty, "stuk"
    if any(marker in raw for marker in ("tbsp", "tbs", "tblsp", "tablespoon", "tablespoons", "el", "eetlepel", "eetlepels")):
        return qty, "eetlepel"
    if any(marker in raw for marker in ("tsp", "tl", "theelepel", "theelepels")):
        return qty, "theelepel"
    if any(marker in raw for marker in ("splash", "scheut")):
        return qty, "scheut"
    if any(marker in raw for marker in ("handful", "handvol")):
        return qty, "handvol"
    if any(marker in raw for marker in ("pinch", "snufje")):
        return qty, "snufje"
    return qty, raw


def _build_shopping_items(user_email, dates, person_count, base_servings):
    scale = person_count / base_servings
    recipe_map = _recipe_map_for_user(user_email)
    ingredients = {}

    for day in dates:
        row = get_day(day)
        if not row or not row.get("meal_id"):
            continue

        recipe = recipe_map.get(row["meal_id"])
        if not recipe:
            continue

        for ing in recipe.get("ingredients", []):
            name = _normalize_ingredient_name(ing.get("name", ""))
            quantity = float(ing.get("quantity", 0)) * scale
            quantity, unit = _normalize_unit(quantity, ing.get("unit", ""))
            key = (name, unit)
            ingredients[key] = ingredients.get(key, 0) + quantity

    output = [
        {"name": key[0], "quantity": qty, "unit": key[1], "checked": False, "sort_order": idx}
        for idx, (key, qty) in enumerate(sorted(ingredients.items(), key=lambda item: item[0][0]))
    ]
    return output


def _decorate_shopping_items(items):
    out = []
    for item in items or []:
        out.append(
            {
                **item,
                "show_quantity": True,
            }
        )
    return sorted(out, key=lambda x: (bool(x.get("checked", False)), int(x.get("sort_order", 0)), str(x.get("name", "")).lower()))


def _normalize_stored_shopping_items(items):
    merged = {}
    order = {}
    checked_state = {}
    for idx, item in enumerate(items or []):
        name = _normalize_ingredient_name(item.get("name", ""))
        quantity, unit = _normalize_unit(item.get("quantity", 0), item.get("unit", ""))
        key = (name, unit)
        merged[key] = merged.get(key, 0) + float(quantity or 0)
        if key not in order:
            order[key] = idx
            checked_state[key] = bool(item.get("checked", False))
        else:
            checked_state[key] = checked_state[key] and bool(item.get("checked", False))

    normalized = []
    for key in sorted(order.keys(), key=lambda k: order[k]):
        normalized.append(
            {
                "name": key[0],
                "quantity": merged[key],
                "unit": key[1],
                "checked": checked_state[key],
                "sort_order": order[key],
            }
        )
    return normalized


def _has_generated_plan_between(start, end):
    rows = get_days_between(start, end)
    return any(row.get("meal_id") for row in rows)


def _week_bounds(day_iso):
    day_date = datetime.strptime(day_iso, "%Y-%m-%d").date()
    weekday = day_date.weekday()  # maandag=0
    monday = day_date - timedelta(days=weekday)
    sunday = monday + timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()


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
    rating = _parse_int(payload.get("rating"), default=3, min_value=1, max_value=5)

    nutrition_payload = payload.get("nutrition") or {}
    normalized = {
        "name": name,
        "description": payload.get("description", ""),
        "image_url": payload.get("image_url", ""),
        "rating": rating,
        "tags": norm_list(payload.get("tags", [])),
        "allergens": norm_list(payload.get("allergens", [])),
        "ingredients": normalized_ingredients,
        "preparation": normalized_preparation,
        "rotation_limit": rotation_limit,
        "protein": float(payload.get("protein") if payload.get("protein") is not None else nutrition_payload.get("protein") or 0),
        "carbs": float(payload.get("carbs") if payload.get("carbs") is not None else nutrition_payload.get("carbs") or 0),
        "calories": float(payload.get("calories") if payload.get("calories") is not None else nutrition_payload.get("calories") or 0),
    }
    return normalized, None


def _custom_meal_bulk_item(item):
    nutrition = item.get("nutrition") or {}
    return {
        "name": item.get("name", ""),
        "description": item.get("description", ""),
        "image_url": item.get("image_url", ""),
        "rating": int(item.get("rating") or 3),
        "tags": item.get("tags", []),
        "allergens": item.get("allergens", []),
        "ingredients": item.get("ingredients", []),
        "preparation": item.get("preparation", []),
        "protein": float(nutrition.get("protein") or 0),
        "carbs": float(nutrition.get("carbs") or 0),
        "calories": float(nutrition.get("calories") or 0),
        "rotation_limit": item.get("rotation_limit", "1_per_week"),
    }


def _normalize_custom_meal_id_token(meal_id):
    token = str(meal_id).strip()
    if token.startswith("custom_"):
        token = token[len("custom_") :]
    if not token.isdigit():
        return None
    return token


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
                "rating": int(item.get("rating") or 3),
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
    @app.get("/pictures/<path:filename>")
    def pictures_file(filename):
        pictures_dir = _pictures_dir()
        pictures_dir.mkdir(parents=True, exist_ok=True)
        return send_from_directory(pictures_dir, filename)

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

    @app.get("/shopping-history/<day_iso>")
    def shopping_history_detail(day_iso):
        user = _require_auth()
        try:
            datetime.strptime(day_iso, "%Y-%m-%d")
        except ValueError:
            abort(404)

        entries = list_shopping_history_for_day(user["email"], day_iso)
        return render_template(
            "shopping_history_detail.html",
            user=user,
            day_iso=day_iso,
            day_label=_format_day_long_nl(day_iso),
            entries=entries,
        )

    @app.delete("/api/shopping-history/<int:entry_id>")
    def api_delete_shopping_history_entry(entry_id):
        user = _require_auth()
        ok = delete_shopping_history_entry(user["email"], entry_id)
        if not ok:
            return jsonify({"error": "lijst niet gevonden"}), 404
        return jsonify({"ok": True})

    @app.get("/")
    def index():
        if not session.get("user"):
            return redirect(url_for("login"))
        return render_template("index.html", settings=_runtime_settings(app))

    @app.get("/login")
    def login():
        settings = _runtime_settings(app)
        return render_template(
            "login.html",
            dev_login=settings["auth"].get("allow_dev_login", False),
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
        existing = get_auth_user(email)
        if not existing:
            return redirect(url_for("login", error="Onbekend account"))
        user_cfg = verify_auth_password(email, password)
        if not user_cfg:
            return redirect(url_for("login", error="Verkeerd wachtwoord"))
        user = {"email": email, "name": user_cfg.get("name", email), "is_admin": bool(user_cfg.get("is_admin"))}
        session["user"] = user
        upsert_user(email, user["name"], user["is_admin"])
        return redirect(url_for("index"))

    @app.get("/auth/dev")
    def auth_dev():
        settings = _runtime_settings(app)
        if not settings["auth"].get("allow_dev_login", False):
            return "Dev login disabled", 403

        email = request.args.get("email", "").strip().lower()
        if not email:
            return "Missing email", 400

        allowed = {str(item).strip().lower() for item in settings["auth"].get("allowed_emails", [])}
        admin_email = settings["auth"].get("admin_email", "").lower().strip()
        if email != admin_email and email not in allowed:
            return "Je account heeft geen toegang", 403

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
        settings = _runtime_settings(app)
        allergies = get_user_allergies(user["email"])
        likes = get_user_likes(user["email"])
        dislikes = get_user_dislikes(user["email"])
        mode, count = _effective_menu_mode(user["email"])
        return jsonify(
            {
                "allergies": allergies,
                "likes": likes,
                "dislikes": dislikes,
                "menu_mode": mode,
                "custom_meals_count": count,
                "global": {
                    "nutrition": settings["nutrition"],
                    "family": settings["family"],
                    "auth": {
                        "admin_email": settings["auth"].get("admin_email", ""),
                        "allowed_emails": settings["auth"].get("allowed_emails", []),
                    },
                },
            }
        )

    @app.put("/api/profile")
    def api_profile_put():
        user = _require_auth()
        settings = _runtime_settings(app)
        payload = request.get_json(force=True, silent=True) or {}
        allergies = payload.get("allergies", [])
        likes = payload.get("likes", [])
        dislikes = payload.get("dislikes", [])
        menu_mode = _normalize_menu_mode(payload.get("menu_mode", "ai_only"))

        if isinstance(allergies, str):
            allergies = [part.strip() for part in allergies.split(",")]
        if isinstance(likes, str):
            likes = [part.strip() for part in likes.split(",")]
        if isinstance(dislikes, str):
            dislikes = [part.strip() for part in dislikes.split(",")]

        allergies = _normalize_allergies(allergies)
        likes = _normalize_allergies(likes)
        dislikes = _normalize_allergies(dislikes)
        custom_count = len(list_custom_meals(user["email"]))
        if menu_mode == "ai_and_custom" and custom_count < 1:
            return jsonify({"error": "Voor deze optie heb je minstens 1 eigen maaltijd nodig."}), 400
        if menu_mode == "custom_only" and custom_count < 8:
            return jsonify({"error": "Voor deze optie heb je minstens 8 eigen maaltijden nodig."}), 400

        set_user_allergies(user["email"], allergies)
        set_user_likes(user["email"], likes)
        set_user_dislikes(user["email"], dislikes)
        set_user_menu_mode(user["email"], menu_mode)

        if user.get("is_admin"):
            global_payload = payload.get("global", {}) or {}

            nutrition = dict(settings.get("nutrition", {}))
            nutrition.update(global_payload.get("nutrition", {}) or {})
            nutrition = {
                "high_protein_weight": _to_float(nutrition.get("high_protein_weight"), 1.3),
                "low_carb_weight": _to_float(nutrition.get("low_carb_weight"), 1.1),
                "weekly_min_fish": int(_to_float(nutrition.get("weekly_min_fish"), 0)),
                "west_europe_preference": _to_float(nutrition.get("west_europe_preference"), 2.2),
                "asian_penalty": _to_float(nutrition.get("asian_penalty"), 2.8),
            }

            family_payload = global_payload.get("family", {}) or {}
            family = {
                "allergies": _normalize_allergies(family_payload.get("allergies", settings["family"].get("allergies", []))),
                "likes": _normalize_allergies(family_payload.get("likes", settings["family"].get("likes", []))),
                "dislikes": _normalize_allergies(family_payload.get("dislikes", settings["family"].get("dislikes", []))),
            }

            auth_payload = global_payload.get("auth", {}) or {}
            admin_email = str(auth_payload.get("admin_email", settings["auth"].get("admin_email", ""))).strip().lower()
            if not admin_email:
                return jsonify({"error": "Admin e-mail is verplicht."}), 400
            allowed_emails = auth_payload.get("allowed_emails", settings["auth"].get("allowed_emails", []))
            if isinstance(allowed_emails, str):
                allowed_emails = [part.strip() for part in allowed_emails.split(",")]
            allowed_emails = _normalize_email_values(allowed_emails)

            current_admin_email = settings["auth"].get("admin_email", "")
            admin_name = str(auth_payload.get("admin_name") or "").strip() or admin_email
            admin_password = str(auth_payload.get("admin_password") or "")
            current_admin = get_auth_user(current_admin_email)

            if admin_email and admin_email != current_admin_email and admin_password:
                upsert_auth_user(
                    email=admin_email,
                    name=admin_name,
                    password=admin_password,
                    is_admin=True,
                    password_is_hash=False,
                )
            elif admin_email and admin_email == current_admin_email and admin_password:
                update_auth_password(admin_email, admin_password)
            elif admin_email and admin_email != current_admin_email and current_admin:
                upsert_auth_user(
                    email=admin_email,
                    name=admin_name,
                    password=current_admin.get("password_hash", ""),
                    is_admin=True,
                    password_is_hash=True,
                )
            else:
                existing_admin = get_auth_user(admin_email)
                if existing_admin:
                    upsert_auth_user(
                        email=admin_email,
                        name=admin_name,
                        password=existing_admin.get("password_hash", ""),
                        is_admin=True,
                        password_is_hash=True,
                    )

            set_auth_config(admin_email, allowed_emails)
            set_app_setting("nutrition", nutrition)
            set_app_setting("family", family)

            # Keep active session aligned with changed admin e-mail.
            if user["email"] == current_admin_email and admin_email and admin_email != current_admin_email:
                user["email"] = admin_email
                user["is_admin"] = True
                user["name"] = admin_name or user["name"]
                session["user"] = user
                upsert_user(user["email"], user["name"], True)

            settings = _runtime_settings(app)

        return jsonify(
            {
                "ok": True,
                "allergies": allergies,
                "likes": likes,
                "dislikes": dislikes,
                "menu_mode": menu_mode,
                "custom_meals_count": custom_count,
                "global": {
                    "nutrition": settings["nutrition"],
                    "family": settings["family"],
                    "auth": {
                        "admin_email": settings["auth"].get("admin_email", ""),
                        "allowed_emails": settings["auth"].get("allowed_emails", []),
                    },
                },
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
        shopping_history_counts = get_shopping_history_counts_between(user["email"], start, end)
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
                    "meal_name": recipe_map.get(row["meal_id"], {}).get("name") if row and row["cook"] and row["meal_id"] else None,
                    "meal_image": recipe_map.get(row["meal_id"], {}).get("image_url") if row and row["cook"] and row["meal_id"] else None,
                    "shopping_done": int(shopping_history_counts.get(day, 0)) > 0,
                    "shopping_count": int(shopping_history_counts.get(day, 0)),
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
        user_settings = _settings_for_user(user["email"], _runtime_settings(app))
        effective_allergies = _effective_allergies(user["email"], user_settings)
        recipe_map = _recipe_map_for_user(user["email"])
        prev_day = get_day(_shift_iso(day, -1)) or {}
        next_day = get_day(_shift_iso(day, 1)) or {}
        prev_recipe = recipe_map.get(prev_day.get("meal_id")) if prev_day.get("meal_id") else None
        next_recipe = recipe_map.get(next_day.get("meal_id")) if next_day.get("meal_id") else None
        week_start, week_end = _week_bounds(day)
        week_rows = get_days_between(week_start, week_end)
        recent_ids = [row.get("meal_id") for row in week_rows if row.get("meal_id") and row.get("day_date") != day]

        recipe = select_best_recipe(
            user_settings,
            options,
            day_iso=day,
            prev_recipe=prev_recipe,
            next_recipe=next_recipe,
            allergies_override=effective_allergies,
            excluded_ids=[current_meal_id] if current_meal_id else [],
            recent_ids=recent_ids,
            custom_recipes=_extra_recipes_for_mode(user["email"]),
            include_base_recipes=_include_base_recipes_for_mode(user["email"]),
        )
        if not recipe:
            return jsonify({"error": "Geen alternatief gerecht beschikbaar"}), 400

        set_day_meal(day, recipe["id"])
        clear_shopping_items(user["email"])
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

    @app.get("/api/custom-meals/export")
    def api_custom_meals_export():
        user = _require_auth()
        items = [_custom_meal_bulk_item(item) for item in list_custom_meals(user["email"])]
        return jsonify({"items": items})

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

        meal_token = _normalize_custom_meal_id_token(meal_id)
        if meal_token is None:
            return jsonify({"error": "invalid meal id"}), 400

        normalized, error = _normalize_custom_meal_payload(payload)
        if error:
            return jsonify({"error": error}), 400

        ok = update_custom_meal(user["email"], meal_token, normalized)
        if not ok:
            return jsonify({"error": "meal not found"}), 404
        return jsonify({"ok": True})

    @app.put("/api/custom-meals/<meal_id>/rating")
    def api_custom_meals_set_rating(meal_id):
        user = _require_auth()
        meal_token = _normalize_custom_meal_id_token(meal_id)
        if meal_token is None:
            return jsonify({"error": "invalid meal id"}), 400
        payload = request.get_json(force=True, silent=True) or {}
        rating = _parse_int(payload.get("rating"), default=3, min_value=1, max_value=5)
        ok = update_custom_meal_rating(user["email"], meal_token, rating)
        if not ok:
            return jsonify({"error": "meal not found"}), 404
        return jsonify({"ok": True, "rating": rating})

    @app.post("/api/custom-meals/<meal_id>/photo")
    def api_custom_meals_upload_photo(meal_id):
        user = _require_auth()
        meal_token = _normalize_custom_meal_id_token(meal_id)
        if meal_token is None:
            return jsonify({"error": "invalid meal id"}), 400

        meal = get_custom_meal(user["email"], meal_token)
        if not meal:
            return jsonify({"error": "meal not found"}), 404

        photo = request.files.get("photo")
        if not photo or not photo.filename:
            return jsonify({"error": "Kies eerst een fotobestand."}), 400
        if not str(photo.mimetype or "").startswith("image/"):
            return jsonify({"error": "Alleen afbeeldingsbestanden zijn toegestaan."}), 400

        original_name = secure_filename(photo.filename)
        ext = Path(original_name).suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            ext = ".jpg"

        target_dir = _pictures_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"custom_{meal_token}_{uuid4().hex[:12]}{ext}"
        target_path = target_dir / filename
        photo.save(target_path)

        image_url = f"/pictures/{filename}"
        update_custom_meal_image(user["email"], meal_token, image_url)
        return jsonify({"ok": True, "image_url": image_url})

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
        force = _parse_bool(payload.get("force", False))
        if not force and _has_generated_plan_between(start, end):
            return jsonify({"error": "Er bestaat al een weekmenu voor deze periode. Opnieuw genereren?", "requires_confirmation": True}), 409

        person_count = _parse_int(options.get("person_count"), default=2, min_value=1, max_value=8)
        user_settings = _settings_for_user(user["email"], _runtime_settings(app))
        effective_allergies = _effective_allergies(user["email"], user_settings)

        days = get_days_between(start, end)
        cook_days = [d["day_date"] for d in days if d["cook"]]

        known = set(d["day_date"] for d in days)
        for d in _date_range(start, end):
            if d not in known:
                cook_days.append(d)

        cook_days = sorted(set(cook_days))

        # Prevent stale meals from previous generations in the same range
        # from leaking into refreshed shopping lists.
        clear_day_meals_between(start, end)

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

        clear_shopping_items(user["email"])
        return jsonify({"plan": enriched})

    @app.get("/api/shopping-list")
    def api_shopping_list_get():
        user = _require_auth()
        current = list_shopping_items(user["email"])
        normalized = _normalize_stored_shopping_items(current)
        replace_shopping_items(user["email"], normalized)
        return jsonify({"items": _decorate_shopping_items(list_shopping_items(user["email"]))})

    @app.delete("/api/shopping-list")
    def api_shopping_list_clear():
        user = _require_auth()
        clear_shopping_items(user["email"])
        return jsonify({"ok": True, "items": []})

    @app.post("/api/shopping-list/complete")
    def api_shopping_list_complete():
        user = _require_auth()
        settings = _runtime_settings(app)
        now_local = datetime.now(_timezone_from_settings(settings))
        ok, reason = complete_shopping_items(
            user["email"],
            now_local.date().isoformat(),
            now_local.strftime("%H:%M"),
        )
        if not ok:
            if reason == "empty":
                return jsonify({"error": "Geen items om af te ronden."}), 400
            if reason == "none_checked":
                return jsonify({"error": "Vink eerst minstens één item af."}), 400
            return jsonify({"error": "Kon boodschappen niet opslaan."}), 400
        normalized = _normalize_stored_shopping_items(list_shopping_items(user["email"]))
        replace_shopping_items(user["email"], normalized)
        return jsonify({"ok": True, "items": _decorate_shopping_items(list_shopping_items(user["email"]))})

    @app.post("/api/shopping-list")
    def api_shopping_list():
        user = _require_auth()
        payload = request.get_json(force=True, silent=True) or {}
        dates = payload.get("dates", [])
        person_count = _parse_int(payload.get("person_count"), default=2, min_value=1, max_value=8)
        base_servings = _parse_int(
            _runtime_settings(app).get("app", {}).get("base_servings", 2),
            default=2,
            min_value=1,
            max_value=8,
        )

        if not dates:
            start = payload.get("start")
            end = payload.get("end")
            if not start or not end:
                return jsonify({"error": "dates or start/end are required"}), 400
            dates = list(_date_range(start, end))

        output = _build_shopping_items(user["email"], dates, person_count, base_servings)
        replace_shopping_items(user["email"], output)
        return jsonify({"items": _decorate_shopping_items(list_shopping_items(user["email"])), "person_count": person_count})

    @app.post("/api/shopping-list/items")
    def api_shopping_list_add_item():
        user = _require_auth()
        payload = request.get_json(force=True, silent=True) or {}
        name = (payload.get("name") or "").strip()
        if not name:
            return jsonify({"error": "name is required"}), 400
        quantity, unit = _normalize_unit(payload.get("quantity", 1), payload.get("unit", "stuk"))
        normalized_name = _normalize_ingredient_name(name)
        add_shopping_item(user["email"], normalized_name, quantity, unit)
        normalized = _normalize_stored_shopping_items(list_shopping_items(user["email"]))
        replace_shopping_items(user["email"], normalized)
        return jsonify({"ok": True, "items": _decorate_shopping_items(list_shopping_items(user["email"]))})

    @app.put("/api/shopping-list/reorder")
    def api_shopping_list_reorder():
        user = _require_auth()
        payload = request.get_json(force=True, silent=True) or {}
        item_ids = payload.get("item_ids", [])
        if not isinstance(item_ids, list) or not item_ids:
            return jsonify({"error": "item_ids must be a non-empty list"}), 400
        ok = set_shopping_items_order(user["email"], item_ids)
        if not ok:
            return jsonify({"error": "reorder failed"}), 400
        normalized = _normalize_stored_shopping_items(list_shopping_items(user["email"]))
        replace_shopping_items(user["email"], normalized)
        return jsonify({"ok": True, "items": _decorate_shopping_items(list_shopping_items(user["email"]))})

    @app.put("/api/shopping-list/<int:item_id>")
    def api_shopping_list_update_item(item_id):
        user = _require_auth()
        payload = request.get_json(force=True, silent=True) or {}
        checked = _parse_bool(payload.get("checked", False))
        ok = set_shopping_item_checked(user["email"], item_id, checked)
        if not ok:
            return jsonify({"error": "item not found"}), 404
        normalized = _normalize_stored_shopping_items(list_shopping_items(user["email"]))
        replace_shopping_items(user["email"], normalized)
        return jsonify({"ok": True, "items": _decorate_shopping_items(list_shopping_items(user["email"]))})

    @app.delete("/api/shopping-list/<int:item_id>")
    def api_shopping_list_delete_item(item_id):
        user = _require_auth()
        ok = delete_shopping_item(user["email"], item_id)
        if not ok:
            return jsonify({"error": "item not found"}), 404
        normalized = _normalize_stored_shopping_items(list_shopping_items(user["email"]))
        replace_shopping_items(user["email"], normalized)
        return jsonify({"ok": True, "items": _decorate_shopping_items(list_shopping_items(user["email"]))})

    @app.get("/api/settings")
    def api_settings():
        user = _require_auth()
        settings = _runtime_settings(app)
        user_allergies = get_user_allergies(user["email"])
        user_likes = get_user_likes(user["email"])
        user_dislikes = get_user_dislikes(user["email"])
        mode, count = _effective_menu_mode(user["email"])
        public = {
            "nutrition": settings["nutrition"],
            "family": {
                "allergies": settings["family"].get("allergies", []),
                "likes": settings["family"].get("likes", []),
                "dislikes": settings["family"].get("dislikes", []),
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
                "dislikes": user_dislikes,
                "menu_mode": mode,
                "custom_meals_count": count,
            },
            "is_admin": user.get("is_admin", False),
        }
        return jsonify(public)
