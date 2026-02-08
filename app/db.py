import sqlite3
from pathlib import Path
import json


DB_PATH = Path("data/app.db")


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
    cur.execute("PRAGMA table_info(custom_meals)")
    columns = {row["name"] for row in cur.fetchall()}
    if "rotation_limit" not in columns:
        cur.execute("ALTER TABLE custom_meals ADD COLUMN rotation_limit TEXT NOT NULL DEFAULT '1_per_week'")
    if "preparation_json" not in columns:
        cur.execute("ALTER TABLE custom_meals ADD COLUMN preparation_json TEXT NOT NULL DEFAULT '[]'")
    conn.commit()
    conn.close()


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
    cur.execute(
        """
        INSERT INTO day_plans (day_date, cook)
        VALUES (?, ?)
        ON CONFLICT(day_date) DO UPDATE SET
            cook=excluded.cook,
            updated_at=CURRENT_TIMESTAMP
        """,
        (date_str, int(bool(cook))),
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
            id, email, name, description, image_url,
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
            tags_json, allergens_json, ingredients_json, preparation_json, rotation_limit,
            protein, carbs, calories
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email,
            name,
            description,
            image_url,
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
