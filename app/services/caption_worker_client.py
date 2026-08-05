import json
import logging
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
from threading import Thread
from typing import Iterator


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
        nice_level: int = 10,
    ) -> None:
        if not 0 <= nice_level <= 19:
            raise ValueError("nice_level muss zwischen 0 und 19 liegen.")
        self._model_path = model_path
        self._threads = max(1, threads)
        self._timeout_seconds = timeout_seconds
        self._nice_level = nice_level
        self._working_directory = Path(__file__).resolve().parents[2]

    def generate(self, events: list[dict]) -> Iterator[dict]:
        if not events:
            return

        command = [
            "nice",
            "-n",
            str(self._nice_level),
            sys.executable,
            "-m",
            "app.services.event_caption_worker",
            "--model",
            str(self._model_path),
            "--threads",
            str(self._threads),
        ]
        logger.info(
            "Caption-Worker gestartet: events=%d model=%s nice=%d",
            len(events),
            self._model_path.name,
            self._nice_level,
        )

        process: subprocess.Popen[str] | None = None
        stderr_lines: list[str] = []
        stdout_queue: Queue[str | None] = Queue()

        try:
            process = subprocess.Popen(
                command,
                text=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self._working_directory,
                bufsize=1,
            )
        except OSError as exc:
            raise CaptionWorkerError(
                f"Caption-Worker konnte nicht gestartet werden: {exc}"
            ) from exc

        try:
            assert process.stdin is not None
            assert process.stdout is not None
            assert process.stderr is not None

            stdout_thread = Thread(
                target=_read_stdout,
                args=(process.stdout, stdout_queue),
                daemon=True,
            )
            stderr_thread = Thread(
                target=_read_stderr,
                args=(process.stderr, stderr_lines),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()

            process.stdin.write(json.dumps(events, ensure_ascii=False))
            process.stdin.close()

            result_count = 0
            while True:
                try:
                    line = stdout_queue.get(timeout=self._timeout_seconds)
                except Empty as exc:
                    raise CaptionWorkerError(
                        "Caption-Worker lieferte seit "
                        f"{self._timeout_seconds}s kein Ergebnis."
                    ) from exc

                if line is None:
                    break
                if not line.strip():
                    continue

                try:
                    result = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise CaptionWorkerError(
                        "Caption-Worker lieferte ungueltiges JSONL."
                    ) from exc
                if not isinstance(result, dict):
                    raise CaptionWorkerError(
                        "Eine Caption-Worker-Ausgabe muss ein JSON-Objekt sein."
                    )

                result_count += 1
                yield result

            return_code = process.wait()
            stderr_thread.join(timeout=1)
            if return_code != 0:
                detail = "\n".join(stderr_lines).strip() or "keine Fehlermeldung"
                raise CaptionWorkerError(
                    f"Caption-Worker Exit-Code {return_code}: {detail}"
                )

            logger.info("Caption-Worker beendet: ergebnisse=%d", result_count)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


def _read_stdout(stream, queue: Queue[str | None]) -> None:
    try:
        for line in stream:
            queue.put(line)
    finally:
        queue.put(None)


def _read_stderr(stream, lines: list[str]) -> None:
    for raw_line in stream:
        line = raw_line.rstrip()
        if line:
            lines.append(line)
            logger.info("Caption-Worker: %s", line)
