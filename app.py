import logging
import os

from app import create_app


logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

debug = os.environ.get("APP_DEBUG", "").lower() in {"1", "true", "yes"}
start_calendar_cache = not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
app = create_app(start_calendar_cache=start_calendar_cache)


if __name__ == "__main__":
    # Environment variables make local runs and Docker runs behave the same way.
    host = os.environ.get("APP_HOST", "0.0.0.0")
    port = int(os.environ.get("APP_PORT", "8000"))
    app.run(host=host, port=port, debug=debug)
