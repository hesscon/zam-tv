import json
import importlib.util
from io import StringIO
from pathlib import Path
from unittest import TestCase


MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "services" / "event_caption_worker.py"
MODULE_SPEC = importlib.util.spec_from_file_location("event_caption_worker", MODULE_PATH)
event_caption_worker = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC and MODULE_SPEC.loader
MODULE_SPEC.loader.exec_module(event_caption_worker)


class FakeModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def create_chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return {"choices": [{"message": {"content": response}}]}


class EventCaptionWorkerTest(TestCase):
    def test_generates_one_result_per_event(self) -> None:
        model = FakeModel(
            [
                '{"caption":"Kurze Vorträge zu vielfältigen Themen"}',
                '{"caption":"Gemeinsam defekte Geräte reparieren"}',
            ]
        )
        events = [
            {
                "uid": "event-1",
                "title": "Pecha-Kucha-Nacht",
                "description": "Mehrere kurze Vorträge behandeln verschiedene Themen.",
            },
            {
                "uid": "event-2",
                "title": "Repair-Café",
                "description": "Wir reparieren gemeinsam mitgebrachte Geräte.",
            },
        ]

        results = event_caption_worker.generate_captions(
            events,
            model,
            log_stream=StringIO(),
        )

        self.assertEqual(
            [
                {"uid": "event-1", "caption": "Kurze Vorträge zu vielfältigen Themen"},
                {"uid": "event-2", "caption": "Gemeinsam defekte Geräte reparieren"},
            ],
            results,
        )
        self.assertEqual(2, len(model.calls))

    def test_empty_description_does_not_call_model(self) -> None:
        model = FakeModel([])

        results = event_caption_worker.generate_captions(
            [{"uid": "event-1", "title": "Unklarer Termin", "description": ""}],
            model,
            log_stream=StringIO(),
        )

        self.assertEqual([{"uid": "event-1", "caption": ""}], results)
        self.assertEqual([], model.calls)

    def test_failure_of_one_event_does_not_abort_batch(self) -> None:
        model = FakeModel(
            [
                RuntimeError("Modellfehler"),
                '{"caption":"Musik und spontane Auftritte"}',
            ]
        )
        events = [
            {"uid": "event-1", "title": "Erstes Event", "description": "Inhalt eins"},
            {"uid": "event-2", "title": "Offene Bühne", "description": "Musik und Auftritte"},
        ]

        results = event_caption_worker.generate_captions(
            events,
            model,
            log_stream=StringIO(),
        )

        self.assertEqual("", results[0]["caption"])
        self.assertEqual("Modellfehler", results[0]["error"])
        self.assertEqual(
            {"uid": "event-2", "caption": "Musik und spontane Auftritte"},
            results[1],
        )

    def test_prompt_examples_contain_valid_caption_json(self) -> None:
        assistant_messages = [
            message
            for message in event_caption_worker.EXAMPLE_MESSAGES
            if message["role"] == "assistant"
        ]

        for message in assistant_messages:
            self.assertIsInstance(json.loads(message["content"])["caption"], str)

    def test_requests_caption_json_schema_from_model(self) -> None:
        model = FakeModel(['{"caption":"Kreative Projekte gemeinsam entwickeln"}'])

        event_caption_worker.generate_captions(
            [{"uid": "event-1", "title": "Werkstatt", "description": "Projekte entwickeln"}],
            model,
            log_stream=StringIO(),
        )

        self.assertEqual(
            event_caption_worker.CAPTION_RESPONSE_FORMAT,
            model.calls[0]["response_format"],
        )
        actual_user_message = model.calls[0]["messages"][-1]["content"]
        self.assertEqual(
            {
                "title": "Werkstatt",
                "description": "Projekte entwickeln",
            },
            json.loads(actual_user_message),
        )

    def test_rejects_caption_that_only_repeats_title(self) -> None:
        with self.assertRaisesRegex(ValueError, "Veranstaltungstitel"):
            event_caption_worker._validate_caption("Offene Bühne", "Offene Bühne")

    def test_accepts_caption_with_nine_words(self) -> None:
        event_caption_worker._validate_caption(
            "Computer klemmt? Wir entwirren Kabel, Klicks und alle Fragezeichen.",
            "Computersprechstunde",
        )

    def test_rejects_caption_with_ten_words(self) -> None:
        with self.assertRaisesRegex(ValueError, "3 bis 9"):
            event_caption_worker._validate_caption(
                "Computer klemmt? Wir entwirren Kabel, Klicks und wirklich alle Fragezeichen.",
                "Computersprechstunde",
            )

    def test_rejects_non_array_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "JSON-Array"):
            event_caption_worker.read_events(StringIO('{"uid": "event-1"}'))
