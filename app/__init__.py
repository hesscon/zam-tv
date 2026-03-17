from pathlib import Path

from flask import Flask

from .services.config_service import ensure_config_exists
from .views import main_bp


def create_app() -> Flask:
    app = Flask(__name__)

    base_dir = Path(__file__).resolve().parent.parent
    app.config["BASE_DIR"] = base_dir
    app.config["CONFIG_PATH"] = base_dir / "config" / "content.yaml"
    app.config["UPLOADS_DIR"] = base_dir / "data" / "uploads"
    app.config["SECRET_KEY"] = "dev-secret-key"

    ensure_config_exists(app.config["CONFIG_PATH"], app.config["UPLOADS_DIR"])
    app.register_blueprint(main_bp)

    return app
