import os
from datetime import timedelta
from pathlib import Path

from flask import Flask

from .services.calendar_cache import CalendarSlideCache
from .services.calendar_snapshot_builder import CalendarSnapshotBuilder
from .services.caption_worker_client import CaptionWorkerClient
from .services.config_service import ensure_config_exists
from .services.recent_log_handler import install_recent_log_handler
from .services.screen_heartbeat import ScreenHeartbeat
from .services.textecke_worker import TexteckeWorker
from .views import main_bp


def create_app(
    start_calendar_cache: bool = True,
    start_textecke_worker: bool | None = None,
) -> Flask:
    app = Flask(__name__)
    recent_log_handler = install_recent_log_handler()

    base_dir = Path(__file__).resolve().parent.parent
    app.config["BASE_DIR"] = base_dir
    app.config["CONFIG_PATH"] = base_dir / "config" / "content.yaml"
    app.config["UPLOADS_DIR"] = base_dir / "data" / "uploads"
    app.config["CALENDAR_CACHE_PATH"] = (
        base_dir / "data" / "cache" / "calendar_cache.json"
    )
    app.config["SECRET_KEY"] = "dev-secret-key"
    refresh_seconds = int(os.environ.get("CALENDAR_CACHE_REFRESH_SECONDS", "900"))
    if refresh_seconds <= 0:
        raise ValueError("CALENDAR_CACHE_REFRESH_SECONDS muss groesser als 0 sein.")
    app.config["CALENDAR_CACHE_REFRESH_SECONDS"] = refresh_seconds
    model_path = Path(
        os.environ.get(
            "EVENT_CAPTION_MODEL_PATH",
            "data/models/gemma-4-E4B-it-Q5_K_M.gguf",
        )
    )
    if not model_path.is_absolute():
        model_path = base_dir / model_path
    app.config["EVENT_CAPTION_MODEL_PATH"] = model_path
    caption_threads = int(os.environ.get("EVENT_CAPTION_THREADS", "2"))
    caption_timeout = int(os.environ.get("EVENT_CAPTION_TIMEOUT_SECONDS", "1800"))
    caption_nice_level = int(os.environ.get("EVENT_CAPTION_NICE_LEVEL", "10"))
    if caption_threads <= 0 or caption_timeout <= 0:
        raise ValueError(
            "EVENT_CAPTION_THREADS und EVENT_CAPTION_TIMEOUT_SECONDS "
            "muessen groesser als 0 sein."
        )
    if not 0 <= caption_nice_level <= 19:
        raise ValueError(
            "EVENT_CAPTION_NICE_LEVEL muss zwischen 0 und 19 liegen."
        )

    ensure_config_exists(app.config["CONFIG_PATH"], app.config["UPLOADS_DIR"])
    app.register_blueprint(main_bp)

    caption_worker = CaptionWorkerClient(
        model_path,
        threads=caption_threads,
        timeout_seconds=caption_timeout,
        nice_level=caption_nice_level,
    )
    snapshot_builder = CalendarSnapshotBuilder(caption_worker)
    calendar_cache = CalendarSlideCache(
        app.config["CONFIG_PATH"],
        app.config["CALENDAR_CACHE_PATH"],
        snapshot_builder,
        refresh_interval=timedelta(seconds=refresh_seconds),
    )
    app.extensions["calendar_slide_cache"] = calendar_cache
    textecke_worker = TexteckeWorker(app.config["CONFIG_PATH"])
    app.extensions["textecke_worker"] = textecke_worker
    app.extensions["recent_log_handler"] = recent_log_handler
    app.extensions["screen_heartbeat"] = ScreenHeartbeat()
    if start_calendar_cache:
        calendar_cache.start()
    if start_textecke_worker is None:
        start_textecke_worker = start_calendar_cache
    if start_textecke_worker:
        textecke_worker.start()

    return app
