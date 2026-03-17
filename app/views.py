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
from werkzeug.utils import secure_filename

from .services.calendar_service import build_calendar_slides
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
        uploads=list_uploads(current_app.config["UPLOADS_DIR"]),
    )


@main_bp.post("/admin/save")
def save_admin():
    config_text = request.form.get("config_text", "")

    try:
        # Validate before writing so the previous working config stays intact on errors.
        validate_config_text(config_text)
        save_config(current_app.config["CONFIG_PATH"], config_text)
    except ConfigError as exc:
        flash(str(exc), "error")
        return render_template(
            "admin.html",
            config=None,
            config_text=config_text,
            uploads=list_uploads(current_app.config["UPLOADS_DIR"]),
        ), 400

    flash("Konfiguration gespeichert.", "success")
    return redirect(url_for("main.admin"))


@main_bp.post("/admin/upload")
def upload_media():
    files = request.files.getlist("media_files")
    saved_files = []

    for file in files:
        filename = secure_filename(file.filename or "")
        if not filename:
            continue

        target_path = current_app.config["UPLOADS_DIR"] / filename
        file.save(target_path)
        saved_files.append(filename)

    if saved_files:
        flash(f"Hochgeladen: {', '.join(saved_files)}", "success")
    if not saved_files:
        flash("Keine Datei ausgewaehlt.", "error")

    return redirect(url_for("main.admin"))


@main_bp.post("/admin/cleanup-unused")
def cleanup_unused_uploads():
    config = load_config(current_app.config["CONFIG_PATH"])
    referenced_files = {
        item.get("content")
        for item in config.get("items", [])
        if item.get("type") in {"image", "video"} and item.get("content")
    }
    deleted_files = []

    for path in current_app.config["UPLOADS_DIR"].iterdir():
        if not path.is_file() or path.name.startswith("."):
            continue

        if path.name in referenced_files:
            continue

        path.unlink()
        deleted_files.append(path.name)

    if deleted_files:
        flash(f"Nicht benutzte Dateien geloescht: {', '.join(sorted(deleted_files, key=str.lower))}", "success")
    else:
        flash("Keine unbenutzten Dateien gefunden.", "success")

    return redirect(url_for("main.admin"))


@main_bp.get("/screen")
def screen():
    config = load_config(current_app.config["CONFIG_PATH"])
    playlist = []

    for item in config.get("items", []):
        if not item.get("enabled", True):
            continue

        if item.get("type") == "calendar":
            # A single calendar source can expand into several event slides.
            playlist.extend(build_calendar_slides(item))
            continue

        playlist.append(item)

    return render_template(
        "screen.html",
        body_class="screen-body",
        orientation=config.get("orientation", "portrait"),
        playlist=playlist,
    )


@main_bp.get("/uploads/<path:filename>")
def uploads(filename: str):
    return send_from_directory(current_app.config["UPLOADS_DIR"], filename)


def list_uploads(uploads_dir) -> list[str]:
    return sorted(
        [path.name for path in uploads_dir.iterdir() if path.is_file() and not path.name.startswith(".")],
        key=str.lower,
    )
