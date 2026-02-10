import sqlite3
from pathlib import Path
import json
from werkzeug.security import check_password_hash, generate_password_hash


DB_PATH = Path("data/app.db")
DEFAULT_NUTRITION = {
    "high_protein_weight": 1.3,
    "low_carb_weight": 1.1,
    "weekly_min_fish": 0,
    "west_europe_preference": 2.2,
    "asian_penalty": 2.8,
}
DEFAULT_FAMILY = {
    "allergies": [],
    "likes": [],
    "dislikes": [],
}


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            name TEXT,
            is_admin INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_users (
            email TEXT PRIMARY KEY,
            name TEXT,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            setting_key TEXT PRIMARY KEY,
            setting_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS day_plans (
            day_date TEXT PRIMARY KEY,
            cook INTEGER NOT NULL DEFAULT 1,
            meal_id TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_preferences (
            email TEXT PRIMARY KEY,
            allergies_json TEXT NOT NULL DEFAULT '[]',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_food_preferences (
            email TEXT PRIMARY KEY,
            likes_json TEXT NOT NULL DEFAULT '[]',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_food_dislikes (
            email TEXT PRIMARY KEY,
            dislikes_json TEXT NOT NULL DEFAULT '[]',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_menu_preferences (
            email TEXT PRIMARY KEY,
            menu_mode TEXT NOT NULL DEFAULT 'ai_only',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS custom_meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            image_url TEXT DEFAULT '',
            rating INTEGER NOT NULL DEFAULT 3,
            tags_json TEXT NOT NULL DEFAULT '[]',
            allergens_json TEXT NOT NULL DEFAULT '[]',
            ingredients_json TEXT NOT NULL DEFAULT '[]',
            preparation_json TEXT NOT NULL DEFAULT '[]',
            rotation_limit TEXT NOT NULL DEFAULT '1_per_week',
            protein REAL NOT NULL DEFAULT 0,
            carbs REAL NOT NULL DEFAULT 0,
            calories REAL NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS shopping_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            name TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            unit TEXT NOT NULL DEFAULT '',
            checked INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute("PRAGMA table_info(custom_meals)")
    columns = {row["name"] for row in cur.fetchall()}
    if "rotation_limit" not in columns:
        cur.execute("ALTER TABLE custom_meals ADD COLUMN rotation_limit TEXT NOT NULL DEFAULT '1_per_week'")
    if "preparation_json" not in columns:
        cur.execute("ALTER TABLE custom_meals ADD COLUMN preparation_json TEXT NOT NULL DEFAULT '[]'")
    if "rating" not in columns:
        cur.execute("ALTER TABLE custom_meals ADD COLUMN rating INTEGER NOT NULL DEFAULT 3")
    conn.commit()
    conn.close()


def _is_password_hash(value):
    token = str(value or "")
    return token.startswith("pbkdf2:") or token.startswith("scrypt:")


def _as_password_hash(value):
    raw = str(value or "")
    if _is_password_hash(raw):
        return raw
    return generate_password_hash(raw)


def _load_json_or_default(value, default):
    try:
        parsed = json.loads(value or "")
    except Exception:
        return default
    if isinstance(default, dict) and isinstance(parsed, dict):
        return parsed
    if isinstance(default, list) and isinstance(parsed, list):
        return parsed
    return default


def upsert_auth_user(email, name, password, is_admin, password_is_hash=False):
    email_token = str(email or "").strip().lower()
    if not email_token:
        return False
    password_token = str(password or "")
    if not password_token:
        return False
    password_hash = password_token if password_is_hash else _as_password_hash(password_token)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO auth_users (email, name, password_hash, is_admin)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            name=excluded.name,
            password_hash=excluded.password_hash,
            is_admin=excluded.is_admin,
            updated_at=CURRENT_TIMESTAMP
        """,
        (email_token, str(name or "").strip(), password_hash, int(bool(is_admin))),
    )
    conn.commit()
    conn.close()
    return True


def get_auth_user(email):
    email_token = str(email or "").strip().lower()
    if not email_token:
        return None
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT email, name, password_hash, is_admin FROM auth_users WHERE email = ?",
        (email_token,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "email": row["email"],
        "name": row["name"] or row["email"],
        "password_hash": row["password_hash"] or "",
        "is_admin": bool(row["is_admin"]),
    }


def verify_auth_password(email, password):
    user = get_auth_user(email)
    if not user:
        return None
    if not check_password_hash(user.get("password_hash", ""), str(password or "")):
        return None
    return user


def _normalize_email_list(values):
    out = []
    for value in values or []:
        token = str(value or "").strip().lower()
        if token and token not in out:
            out.append(token)
    return out


def set_app_setting(setting_key, payload):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO app_settings (setting_key, setting_json)
        VALUES (?, ?)
        ON CONFLICT(setting_key) DO UPDATE SET
            setting_json=excluded.setting_json,
            updated_at=CURRENT_TIMESTAMP
        """,
        (str(setting_key), json.dumps(payload or {})),
    )
    conn.commit()
    conn.close()


def get_app_setting(setting_key, default):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT setting_json FROM app_settings WHERE setting_key = ?", (str(setting_key),))
    row = cur.fetchone()
    conn.close()
    if not row:
        return default
    return _load_json_or_default(row["setting_json"], default)


def get_runtime_settings(base_settings):
    base_app = dict((base_settings or {}).get("app", {}))
    base_auth = dict((base_settings or {}).get("auth", {}))
    admin_email = str(base_auth.get("admin_email", "")).strip().lower()
    allowed_emails = _normalize_email_list(base_auth.get("allowed_emails", []))
    allow_dev_login = bool(base_auth.get("allow_dev_login", False))

    auth_settings = get_app_setting(
        "auth",
        {
            "admin_email": admin_email,
            "allowed_emails": allowed_emails,
        },
    )
    if not isinstance(auth_settings, dict):
        auth_settings = {}
    auth = {
        "admin_email": str(auth_settings.get("admin_email", admin_email)).strip().lower(),
        "allowed_emails": _normalize_email_list(auth_settings.get("allowed_emails", allowed_emails)),
        "allow_dev_login": allow_dev_login,
    }

    nutrition_seed = dict(DEFAULT_NUTRITION)
    nutrition_seed.update((base_settings or {}).get("nutrition", {}))
    nutrition = dict(DEFAULT_NUTRITION)
    nutrition.update(get_app_setting("nutrition", nutrition_seed))

    family_seed = dict(DEFAULT_FAMILY)
    family_seed.update((base_settings or {}).get("family", {}))
    family_raw = get_app_setting("family", family_seed)
    if not isinstance(family_raw, dict):
        family_raw = {}
    family = {
        "allergies": _normalize_email_list(family_raw.get("allergies", [])),
        "likes": _normalize_email_list(family_raw.get("likes", [])),
        "dislikes": _normalize_email_list(family_raw.get("dislikes", [])),
    }

    return {
        "app": base_app,
        "auth": auth,
        "nutrition": nutrition,
        "family": family,
    }


def bootstrap_db_settings(base_settings):
    runtime = get_runtime_settings(base_settings)
    set_auth_config(runtime["auth"]["admin_email"], runtime["auth"]["allowed_emails"])
    set_app_setting("nutrition", runtime["nutrition"])
    set_app_setting("family", runtime["family"])

    admin_email = runtime["auth"]["admin_email"]
    local_users = list((base_settings or {}).get("auth", {}).get("local_users", []))
    for item in local_users:
        email = str(item.get("email", "")).strip().lower()
        if not email:
            continue
        if get_auth_user(email):
            continue
        upsert_auth_user(
            email=email,
            name=item.get("name") or email,
            password=item.get("password") or "",
            is_admin=(email == admin_email),
            password_is_hash=_is_password_hash(item.get("password") or ""),
        )


def set_auth_config(admin_email, allowed_emails):
    admin_email_token = str(admin_email or "").strip().lower()
    allowed = _normalize_email_list(allowed_emails)
    if admin_email_token and admin_email_token not in allowed:
        allowed.append(admin_email_token)

    set_app_setting("auth", {"admin_email": admin_email_token, "allowed_emails": allowed})

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE auth_users SET is_admin = 0")
    if admin_email_token:
        cur.execute(
            """
            UPDATE auth_users
            SET is_admin = 1, updated_at = CURRENT_TIMESTAMP
            WHERE email = ?
            """,
            (admin_email_token,),
        )
    conn.commit()
    conn.close()


def update_auth_password(email, new_password):
    email_token = str(email or "").strip().lower()
    password_token = str(new_password or "")
    if not email_token or not password_token:
        return False
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE auth_users
        SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
        WHERE email = ?
        """,
        (_as_password_hash(password_token), email_token),
    )
    ok = (cur.rowcount or 0) > 0
    conn.commit()
    conn.close()
    return ok


def upsert_user(email, name, is_admin):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO users (email, name, is_admin)
        VALUES (?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            name=excluded.name,
            is_admin=excluded.is_admin
        """,
        (email, name, int(is_admin)),
    )
    conn.commit()
    conn.close()


def set_day_cook(date_str, cook):
    conn = get_conn()
    cur = conn.cursor()
    cook_int = int(bool(cook))
    cur.execute(
        """
        INSERT INTO day_plans (day_date, cook, meal_id)
        VALUES (?, ?, CASE WHEN ? = 0 THEN NULL ELSE NULL END)
        ON CONFLICT(day_date) DO UPDATE SET
            cook=excluded.cook,
            meal_id=CASE WHEN excluded.cook = 0 THEN NULL ELSE day_plans.meal_id END,
            updated_at=CURRENT_TIMESTAMP
        """,
        (date_str, cook_int, cook_int),
    )
    conn.commit()
    conn.close()


def set_day_meal(date_str, meal_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO day_plans (day_date, cook, meal_id)
        VALUES (?, 1, ?)
        ON CONFLICT(day_date) DO UPDATE SET
            meal_id=excluded.meal_id,
            cook=1,
            updated_at=CURRENT_TIMESTAMP
        """,
        (date_str, meal_id),
    )
    conn.commit()
    conn.close()


def get_days_between(start_date, end_date):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT day_date, cook, meal_id
        FROM day_plans
        WHERE day_date BETWEEN ? AND ?
        ORDER BY day_date ASC
        """,
        (start_date, end_date),
    )
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def get_day(date_str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT day_date, cook, meal_id FROM day_plans WHERE day_date = ?", (date_str,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_allergies(email):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT allergies_json FROM user_preferences WHERE email = ?", (email,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return []
    try:
        return json.loads(row["allergies_json"] or "[]")
    except Exception:
        return []


def set_user_allergies(email, allergies):
    payload = json.dumps(allergies or [])
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO user_preferences (email, allergies_json)
        VALUES (?, ?)
        ON CONFLICT(email) DO UPDATE SET
            allergies_json=excluded.allergies_json,
            updated_at=CURRENT_TIMESTAMP
        """,
        (email, payload),
    )
    conn.commit()
    conn.close()


def get_user_likes(email):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT likes_json FROM user_food_preferences WHERE email = ?", (email,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return []
    try:
        return json.loads(row["likes_json"] or "[]")
    except Exception:
        return []


def set_user_likes(email, likes):
    payload = json.dumps(likes or [])
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO user_food_preferences (email, likes_json)
        VALUES (?, ?)
        ON CONFLICT(email) DO UPDATE SET
            likes_json=excluded.likes_json,
            updated_at=CURRENT_TIMESTAMP
        """,
        (email, payload),
    )
    conn.commit()
    conn.close()


def get_user_dislikes(email):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT dislikes_json FROM user_food_dislikes WHERE email = ?", (email,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return []
    try:
        return json.loads(row["dislikes_json"] or "[]")
    except Exception:
        return []


def set_user_dislikes(email, dislikes):
    payload = json.dumps(dislikes or [])
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO user_food_dislikes (email, dislikes_json)
        VALUES (?, ?)
        ON CONFLICT(email) DO UPDATE SET
            dislikes_json=excluded.dislikes_json,
            updated_at=CURRENT_TIMESTAMP
        """,
        (email, payload),
    )
    conn.commit()
    conn.close()


def get_user_menu_mode(email):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT menu_mode FROM user_menu_preferences WHERE email = ?", (email,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return "ai_only"
    return (row["menu_mode"] or "ai_only").strip()


def set_user_menu_mode(email, menu_mode):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO user_menu_preferences (email, menu_mode)
        VALUES (?, ?)
        ON CONFLICT(email) DO UPDATE SET
            menu_mode=excluded.menu_mode,
            updated_at=CURRENT_TIMESTAMP
        """,
        (email, menu_mode),
    )
    conn.commit()
    conn.close()


def list_custom_meals(email):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            id, email, name, description, image_url, rating,
            tags_json, allergens_json, ingredients_json, preparation_json, rotation_limit,
            protein, carbs, calories
        FROM custom_meals
        WHERE email = ?
        ORDER BY id DESC
        """,
        (email,),
    )
    rows = cur.fetchall()
    conn.close()

    out = []
    for row in rows:
        try:
            tags = json.loads(row["tags_json"] or "[]")
        except Exception:
            tags = []
        try:
            allergens = json.loads(row["allergens_json"] or "[]")
        except Exception:
            allergens = []
        try:
            ingredients = json.loads(row["ingredients_json"] or "[]")
        except Exception:
            ingredients = []
        try:
            preparation = json.loads(row["preparation_json"] or "[]")
        except Exception:
            preparation = []

        out.append(
            {
                "id": row["id"],
                "email": row["email"],
                "name": row["name"],
                "description": row["description"] or "",
                "image_url": row["image_url"] or "",
                "rating": max(1, min(5, int(row["rating"] or 3))),
                "tags": tags,
                "allergens": allergens,
                "ingredients": ingredients,
                "preparation": preparation,
                "rotation_limit": row["rotation_limit"] or "1_per_week",
                "nutrition": {
                    "protein": float(row["protein"] or 0),
                    "carbs": float(row["carbs"] or 0),
                    "calories": float(row["calories"] or 0),
                },
            }
        )
    return out


def create_custom_meal(email, payload):
    name = (payload.get("name") or "").strip()
    description = (payload.get("description") or "").strip()
    image_url = (payload.get("image_url") or "").strip()
    rating = max(1, min(5, int(payload.get("rating") or 3)))
    tags = payload.get("tags") or []
    allergens = payload.get("allergens") or []
    ingredients = payload.get("ingredients") or []
    preparation = payload.get("preparation") or []
    rotation_limit = (payload.get("rotation_limit") or "1_per_week").strip()
    protein = float(payload.get("protein") or 0)
    carbs = float(payload.get("carbs") or 0)
    calories = float(payload.get("calories") or 0)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO custom_meals (
            email, name, description, image_url,
            rating,
            tags_json, allergens_json, ingredients_json, preparation_json, rotation_limit,
            protein, carbs, calories
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email,
            name,
            description,
            image_url,
            rating,
            json.dumps(tags),
            json.dumps(allergens),
            json.dumps(ingredients),
            json.dumps(preparation),
            rotation_limit,
            protein,
            carbs,
            calories,
        ),
    )
    meal_id = cur.lastrowid
    conn.commit()
    conn.close()
    return meal_id


def delete_custom_meals(email, meal_ids):
    ids = [int(x) for x in (meal_ids or []) if str(x).isdigit()]
    if not ids:
        return 0

    conn = get_conn()
    cur = conn.cursor()
    placeholders = ", ".join(["?"] * len(ids))
    cur.execute(
        f"DELETE FROM custom_meals WHERE email = ? AND id IN ({placeholders})",
        [email, *ids],
    )
    deleted = cur.rowcount or 0
    conn.commit()
    conn.close()
    return deleted


def update_custom_meal(email, meal_id, payload):
    if not str(meal_id).isdigit():
        return False

    name = (payload.get("name") or "").strip()
    if not name:
        return False

    description = (payload.get("description") or "").strip()
    image_url = (payload.get("image_url") or "").strip()
    rating = max(1, min(5, int(payload.get("rating") or 3)))
    tags = payload.get("tags") or []
    allergens = payload.get("allergens") or []
    ingredients = payload.get("ingredients") or []
    preparation = payload.get("preparation") or []
    rotation_limit = (payload.get("rotation_limit") or "1_per_week").strip()
    protein = float(payload.get("protein") or 0)
    carbs = float(payload.get("carbs") or 0)
    calories = float(payload.get("calories") or 0)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE custom_meals
        SET
            name = ?,
            description = ?,
            image_url = ?,
            rating = ?,
            tags_json = ?,
            allergens_json = ?,
            ingredients_json = ?,
            preparation_json = ?,
            rotation_limit = ?,
            protein = ?,
            carbs = ?,
            calories = ?
        WHERE email = ? AND id = ?
        """,
        (
            name,
            description,
            image_url,
            rating,
            json.dumps(tags),
            json.dumps(allergens),
            json.dumps(ingredients),
            json.dumps(preparation),
            rotation_limit,
            protein,
            carbs,
            calories,
            email,
            int(meal_id),
        ),
    )
    updated = (cur.rowcount or 0) > 0
    conn.commit()
    conn.close()
    return updated


def get_custom_meal(email, meal_id):
    if not str(meal_id).isdigit():
        return None
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            id, email, name, description, image_url, rating,
            tags_json, allergens_json, ingredients_json, preparation_json, rotation_limit,
            protein, carbs, calories
        FROM custom_meals
        WHERE email = ? AND id = ?
        """,
        (email, int(meal_id)),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    try:
        tags = json.loads(row["tags_json"] or "[]")
    except Exception:
        tags = []
    try:
        allergens = json.loads(row["allergens_json"] or "[]")
    except Exception:
        allergens = []
    try:
        ingredients = json.loads(row["ingredients_json"] or "[]")
    except Exception:
        ingredients = []
    try:
        preparation = json.loads(row["preparation_json"] or "[]")
    except Exception:
        preparation = []
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "description": row["description"] or "",
        "image_url": row["image_url"] or "",
        "rating": max(1, min(5, int(row["rating"] or 3))),
        "tags": tags,
        "allergens": allergens,
        "ingredients": ingredients,
        "preparation": preparation,
        "rotation_limit": row["rotation_limit"] or "1_per_week",
        "nutrition": {
            "protein": float(row["protein"] or 0),
            "carbs": float(row["carbs"] or 0),
            "calories": float(row["calories"] or 0),
        },
    }


def update_custom_meal_image(email, meal_id, image_url):
    if not str(meal_id).isdigit():
        return False
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE custom_meals
        SET image_url = ?
        WHERE email = ? AND id = ?
        """,
        (str(image_url or "").strip(), email, int(meal_id)),
    )
    ok = (cur.rowcount or 0) > 0
    conn.commit()
    conn.close()
    return ok


def update_custom_meal_rating(email, meal_id, rating):
    if not str(meal_id).isdigit():
        return False
    value = max(1, min(5, int(rating or 3)))
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE custom_meals
        SET rating = ?
        WHERE email = ? AND id = ?
        """,
        (value, email, int(meal_id)),
    )
    ok = (cur.rowcount or 0) > 0
    conn.commit()
    conn.close()
    return ok


def list_shopping_items(email):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, quantity, unit, checked, sort_order
        FROM shopping_items
        WHERE email = ?
        ORDER BY sort_order ASC, id ASC
        """,
        (email,),
    )
    rows = [
        {
            "id": row["id"],
            "name": row["name"],
            "quantity": float(row["quantity"] or 0),
            "unit": row["unit"] or "",
            "checked": bool(row["checked"]),
            "sort_order": int(row["sort_order"] or 0),
        }
        for row in cur.fetchall()
    ]
    conn.close()
    return rows


def replace_shopping_items(email, items):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM shopping_items WHERE email = ?", (email,))
    for index, item in enumerate(items or []):
        cur.execute(
            """
            INSERT INTO shopping_items (email, name, quantity, unit, checked, sort_order)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                email,
                str(item.get("name", "")).strip(),
                float(item.get("quantity") or 0),
                str(item.get("unit", "")).strip(),
                int(bool(item.get("checked", False))),
                int(item.get("sort_order", index)),
            ),
        )
    conn.commit()
    conn.close()


def add_shopping_item(email, name, quantity, unit):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(MAX(sort_order), -1) AS max_sort FROM shopping_items WHERE email = ?", (email,))
    max_sort = int(cur.fetchone()["max_sort"])
    cur.execute(
        """
        INSERT INTO shopping_items (email, name, quantity, unit, checked, sort_order)
        VALUES (?, ?, ?, ?, 0, ?)
        """,
        (email, str(name).strip(), float(quantity or 0), str(unit or "").strip(), max_sort + 1),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def set_shopping_item_checked(email, item_id, checked):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE shopping_items
        SET checked = ?, updated_at = CURRENT_TIMESTAMP
        WHERE email = ? AND id = ?
        """,
        (int(bool(checked)), email, int(item_id)),
    )
    ok = (cur.rowcount or 0) > 0
    conn.commit()
    conn.close()
    return ok


def delete_shopping_item(email, item_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM shopping_items WHERE email = ? AND id = ?", (email, int(item_id)))
    ok = (cur.rowcount or 0) > 0
    conn.commit()
    conn.close()
    return ok


def clear_shopping_items(email):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM shopping_items WHERE email = ?", (email,))
    conn.commit()
    conn.close()


def set_shopping_items_order(email, item_ids):
    ids = [int(x) for x in (item_ids or []) if str(x).isdigit()]
    if not ids:
        return False

    conn = get_conn()
    cur = conn.cursor()
    for idx, item_id in enumerate(ids):
        cur.execute(
            """
            UPDATE shopping_items
            SET sort_order = ?, updated_at = CURRENT_TIMESTAMP
            WHERE email = ? AND id = ?
            """,
            (idx, email, item_id),
        )
    conn.commit()
    conn.close()
    return True


def clear_day_meals_between(start_date, end_date):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE day_plans
        SET meal_id = NULL, updated_at = CURRENT_TIMESTAMP
        WHERE day_date BETWEEN ? AND ?
        """,
        (start_date, end_date),
    )
    conn.commit()
    conn.close()
