import json
from pathlib import Path
from werkzeug.security import check_password_hash


DEFAULT_SETTINGS = {
    "app": {
        "name": "Menu Planner",
        "secret_key": "change-this-secret",
        "base_servings": 2,
    },
    "auth": {
        "admin_email": "bert.deknijf@gmail.com",
        "allowed_emails": ["bert.deknijf@gmail.com"],
        "allow_dev_login": True,
        "local_users": [
            {
                "email": "bert.deknijf@gmail.com",
                "name": "Bert",
                "password": "admin1234",
            }
        ],
    },
}


def deep_merge(base, override):
    out = dict(base)
    for key, value in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_settings(path: str | Path = "config/settings.json"):
    config_path = Path(path)
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(DEFAULT_SETTINGS, indent=2), encoding="utf-8")
        return DEFAULT_SETTINGS

    user_settings = json.loads(config_path.read_text(encoding="utf-8"))
    return deep_merge(DEFAULT_SETTINGS, user_settings)


def is_allowed_email(email: str, settings: dict) -> bool:
    if not email:
        return False
    email = email.lower().strip()
    admin_email = settings["auth"].get("admin_email", "").lower().strip()
    if email == admin_email:
        return True
    allowed = [e.lower().strip() for e in settings["auth"].get("allowed_emails", [])]
    return email in allowed


def find_local_user(email: str, settings: dict) -> dict | None:
    if not email:
        return None
    needle = email.lower().strip()
    for user in settings.get("auth", {}).get("local_users", []):
        if user.get("email", "").lower().strip() == needle:
            return user
    return None


def verify_local_password(user: dict, password: str) -> bool:
    stored = (user or {}).get("password", "")
    if not stored or password is None:
        return False

    # Support both plaintext (simple local testing) and werkzeug hash format.
    if stored.startswith("pbkdf2:") or stored.startswith("scrypt:"):
        return check_password_hash(stored, password)
    return stored == password
