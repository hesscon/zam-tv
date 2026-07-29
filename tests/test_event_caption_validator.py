import importlib.util
from io import StringIO
import json
from pathlib import Path
from unittest import TestCase


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "event_caption_validator.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location("event_caption_validator", MODULE_PATH)
event_caption_validator = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC and MODULE_SPEC.loader
MODULE_SPEC.loader.exec_module(event_caption_validator)


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


class EventCaptionValidatorTest(TestCase):
    def test_returns_one_result_per_candidate(self) -> None:
        model = FakeModel(
            [
                '{"approved":true,"reason":""}',
                (
                    '{"approved":false,'
                    '"reason":"Die Aussage ist nicht durch die Beschreibung belegt."}'
                ),
            ]
        )
        candidates = [
            {
                "uid": "event-1",
                "title": "Repair-Café",
                "description": "Gemeinsam werden defekte Geräte repariert.",
                "caption": "Gemeinsam defekte Geräte reparieren",
            },
            {
                "uid": "event-2",
                "title": "Suppentag",
                "description": "Menschen essen gemeinsam Suppe.",
                "caption": "Suppe, Gemeinschaft und Wärme",
            },
        ]

        results = event_caption_validator.validate_captions(
            candidates,
            model,
            log_stream=StringIO(),
        )

        self.assertEqual(
            [
                {"uid": "event-1", "approved": True, "reason": ""},
                {
                    "uid": "event-2",
                    "approved": False,
                    "reason": "Die Aussage ist nicht durch die Beschreibung belegt.",
                },
            ],
            results,
        )
        self.assertEqual(2, len(model.calls))

    def test_empty_caption_does_not_call_model(self) -> None:
        model = FakeModel([])

        results = event_caption_validator.validate_captions(
            [
                {
                    "uid": "event-1",
                    "title": "Unklarer Termin",
                    "description": "Eine Veranstaltung.",
                    "caption": "",
                }
            ],
            model,
            log_stream=StringIO(),
        )

        self.assertEqual(
            [
                {
                    "uid": "event-1",
                    "approved": False,
                    "reason": "Die Caption ist leer.",
                }
            ],
            results,
        )
        self.assertEqual([], model.calls)

    def test_failure_of_one_candidate_does_not_abort_batch(self) -> None:
        model = FakeModel(
            [
                RuntimeError("Modellfehler"),
                '{"approved":true,"reason":""}',
            ]
        )
        candidates = [
            {
                "uid": "event-1",
                "title": "Erstes Event",
                "description": "Inhalt eins.",
                "caption": "Erster kurzer Inhalt",
            },
            {
                "uid": "event-2",
                "title": "Offene Bühne",
                "description": "Musik und Auftritte.",
                "caption": "Musik und spontane Auftritte",
            },
        ]

        results = event_caption_validator.validate_captions(
            candidates,
            model,
            log_stream=StringIO(),
        )

        self.assertFalse(results[0]["approved"])
        self.assertEqual("Modellfehler", results[0]["error"])
        self.assertEqual(
            {"uid": "event-2", "approved": True, "reason": ""},
            results[1],
        )

    def test_requests_validation_json_schema_and_sends_candidate_json(self) -> None:
        model = FakeModel(['{"approved":true,"reason":""}'])

        event_caption_validator.validate_captions(
            [
                {
                    "uid": "event-1",
                    "title": "Werkstatt",
                    "description": "Projekte gemeinsam entwickeln.",
                    "caption": "Gemeinsam kreative Projekte entwickeln",
                }
            ],
            model,
            log_stream=StringIO(),
        )

        self.assertEqual(
            event_caption_validator.VALIDATION_RESPONSE_FORMAT,
            model.calls[0]["response_format"],
        )
        self.assertEqual(
            {
                "title": "Werkstatt",
                "description": "Projekte gemeinsam entwickeln.",
                "caption": "Gemeinsam kreative Projekte entwickeln",
            },
            json.loads(model.calls[0]["messages"][-1]["content"]),
        )

    def test_rejects_declined_response_without_reason(self) -> None:
        model = FakeModel(['{"approved":false,"reason":""}'])

        results = event_caption_validator.validate_captions(
            [
                {
                    "uid": "event-1",
                    "title": "Werkstatt",
                    "description": "Projekte gemeinsam entwickeln.",
                    "caption": "Gemeinsam kreative Projekte entwickeln",
                }
            ],
            model,
            log_stream=StringIO(),
        )

        self.assertFalse(results[0]["approved"])
        self.assertIn("Begründung", results[0]["error"])

    def test_rejects_non_array_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "JSON-Array"):
            event_caption_validator.read_candidates(StringIO('{"uid": "event-1"}'))
