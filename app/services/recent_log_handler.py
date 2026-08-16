import logging
from collections import deque


DEFAULT_LOG_CAPACITY = 100
MAX_LOG_LINE_LENGTH = 2_000


class RecentLogHandler(logging.Handler):
    """Keep a small, thread-safe selection of recent application log lines."""

    def __init__(self, capacity: int = DEFAULT_LOG_CAPACITY) -> None:
        super().__init__()
        if capacity <= 0:
            raise ValueError("capacity muss groesser als 0 sein.")

        self._lines: deque[str] = deque(maxlen=capacity)
        self.setFormatter(
            _SingleLineFormatter(
                "%(asctime)s %(levelname)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record).replace("\r", " ").replace("\n", " ")
            if len(line) > MAX_LOG_LINE_LENGTH:
                line = f"{line[:MAX_LOG_LINE_LENGTH - 3]}..."
            self._lines.append(line)
        except Exception:
            self.handleError(record)

    def get_lines(self) -> list[str]:
        self.acquire()
        try:
            return list(self._lines)
        finally:
            self.release()


class _SingleLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # The console keeps the traceback. The admin page only needs the concise
        # message and must not be flooded by multi-line exception details.
        exception_info = record.exc_info
        exception_text = record.exc_text
        record.exc_info = None
        record.exc_text = None
        try:
            return super().format(record)
        finally:
            record.exc_info = exception_info
            record.exc_text = exception_text


def install_recent_log_handler() -> RecentLogHandler:
    application_logger = logging.getLogger("app")

    for handler in list(application_logger.handlers):
        if isinstance(handler, RecentLogHandler):
            application_logger.removeHandler(handler)

    handler = RecentLogHandler()
    application_logger.addHandler(handler)
    return handler
