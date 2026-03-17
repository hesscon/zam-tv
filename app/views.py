from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from .services.calendar_service import build_calendar_entries
from .services.config_service import ConfigError, load_config, save_config, validate_config_text


main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def index():
    return redirect(url_for("main.screen"))


@main_bp.get("/admin")
def admin():
    config = load_config(current_app.config["CONFIG_PATH"])
    config_text = current_app.config["CONFIG_PATH"].read_text(encoding="utf-8")
    return render_template(
        "admin.html",
        config=config,
        config_text=config_text,
    )


@main_bp.post("/admin/save")
def save_admin():
    config_text = request.form.get("config_text", "")

    try:
        validate_config_text(config_text)
        save_config(current_app.config["CONFIG_PATH"], config_text)
    except ConfigError as exc:
        flash(str(exc), "error")
        return render_template(
            "admin.html",
            config=None,
            config_text=config_text,
        ), 400

    flash("Konfiguration gespeichert.", "success")
    return redirect(url_for("main.admin"))


@main_bp.get("/screen")
def screen():
    config = load_config(current_app.config["CONFIG_PATH"])
    playlist = []

    for item in config.get("items", []):
        if not item.get("enabled", True):
            continue

        if item.get("type") == "calendar":
            playlist.append(
                {
                    "type": "calendar",
                    "title": item.get("title", "Kalender"),
                    "duration": item.get("duration", 15),
                    "events": build_calendar_entries(item),
                }
            )
            continue

        playlist.append(item)

    return render_template(
        "screen.html",
        orientation=config.get("orientation", "portrait"),
        rotation_seconds=config.get("rotation_seconds", 10),
        playlist=playlist,
    )


@main_bp.get("/uploads/<path:filename>")
def uploads(filename: str):
    return send_from_directory(current_app.config["UPLOADS_DIR"], filename)
