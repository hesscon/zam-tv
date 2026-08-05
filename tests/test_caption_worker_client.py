import json
from pathlib import Path
import subprocess
from unittest import TestCase
from unittest.mock import patch

from app.services.caption_worker_client import CaptionWorkerClient, CaptionWorkerError


EVENTS = [
    {
        "uid": "request-1",
        "title": "Funkenflug",
        "description": "Langzeitfotos mit Wunderkerzen.",
    }
]


class CaptionWorkerClientTest(TestCase):
    def setUp(self) -> None:
        self.client = CaptionWorkerClient(
            Path("/models/test.gguf"),
            threads=3,
            timeout_seconds=42,
        )

    def test_runs_worker_once_with_json_batch(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='[{"uid":"request-1","caption":"Leuchtende Fotos aufnehmen"}]',
            stderr="Modell geladen: 1.0s\n",
        )

        with patch(
            "app.services.caption_worker_client.subprocess.run",
            return_value=completed,
        ) as run_mock:
            results = self.client.generate(EVENTS)

        command = run_mock.call_args.args[0]
        self.assertEqual("app.services.event_caption_worker", command[2])
        self.assertIn("/models/test.gguf", command)
        self.assertIn("3", command)
        self.assertEqual(EVENTS, json.loads(run_mock.call_args.kwargs["input"]))
        self.assertEqual(
            Path(__file__).resolve().parents[1],
            run_mock.call_args.kwargs["cwd"],
        )
        self.assertEqual(42, run_mock.call_args.kwargs["timeout"])
        self.assertEqual("Leuchtende Fotos aufnehmen", results[0]["caption"])

    def test_empty_batch_does_not_start_worker(self) -> None:
        with patch(
            "app.services.caption_worker_client.subprocess.run"
        ) as run_mock:
            self.assertEqual([], self.client.generate([]))

        run_mock.assert_not_called()

    def test_nonzero_exit_code_raises_worker_error(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="Modelldatei nicht gefunden",
        )

        with patch(
            "app.services.caption_worker_client.subprocess.run",
            return_value=completed,
        ):
            with self.assertRaisesRegex(
                CaptionWorkerError,
                "Modelldatei nicht gefunden",
            ):
                self.client.generate(EVENTS)

    def test_invalid_json_raises_worker_error(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="kein JSON",
            stderr="",
        )

        with patch(
            "app.services.caption_worker_client.subprocess.run",
            return_value=completed,
        ):
            with self.assertRaisesRegex(CaptionWorkerError, "ungueltiges JSON"):
                self.client.generate(EVENTS)

    def test_timeout_raises_worker_error(self) -> None:
        with patch(
            "app.services.caption_worker_client.subprocess.run",
            side_effect=subprocess.TimeoutExpired(["python"], 42),
        ):
            with self.assertRaisesRegex(CaptionWorkerError, "Timeout nach 42s"):
                self.client.generate(EVENTS)
