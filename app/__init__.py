import os
from flask import Flask
from dotenv import load_dotenv

from .config_loader import load_settings
from .db import bootstrap_db_settings, init_db
from .routes import register_routes


def create_app():
    load_dotenv()
    app = Flask(__name__, static_folder="../static", template_folder="../templates")

    settings = load_settings()
    app.config["SETTINGS"] = settings
    app.secret_key = os.getenv("APP_SECRET_KEY", settings["app"]["secret_key"])

    init_db()
    bootstrap_db_settings(settings)

    register_routes(app)
    return app
