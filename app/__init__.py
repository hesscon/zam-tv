import os
from datetime import timedelta
from pathlib import Path

from flask import Flask

from .services.calendar_cache import CalendarSlideCache
from .services.config_service import ensure_config_exists
from .views import main_bp


def create_app(start_calendar_cache: bool = True) -> Flask:
    app = Flask(__name__)

    base_dir = Path(__file__).resolve().parent.parent
    app.config["BASE_DIR"] = base_dir
    app.config["CONFIG_PATH"] = base_dir / "config" / "content.yaml"
    app.config["UPLOADS_DIR"] = base_dir / "data" / "uploads"
    app.config["SECRET_KEY"] = "dev-secret-key"
    refresh_seconds = int(os.environ.get("CALENDAR_CACHE_REFRESH_SECONDS", "900"))
    if refresh_seconds <= 0:
        raise ValueError("CALENDAR_CACHE_REFRESH_SECONDS muss groesser als 0 sein.")
    app.config["CALENDAR_CACHE_REFRESH_SECONDS"] = refresh_seconds

    ensure_config_exists(app.config["CONFIG_PATH"], app.config["UPLOADS_DIR"])
    app.register_blueprint(main_bp)

    calendar_cache = CalendarSlideCache(
        app.config["CONFIG_PATH"],
        refresh_interval=timedelta(seconds=refresh_seconds),
    )
    app.extensions["calendar_slide_cache"] = calendar_cache
    if start_calendar_cache:
        calendar_cache.start()

    return app
