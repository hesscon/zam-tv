import json
import logging
from pathlib import Path
import subprocess
import sys


logger = logging.getLogger(__name__)


class CaptionWorkerError(RuntimeError):
    pass


class CaptionWorkerClient:
    def __init__(
        self,
        model_path: Path,
        *,
        threads: int = 2,
        timeout_seconds: int = 1_800,
    ) -> None:
        self._model_path = model_path
        self._threads = max(1, threads)
        self._timeout_seconds = timeout_seconds
        self._working_directory = Path(__file__).resolve().parents[2]

    def generate(self, events: list[dict]) -> list[dict]:
        if not events:
            return []

        command = [
            sys.executable,
            "-m",
            "app.services.event_caption_worker",
            "--model",
            str(self._model_path),
            "--threads",
            str(self._threads),
        ]
        logger.info(
            "Caption-Worker gestartet: events=%d model=%s",
            len(events),
            self._model_path.name,
        )

        try:
            completed = subprocess.run(
                command,
                input=json.dumps(events, ensure_ascii=False),
                text=True,
                capture_output=True,
                cwd=self._working_directory,
                timeout=self._timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CaptionWorkerError(
                f"Caption-Worker Timeout nach {self._timeout_seconds}s."
            ) from exc
        except OSError as exc:
            raise CaptionWorkerError(
                f"Caption-Worker konnte nicht gestartet werden: {exc}"
            ) from exc

        if completed.stderr.strip():
            for line in completed.stderr.splitlines():
                logger.info("Caption-Worker: %s", line)

        if completed.returncode != 0:
            detail = completed.stderr.strip() or "keine Fehlermeldung"
            raise CaptionWorkerError(
                f"Caption-Worker Exit-Code {completed.returncode}: {detail}"
            )

        try:
            results = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise CaptionWorkerError(
                "Caption-Worker lieferte ungueltiges JSON."
            ) from exc

        if not isinstance(results, list) or not all(
            isinstance(result, dict) for result in results
        ):
            raise CaptionWorkerError(
                "Caption-Worker-Ausgabe muss ein JSON-Array aus Objekten sein."
            )

        logger.info("Caption-Worker beendet: ergebnisse=%d", len(results))
        return results
