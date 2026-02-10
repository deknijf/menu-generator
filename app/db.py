import sqlite3
from pathlib import Path
import json
import re
from uuid import uuid4
from werkzeug.security import check_password_hash, generate_password_hash


DB_PATH = Path("data/app.db")
DEFAULT_GROUP_SLUG = "default-family"
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
    def _safe_add_column(sql):
        try:
            cur.execute(sql)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        INSERT OR IGNORE INTO groups (id, slug, name)
        VALUES (1, ?, 'Default familie')
        """,
        (DEFAULT_GROUP_SLUG,),
    )
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
            is_group_admin INTEGER NOT NULL DEFAULT 0,
            group_id INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_user_groups (
            email TEXT NOT NULL,
            group_id INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (email, group_id)
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
        CREATE TABLE IF NOT EXISTS group_day_plans (
            group_id INTEGER NOT NULL,
            day_date TEXT NOT NULL,
            cook INTEGER NOT NULL DEFAULT 1,
            meal_id TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (group_id, day_date)
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
        CREATE TABLE IF NOT EXISTS group_menu_preferences (
            group_id INTEGER PRIMARY KEY,
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
            group_id INTEGER NOT NULL DEFAULT 1,
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
            group_id INTEGER NOT NULL DEFAULT 1,
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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS shopping_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            group_id INTEGER NOT NULL DEFAULT 1,
            purchased_on TEXT NOT NULL,
            purchased_time_hhmm TEXT NOT NULL DEFAULT '',
            items_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute("PRAGMA table_info(auth_users)")
    auth_columns = {row["name"] for row in cur.fetchall()}
    if "is_group_admin" not in auth_columns:
        _safe_add_column("ALTER TABLE auth_users ADD COLUMN is_group_admin INTEGER NOT NULL DEFAULT 0")
    if "group_id" not in auth_columns:
        _safe_add_column("ALTER TABLE auth_users ADD COLUMN group_id INTEGER NOT NULL DEFAULT 1")

    cur.execute("PRAGMA table_info(custom_meals)")
    columns = {row["name"] for row in cur.fetchall()}
    if "group_id" not in columns:
        _safe_add_column("ALTER TABLE custom_meals ADD COLUMN group_id INTEGER NOT NULL DEFAULT 1")
    if "rotation_limit" not in columns:
        _safe_add_column("ALTER TABLE custom_meals ADD COLUMN rotation_limit TEXT NOT NULL DEFAULT '1_per_week'")
    if "preparation_json" not in columns:
        _safe_add_column("ALTER TABLE custom_meals ADD COLUMN preparation_json TEXT NOT NULL DEFAULT '[]'")
    if "rating" not in columns:
        _safe_add_column("ALTER TABLE custom_meals ADD COLUMN rating INTEGER NOT NULL DEFAULT 3")
    cur.execute("PRAGMA table_info(shopping_items)")
    shopping_item_columns = {row["name"] for row in cur.fetchall()}
    if "group_id" not in shopping_item_columns:
        _safe_add_column("ALTER TABLE shopping_items ADD COLUMN group_id INTEGER NOT NULL DEFAULT 1")

    cur.execute("PRAGMA table_info(shopping_history)")
    shopping_history_columns = {row["name"] for row in cur.fetchall()}
    if "group_id" not in shopping_history_columns:
        _safe_add_column("ALTER TABLE shopping_history ADD COLUMN group_id INTEGER NOT NULL DEFAULT 1")
    if "purchased_time_hhmm" not in shopping_history_columns:
        _safe_add_column("ALTER TABLE shopping_history ADD COLUMN purchased_time_hhmm TEXT NOT NULL DEFAULT ''")

    # One-time migration for old single-tenant day_plans -> group_day_plans.
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='day_plans'")
    if cur.fetchone():
        cur.execute(
            """
            INSERT OR IGNORE INTO group_day_plans (group_id, day_date, cook, meal_id, updated_at)
            SELECT 1, day_date, cook, meal_id, updated_at FROM day_plans
            """
        )

    # Ensure existing rows are associated with a group.
    cur.execute("UPDATE auth_users SET group_id = 1 WHERE group_id IS NULL OR group_id <= 0")
    cur.execute("UPDATE auth_users SET is_group_admin = 0 WHERE is_group_admin IS NULL")
    cur.execute(
        """
        INSERT OR IGNORE INTO auth_user_groups (email, group_id)
        SELECT email, group_id FROM auth_users
        """
    )
    cur.execute("UPDATE custom_meals SET group_id = 1 WHERE group_id IS NULL OR group_id <= 0")
    cur.execute("UPDATE shopping_items SET group_id = 1 WHERE group_id IS NULL OR group_id <= 0")
    cur.execute("UPDATE shopping_history SET group_id = 1 WHERE group_id IS NULL OR group_id <= 0")
    cur.execute(
        """
        INSERT OR IGNORE INTO group_menu_preferences (group_id, menu_mode)
        SELECT au.group_id, MAX(ump.menu_mode)
        FROM user_menu_preferences ump
        JOIN auth_users au ON au.email = ump.email
        GROUP BY au.group_id
        """
    )
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


def _slugify(value):
    token = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return token or f"group-{uuid4().hex[:8]}"


def _group_id_for_email(cur, email):
    token = str(email or "").strip().lower()
    if not token:
        return 1
    cur.execute("SELECT group_id FROM auth_users WHERE email = ?", (token,))
    row = cur.fetchone()
    gid = int((row["group_id"] if row and row["group_id"] is not None else 1) or 1)
    return gid if gid > 0 else 1


def get_user_group_id(email):
    conn = get_conn()
    cur = conn.cursor()
    gid = _group_id_for_email(cur, email)
    conn.close()
    return gid


def get_user_group_ids(email):
    token = str(email or "").strip().lower()
    if not token:
        return [1]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT group_id
        FROM auth_user_groups
        WHERE email = ?
        ORDER BY group_id ASC
        """,
        (token,),
    )
    gids = [int(row["group_id"] or 1) for row in cur.fetchall()]
    if not gids:
        cur.execute("SELECT group_id FROM auth_users WHERE email = ?", (token,))
        row = cur.fetchone()
        if row:
            gids = [int(row["group_id"] or 1)]
            cur.execute(
                "INSERT OR IGNORE INTO auth_user_groups (email, group_id) VALUES (?, ?)",
                (token, gids[0]),
            )
            conn.commit()
    conn.close()
    return sorted({gid for gid in gids if gid > 0}) or [1]


def upsert_auth_user(email, name, password, is_admin, password_is_hash=False, group_id=None, is_group_admin=False):
    email_token = str(email or "").strip().lower()
    if not email_token:
        return False
    password_token = str(password or "")
    if not password_token:
        return False
    password_hash = password_token if password_is_hash else _as_password_hash(password_token)
    conn = get_conn()
    cur = conn.cursor()
    gid = int(group_id or 1)
    if gid <= 0:
        gid = 1
    cur.execute(
        """
        INSERT INTO auth_users (email, name, password_hash, is_admin, is_group_admin, group_id)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            name=excluded.name,
            password_hash=excluded.password_hash,
            is_admin=excluded.is_admin,
            is_group_admin=excluded.is_group_admin,
            group_id=excluded.group_id,
            updated_at=CURRENT_TIMESTAMP
        """,
        (email_token, str(name or "").strip(), password_hash, int(bool(is_admin)), int(bool(is_group_admin)), gid),
    )
    cur.execute("INSERT OR IGNORE INTO auth_user_groups (email, group_id) VALUES (?, ?)", (email_token, gid))
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
        "SELECT email, name, password_hash, is_admin, is_group_admin, group_id FROM auth_users WHERE email = ?",
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
        "is_group_admin": bool(row["is_group_admin"]),
        "group_id": int(row["group_id"] or 1),
    }


def verify_auth_password(email, password):
    user = get_auth_user(email)
    if not user:
        return None
    if not check_password_hash(user.get("password_hash", ""), str(password or "")):
        return None
    return user


def list_auth_users(group_id=None):
    conn = get_conn()
    cur = conn.cursor()
    if group_id is None:
        cur.execute(
            """
            SELECT email, name, is_admin, is_group_admin, group_id, created_at, updated_at
            FROM auth_users
            ORDER BY email ASC
            """
        )
    else:
        cur.execute(
            """
            SELECT email, name, is_admin, is_group_admin, group_id, created_at, updated_at
            FROM auth_users
            WHERE group_id = ?
            ORDER BY email ASC
            """,
            (int(group_id or 1),),
        )
    rows = [
        {
            "email": row["email"],
            "name": row["name"] or row["email"],
            "is_admin": bool(row["is_admin"]),
            "is_group_admin": bool(row["is_group_admin"]),
            "group_id": int(row["group_id"] or 1),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in cur.fetchall()
    ]
    conn.close()
    return rows


def list_groups():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, slug, name, created_at
        FROM groups
        ORDER BY id ASC
        """
    )
    rows = [
        {
            "id": int(row["id"]),
            "slug": row["slug"],
            "name": row["name"],
            "created_at": row["created_at"],
        }
        for row in cur.fetchall()
    ]
    conn.close()
    return rows


def group_exists(group_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM groups WHERE id = ?", (int(group_id or 0),))
    row = cur.fetchone()
    conn.close()
    return bool(row)


def create_group(name):
    name_token = str(name or "").strip()
    if not name_token:
        return None
    conn = get_conn()
    cur = conn.cursor()
    base_slug = _slugify(name_token)
    slug = base_slug
    idx = 1
    while True:
        cur.execute("SELECT id FROM groups WHERE slug = ?", (slug,))
        if not cur.fetchone():
            break
        idx += 1
        slug = f"{base_slug}-{idx}"
    cur.execute(
        "INSERT INTO groups (slug, name) VALUES (?, ?)",
        (slug, name_token),
    )
    group_id = int(cur.lastrowid or 0)
    conn.commit()
    conn.close()
    return group_id or None


def rename_group(group_id, name):
    gid = int(group_id or 0)
    if gid <= 0:
        return False
    name_token = str(name or "").strip()
    if not name_token:
        return False
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE groups SET name = ? WHERE id = ?", (name_token, gid))
    ok = (cur.rowcount or 0) > 0
    conn.commit()
    conn.close()
    return ok


def delete_group(group_id):
    gid = int(group_id or 0)
    if gid <= 1:
        return False, "protected"
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM groups WHERE id = ?", (gid,))
    if not cur.fetchone():
        conn.close()
        return False, "not_found"

    cur.execute("SELECT email FROM auth_users WHERE group_id = ?", (gid,))
    affected_emails = [str(row["email"] or "").strip().lower() for row in cur.fetchall()]

    # Remove group memberships first.
    cur.execute("DELETE FROM auth_user_groups WHERE group_id = ?", (gid,))

    # Repoint users whose primary group is being deleted.
    for email in affected_emails:
        cur.execute(
            """
            SELECT group_id
            FROM auth_user_groups
            WHERE email = ?
            ORDER BY group_id ASC
            LIMIT 1
            """,
            (email,),
        )
        next_row = cur.fetchone()
        next_gid = int(next_row["group_id"] or 1) if next_row else 1
        if next_gid <= 0:
            next_gid = 1
        cur.execute(
            "UPDATE auth_users SET group_id = ?, updated_at = CURRENT_TIMESTAMP WHERE email = ?",
            (next_gid, email),
        )
        cur.execute("INSERT OR IGNORE INTO auth_user_groups (email, group_id) VALUES (?, ?)", (email, next_gid))

    # Cleanup group-scoped data.
    cur.execute("DELETE FROM group_day_plans WHERE group_id = ?", (gid,))
    cur.execute("DELETE FROM group_menu_preferences WHERE group_id = ?", (gid,))
    cur.execute("DELETE FROM custom_meals WHERE group_id = ?", (gid,))
    cur.execute("DELETE FROM shopping_items WHERE group_id = ?", (gid,))
    cur.execute("DELETE FROM shopping_history WHERE group_id = ?", (gid,))
    cur.execute("DELETE FROM groups WHERE id = ?", (gid,))
    deleted = (cur.rowcount or 0) > 0

    conn.commit()
    conn.close()
    return (deleted, "ok" if deleted else "not_found")


def set_auth_user_group(email, group_id):
    email_token = str(email or "").strip().lower()
    gid = int(group_id or 0)
    if not email_token or gid <= 0:
        return False
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE auth_users SET group_id = ?, updated_at = CURRENT_TIMESTAMP WHERE email = ?", (gid, email_token))
    updated = (cur.rowcount or 0) > 0
    if updated:
        cur.execute("DELETE FROM auth_user_groups WHERE email = ?", (email_token,))
        cur.execute("INSERT OR IGNORE INTO auth_user_groups (email, group_id) VALUES (?, ?)", (email_token, gid))
    conn.commit()
    conn.close()
    return updated


def set_auth_user_groups(email, group_ids):
    email_token = str(email or "").strip().lower()
    ids = sorted({int(item) for item in (group_ids or []) if int(item) > 0})
    if not email_token or not ids:
        return False
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT group_id FROM auth_users WHERE email = ?", (email_token,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False
    current_gid = int(row["group_id"] or 1)
    next_gid = current_gid if current_gid in ids else ids[0]
    cur.execute("UPDATE auth_users SET group_id = ?, updated_at = CURRENT_TIMESTAMP WHERE email = ?", (next_gid, email_token))
    cur.execute("DELETE FROM auth_user_groups WHERE email = ?", (email_token,))
    cur.executemany(
        "INSERT OR IGNORE INTO auth_user_groups (email, group_id) VALUES (?, ?)",
        [(email_token, gid) for gid in ids],
    )
    conn.commit()
    conn.close()
    return True


def set_auth_user_group_admin(email, is_group_admin):
    email_token = str(email or "").strip().lower()
    if not email_token:
        return False
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE auth_users SET is_group_admin = ?, updated_at = CURRENT_TIMESTAMP WHERE email = ?",
        (int(bool(is_group_admin)), email_token),
    )
    ok = (cur.rowcount or 0) > 0
    conn.commit()
    conn.close()
    return ok


def set_auth_user_admin(email, is_admin):
    email_token = str(email or "").strip().lower()
    if not email_token:
        return False
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE auth_users SET is_admin = ?, updated_at = CURRENT_TIMESTAMP WHERE email = ?",
        (int(bool(is_admin)), email_token),
    )
    ok = (cur.rowcount or 0) > 0
    conn.commit()
    conn.close()
    return ok


def delete_auth_user(email):
    email_token = str(email or "").strip().lower()
    if not email_token:
        return False
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM auth_users WHERE email = ?", (email_token,))
    ok = (cur.rowcount or 0) > 0
    cur.execute("DELETE FROM auth_user_groups WHERE email = ?", (email_token,))
    cur.execute("DELETE FROM users WHERE email = ?", (email_token,))
    conn.commit()
    conn.close()
    return ok


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


def update_auth_user_identity(current_email, new_email, new_name):
    old_token = str(current_email or "").strip().lower()
    new_token = str(new_email or "").strip().lower()
    name_token = str(new_name or "").strip()
    if not old_token or not new_token:
        return False, "invalid"

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT email, name, is_admin FROM auth_users WHERE email = ?",
        (old_token,),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return False, "not_found"

    if new_token != old_token:
        cur.execute("SELECT email FROM auth_users WHERE email = ?", (new_token,))
        if cur.fetchone():
            conn.close()
            return False, "exists"

    final_name = name_token or row["name"] or new_token
    try:
        cur.execute(
            """
            UPDATE auth_users
            SET email = ?, name = ?, updated_at = CURRENT_TIMESTAMP
            WHERE email = ?
            """,
            (new_token, final_name, old_token),
        )
        cur.execute("UPDATE users SET email = ?, name = ?, is_admin = ? WHERE email = ?", (new_token, final_name, int(bool(row["is_admin"])), old_token))
        if (cur.rowcount or 0) == 0:
            cur.execute(
                """
                INSERT INTO users (email, name, is_admin)
                VALUES (?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    name=excluded.name,
                    is_admin=excluded.is_admin
                """,
                (new_token, final_name, int(bool(row["is_admin"]))),
            )
        cur.execute("UPDATE user_preferences SET email = ? WHERE email = ?", (new_token, old_token))
        cur.execute("UPDATE user_food_preferences SET email = ? WHERE email = ?", (new_token, old_token))
        cur.execute("UPDATE user_food_dislikes SET email = ? WHERE email = ?", (new_token, old_token))
        cur.execute("UPDATE user_menu_preferences SET email = ? WHERE email = ?", (new_token, old_token))
        cur.execute("UPDATE custom_meals SET email = ? WHERE email = ?", (new_token, old_token))
        cur.execute("UPDATE shopping_items SET email = ? WHERE email = ?", (new_token, old_token))
        cur.execute("UPDATE shopping_history SET email = ? WHERE email = ?", (new_token, old_token))
        cur.execute("UPDATE auth_user_groups SET email = ? WHERE email = ?", (new_token, old_token))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()
        return False, "exists"
    except Exception:
        conn.rollback()
        conn.close()
        return False, "error"

    conn.close()
    return True, ""


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


def set_day_cook(group_id, date_str, cook):
    conn = get_conn()
    cur = conn.cursor()
    gid = int(group_id or 1)
    cook_int = int(bool(cook))
    cur.execute(
        """
        INSERT INTO group_day_plans (group_id, day_date, cook, meal_id)
        VALUES (?, ?, ?, CASE WHEN ? = 0 THEN NULL ELSE NULL END)
        ON CONFLICT(group_id, day_date) DO UPDATE SET
            cook=excluded.cook,
            meal_id=CASE WHEN excluded.cook = 0 THEN NULL ELSE group_day_plans.meal_id END,
            updated_at=CURRENT_TIMESTAMP
        """,
        (gid, date_str, cook_int, cook_int),
    )
    conn.commit()
    conn.close()


def set_day_meal(group_id, date_str, meal_id):
    conn = get_conn()
    cur = conn.cursor()
    gid = int(group_id or 1)
    cur.execute(
        """
        INSERT INTO group_day_plans (group_id, day_date, cook, meal_id)
        VALUES (?, ?, 1, ?)
        ON CONFLICT(group_id, day_date) DO UPDATE SET
            meal_id=excluded.meal_id,
            cook=1,
            updated_at=CURRENT_TIMESTAMP
        """,
        (gid, date_str, meal_id),
    )
    conn.commit()
    conn.close()


def get_days_between(group_id, start_date, end_date):
    conn = get_conn()
    cur = conn.cursor()
    gid = int(group_id or 1)
    cur.execute(
        """
        SELECT day_date, cook, meal_id
        FROM group_day_plans
        WHERE group_id = ? AND day_date BETWEEN ? AND ?
        ORDER BY day_date ASC
        """,
        (gid, start_date, end_date),
    )
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def get_day(group_id, date_str):
    conn = get_conn()
    cur = conn.cursor()
    gid = int(group_id or 1)
    cur.execute(
        "SELECT day_date, cook, meal_id FROM group_day_plans WHERE group_id = ? AND day_date = ?",
        (gid, date_str),
    )
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


def get_group_menu_mode(group_id):
    gid = int(group_id or 1)
    if gid <= 0:
        gid = 1
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT menu_mode FROM group_menu_preferences WHERE group_id = ?", (gid,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return "ai_only"
    return (row["menu_mode"] or "ai_only").strip()


def set_group_menu_mode(group_id, menu_mode):
    gid = int(group_id or 1)
    if gid <= 0:
        gid = 1
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO group_menu_preferences (group_id, menu_mode)
        VALUES (?, ?)
        ON CONFLICT(group_id) DO UPDATE SET
            menu_mode=excluded.menu_mode,
            updated_at=CURRENT_TIMESTAMP
        """,
        (gid, str(menu_mode or "ai_only")),
    )
    conn.commit()
    conn.close()


def list_custom_meals(email):
    gid = get_user_group_id(email)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            id, email, name, description, image_url, rating,
            tags_json, allergens_json, ingredients_json, preparation_json, rotation_limit,
            protein, carbs, calories
        FROM custom_meals
        WHERE group_id = ?
        ORDER BY id DESC
        """,
        (gid,),
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
    gid = get_user_group_id(email)
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
            group_id,
            rating,
            tags_json, allergens_json, ingredients_json, preparation_json, rotation_limit,
            protein, carbs, calories
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email,
            name,
            description,
            image_url,
            gid,
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
    gid = get_user_group_id(email)
    ids = [int(x) for x in (meal_ids or []) if str(x).isdigit()]
    if not ids:
        return 0

    conn = get_conn()
    cur = conn.cursor()
    placeholders = ", ".join(["?"] * len(ids))
    cur.execute(
        f"DELETE FROM custom_meals WHERE group_id = ? AND id IN ({placeholders})",
        [gid, *ids],
    )
    deleted = cur.rowcount or 0
    conn.commit()
    conn.close()
    return deleted


def update_custom_meal(email, meal_id, payload):
    gid = get_user_group_id(email)
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
        WHERE group_id = ? AND id = ?
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
            gid,
            int(meal_id),
        ),
    )
    updated = (cur.rowcount or 0) > 0
    conn.commit()
    conn.close()
    return updated


def get_custom_meal(email, meal_id):
    gid = get_user_group_id(email)
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
        WHERE group_id = ? AND id = ?
        """,
        (gid, int(meal_id)),
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
    gid = get_user_group_id(email)
    if not str(meal_id).isdigit():
        return False
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE custom_meals
        SET image_url = ?
        WHERE group_id = ? AND id = ?
        """,
        (str(image_url or "").strip(), gid, int(meal_id)),
    )
    ok = (cur.rowcount or 0) > 0
    conn.commit()
    conn.close()
    return ok


def update_custom_meal_rating(email, meal_id, rating):
    gid = get_user_group_id(email)
    if not str(meal_id).isdigit():
        return False
    value = max(1, min(5, int(rating or 3)))
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE custom_meals
        SET rating = ?
        WHERE group_id = ? AND id = ?
        """,
        (value, gid, int(meal_id)),
    )
    ok = (cur.rowcount or 0) > 0
    conn.commit()
    conn.close()
    return ok


def list_shopping_items(email):
    gid = get_user_group_id(email)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, quantity, unit, checked, sort_order
        FROM shopping_items
        WHERE group_id = ?
        ORDER BY sort_order ASC, id ASC
        """,
        (gid,),
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
    gid = get_user_group_id(email)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM shopping_items WHERE group_id = ?", (gid,))
    for index, item in enumerate(items or []):
        cur.execute(
            """
            INSERT INTO shopping_items (email, group_id, name, quantity, unit, checked, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                email,
                gid,
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
    gid = get_user_group_id(email)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(MAX(sort_order), -1) AS max_sort FROM shopping_items WHERE group_id = ?", (gid,))
    max_sort = int(cur.fetchone()["max_sort"])
    cur.execute(
        """
        INSERT INTO shopping_items (email, group_id, name, quantity, unit, checked, sort_order)
        VALUES (?, ?, ?, ?, ?, 0, ?)
        """,
        (email, gid, str(name).strip(), float(quantity or 0), str(unit or "").strip(), max_sort + 1),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def set_shopping_item_checked(email, item_id, checked):
    gid = get_user_group_id(email)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE shopping_items
        SET checked = ?, updated_at = CURRENT_TIMESTAMP
        WHERE group_id = ? AND id = ?
        """,
        (int(bool(checked)), gid, int(item_id)),
    )
    ok = (cur.rowcount or 0) > 0
    conn.commit()
    conn.close()
    return ok


def delete_shopping_item(email, item_id):
    gid = get_user_group_id(email)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM shopping_items WHERE group_id = ? AND id = ?", (gid, int(item_id)))
    ok = (cur.rowcount or 0) > 0
    conn.commit()
    conn.close()
    return ok


def clear_shopping_items(email):
    gid = get_user_group_id(email)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM shopping_items WHERE group_id = ?", (gid,))
    conn.commit()
    conn.close()


def complete_shopping_items(email, purchased_on, purchased_time_hhmm):
    gid = get_user_group_id(email)
    day_token = str(purchased_on or "").strip()
    time_token = str(purchased_time_hhmm or "").strip()
    if not day_token:
        return (False, "invalid_date")
    if not time_token:
        time_token = "00:00"

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, quantity, unit, checked, sort_order
        FROM shopping_items
        WHERE group_id = ?
        ORDER BY sort_order ASC, id ASC
        """,
        (gid,),
    )
    rows = cur.fetchall()
    if not rows:
        conn.close()
        return (False, "empty")

    items = []
    for row in rows:
        items.append(
            {
                "name": row["name"],
                "quantity": float(row["quantity"] or 0),
                "unit": row["unit"] or "",
                "checked": bool(row["checked"]),
                "sort_order": int(row["sort_order"] or 0),
            }
        )
    checked_items = [item for item in items if item.get("checked")]
    if not checked_items:
        conn.close()
        return (False, "none_checked")

    cur.execute(
        """
        INSERT INTO shopping_history (email, group_id, purchased_on, purchased_time_hhmm, items_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (email, gid, day_token, time_token, json.dumps(checked_items)),
    )
    cur.execute(
        """
        DELETE FROM shopping_items
        WHERE group_id = ? AND checked = 1
        """,
        (gid,),
    )
    conn.commit()
    conn.close()
    return (True, "ok")


def get_shopping_history_dates_between(email, start_date, end_date):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT purchased_on
        FROM shopping_history
        WHERE email = ? AND purchased_on BETWEEN ? AND ?
        GROUP BY purchased_on
        ORDER BY purchased_on ASC
        """,
        (email, start_date, end_date),
    )
    rows = [str(row["purchased_on"]) for row in cur.fetchall()]
    conn.close()
    return rows


def get_shopping_history_counts_between(email, start_date, end_date):
    gid = get_user_group_id(email)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT purchased_on, COUNT(*) AS list_count
        FROM shopping_history
        WHERE group_id = ? AND purchased_on BETWEEN ? AND ?
        GROUP BY purchased_on
        ORDER BY purchased_on ASC
        """,
        (gid, start_date, end_date),
    )
    rows = {str(row["purchased_on"]): int(row["list_count"] or 0) for row in cur.fetchall()}
    conn.close()
    return rows


def list_shopping_history_for_day(email, day_iso):
    gid = get_user_group_id(email)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, purchased_on, purchased_time_hhmm, items_json, created_at
        FROM shopping_history
        WHERE group_id = ? AND purchased_on = ?
        ORDER BY id DESC
        """,
        (gid, str(day_iso or "").strip()),
    )
    rows = cur.fetchall()
    conn.close()

    out = []
    for row in rows:
        try:
            items = json.loads(row["items_json"] or "[]")
        except Exception:
            items = []
        normalized_items = []
        for item in items:
            normalized_items.append(
                {
                    "name": str((item or {}).get("name", "")).strip(),
                    "quantity": float((item or {}).get("quantity") or 0),
                    "unit": str((item or {}).get("unit", "")).strip(),
                }
            )
        time_hhmm = str(row["purchased_time_hhmm"] or "").strip() or "--:--"
        out.append(
            {
                "id": int(row["id"]),
                "purchased_on": row["purchased_on"],
                "created_at": row["created_at"],
                "time_hhmm": time_hhmm,
                "items": normalized_items,
            }
        )
    return out


def delete_shopping_history_entry(email, entry_id):
    gid = get_user_group_id(email)
    if not str(entry_id).isdigit():
        return False
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM shopping_history
        WHERE group_id = ? AND id = ?
        """,
        (gid, int(entry_id)),
    )
    ok = (cur.rowcount or 0) > 0
    conn.commit()
    conn.close()
    return ok


def set_shopping_items_order(email, item_ids):
    gid = get_user_group_id(email)
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
            WHERE group_id = ? AND id = ?
            """,
            (idx, gid, item_id),
        )
    conn.commit()
    conn.close()
    return True


def clear_day_meals_between(group_id, start_date, end_date):
    conn = get_conn()
    cur = conn.cursor()
    gid = int(group_id or 1)
    cur.execute(
        """
        UPDATE group_day_plans
        SET meal_id = NULL, updated_at = CURRENT_TIMESTAMP
        WHERE group_id = ? AND day_date BETWEEN ? AND ?
        """,
        (gid, start_date, end_date),
    )
    conn.commit()
    conn.close()
