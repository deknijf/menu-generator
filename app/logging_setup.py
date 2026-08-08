"""Logging-configuratie.

De app draait onder gunicorn in een container, dus alles gaat naar stdout en wordt
door Docker en journald opgepikt (`journalctl -u meal-planner`). Er is bewust geen
logbestand: dat zou in de container staan en bij elke redeploy verdwijnen.
"""

import logging
import os
import sys

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"


def configure_logging(app=None):
    """Zet één stdout-handler op de root logger. Idempotent."""
    level_name = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    if not any(getattr(h, "_meal_planner", False) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        handler._meal_planner = True
        root.addHandler(handler)

    if app is not None:
        app.logger.setLevel(level)

    return root


def get_logger(name):
    return logging.getLogger(name)
