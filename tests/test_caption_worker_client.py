import json
from io import StringIO
from pathlib import Path
import time
from unittest import TestCase
from unittest.mock import Mock, patch

from app.services.caption_worker_client import CaptionWorkerClient, CaptionWorkerError


EVENTS = [
    {
        "uid": "request-1",
        "title": "Funkenflug",
        "description": "Langzeitfotos mit Wunderkerzen.",
    }
]


def _process(stdout: str, *, stderr: str = "", return_code: int = 0) -> Mock:
    process = Mock()
    process.stdin = Mock()
    process.stdout = StringIO(stdout)
    process.stderr = StringIO(stderr)
    process.wait.return_value = return_code
    process.poll.return_value = return_code
    return process


class CaptionWorkerClientTest(TestCase):
    def setUp(self) -> None:
        self.client = CaptionWorkerClient(
            Path("/models/test.gguf"),
            threads=3,
            timeout_seconds=42,
            nice_level=7,
        )

    def test_streams_jsonl_results_from_one_worker(self) -> None:
        process = _process(
            '{"uid":"request-1","caption":"Leuchtende Fotos aufnehmen"}\n',
            stderr="Modell geladen: 1.0s\n",
        )

        with patch(
            "app.services.caption_worker_client.subprocess.Popen",
            return_value=process,
        ) as popen_mock:
            results = list(self.client.generate(EVENTS))

        command = popen_mock.call_args.args[0]
        self.assertEqual(
            ["nice", "-n", "7"],
            command[:3],
        )
        self.assertEqual("app.services.event_caption_worker", command[5])
        self.assertIn("/models/test.gguf", command)
        self.assertIn("3", command)
        self.assertEqual(
            EVENTS,
            json.loads(process.stdin.write.call_args.args[0]),
        )
        process.stdin.close.assert_called_once_with()
        self.assertEqual(
            Path(__file__).resolve().parents[1],
            popen_mock.call_args.kwargs["cwd"],
        )
        self.assertEqual("Leuchtende Fotos aufnehmen", results[0]["caption"])

    def test_empty_batch_does_not_start_worker(self) -> None:
        with patch(
            "app.services.caption_worker_client.subprocess.Popen"
        ) as popen_mock:
            self.assertEqual([], list(self.client.generate([])))

        popen_mock.assert_not_called()

    def test_nonzero_exit_code_raises_worker_error(self) -> None:
        process = _process(
            "",
            stderr="Modelldatei nicht gefunden\n",
            return_code=1,
        )

        with patch(
            "app.services.caption_worker_client.subprocess.Popen",
            return_value=process,
        ):
            with self.assertRaisesRegex(
                CaptionWorkerError,
                "Modelldatei nicht gefunden",
            ):
                list(self.client.generate(EVENTS))

    def test_invalid_jsonl_raises_worker_error(self) -> None:
        process = _process("kein JSON\n")

        with patch(
            "app.services.caption_worker_client.subprocess.Popen",
            return_value=process,
        ):
            with self.assertRaisesRegex(CaptionWorkerError, "ungueltiges JSONL"):
                list(self.client.generate(EVENTS))

    def test_timeout_without_next_result_raises_worker_error(self) -> None:
        class SlowStream:
            def __iter__(self):
                time.sleep(0.05)
                return iter(())

        process = _process("")
        process.stdout = SlowStream()
        process.poll.side_effect = [None, 0]
        client = CaptionWorkerClient(
            Path("/models/test.gguf"),
            timeout_seconds=0.01,
        )

        with patch(
            "app.services.caption_worker_client.subprocess.Popen",
            return_value=process,
        ):
            with self.assertRaisesRegex(
                CaptionWorkerError,
                "seit 0.01s kein Ergebnis",
            ):
                list(client.generate(EVENTS))

        process.kill.assert_called_once_with()

    def test_rejects_invalid_nice_level(self) -> None:
        with self.assertRaisesRegex(ValueError, "zwischen 0 und 19"):
            CaptionWorkerClient(
                Path("/models/test.gguf"),
                nice_level=20,
            )
