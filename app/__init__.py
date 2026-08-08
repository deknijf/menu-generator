import os
from datetime import timedelta

from flask import Flask
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

from .config_loader import load_settings
from .db import bootstrap_db_settings, init_db
from .logging_setup import configure_logging
from .routes import register_routes


def _env_flag(name, default=True):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def create_app():
    load_dotenv()
    app = Flask(__name__, static_folder="../static", template_folder="../templates")

    # De app draait achter de nginx reverse proxy. Zonder dit is remote_addr altijd
    # 127.0.0.1, waardoor de login-throttle iedereen op één hoop gooit.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    configure_logging(app)

    settings = load_settings()
    app.config["SETTINGS"] = settings
    app.secret_key = os.getenv("APP_SECRET_KEY", settings["app"]["secret_key"])

    # De app draait achter HTTPS. Secure staat daarom standaard aan; zet
    # SESSION_COOKIE_SECURE=false in .env om lokaal over http te kunnen testen.
    app.config.update(
        SESSION_COOKIE_SECURE=_env_flag("SESSION_COOKIE_SECURE", True),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )

    init_db()
    bootstrap_db_settings(settings)

    register_routes(app)
    return app
