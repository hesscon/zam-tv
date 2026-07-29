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
                '{"caption":"Vielfältige Themen in kurzen Vorträgen"}',
                '{"caption":"Gemeinsam defekte Geräte reparieren"}',
                '{"caption":"Defekte Alltagsgeräte gemeinsam reparieren"}',
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
                {"uid": "event-1", "caption": "Vielfältige Themen in kurzen Vorträgen"},
                {"uid": "event-2", "caption": "Defekte Alltagsgeräte gemeinsam reparieren"},
            ],
            results,
        )
        self.assertEqual(4, len(model.calls))

    def test_empty_description_does_not_call_model(self) -> None:
        model = FakeModel([])

        results = event_caption_worker.generate_captions(
            [{"uid": "event-1", "title": "Unklarer Termin", "description": ""}],
            model,
            log_stream=StringIO(),
        )

        self.assertEqual([{"uid": "event-1", "caption": ""}], results)
        self.assertEqual([], model.calls)

    def test_single_shot_skips_improvement_round(self) -> None:
        model = FakeModel(
            ['{"caption":"Gemeinsam defekte Geräte reparieren"}']
        )

        results = event_caption_worker.generate_captions(
            [
                {
                    "uid": "event-1",
                    "title": "Repair-Café",
                    "description": "Wir reparieren gemeinsam mitgebrachte Geräte.",
                }
            ],
            model,
            improve=False,
            log_stream=StringIO(),
        )

        self.assertEqual(
            [{"uid": "event-1", "caption": "Gemeinsam defekte Geräte reparieren"}],
            results,
        )
        self.assertEqual(1, len(model.calls))

    def test_parser_accepts_single_shot_option(self) -> None:
        args = event_caption_worker.build_argument_parser().parse_args(
            ["--model", "model.gguf", "--single-shot"]
        )

        self.assertTrue(args.single_shot)

    def test_failure_of_one_event_does_not_abort_batch(self) -> None:
        model = FakeModel(
            [
                RuntimeError("Modellfehler"),
                '{"caption":"Musik und spontane Auftritte"}',
                '{"caption":"Musik, Texte und spontane Auftritte"}',
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
            {"uid": "event-2", "caption": "Musik, Texte und spontane Auftritte"},
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

    def test_both_system_prompts_use_the_same_rules(self) -> None:
        self.assertIn(
            event_caption_worker.CAPTION_RULES,
            event_caption_worker.GENERATION_SYSTEM_PROMPT,
        )
        self.assertIn(
            event_caption_worker.CAPTION_RULES,
            event_caption_worker.IMPROVEMENT_SYSTEM_PROMPT,
        )
        self.assertNotEqual(
            event_caption_worker.GENERATION_SYSTEM_PROMPT,
            event_caption_worker.IMPROVEMENT_SYSTEM_PROMPT,
        )

    def test_requests_caption_json_schema_from_model(self) -> None:
        model = FakeModel(
            [
                '{"caption":"Kreative Projekte gemeinsam entwickeln"}',
                '{"caption":"Gemeinsam kreative Projekte entwickeln"}',
            ]
        )

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
        improved_user_message = model.calls[1]["messages"][-1]["content"]
        self.assertEqual(
            {
                "title": "Werkstatt",
                "description": "Projekte entwickeln",
                "caption": "Kreative Projekte gemeinsam entwickeln",
            },
            json.loads(improved_user_message),
        )
        self.assertEqual(
            ["system", "user"],
            [message["role"] for message in model.calls[1]["messages"]],
        )
        self.assertEqual(
            event_caption_worker.GENERATION_SYSTEM_PROMPT,
            model.calls[0]["messages"][0]["content"],
        )
        self.assertEqual(
            event_caption_worker.IMPROVEMENT_SYSTEM_PROMPT,
            model.calls[1]["messages"][0]["content"],
        )

    def test_second_round_can_repair_invalid_first_caption(self) -> None:
        model = FakeModel(
            [
                '{"caption":"Geräte reparieren"}',
                '{"caption":"Gemeinsam defekte Geräte reparieren"}',
            ]
        )

        results = event_caption_worker.generate_captions(
            [
                {
                    "uid": "event-1",
                    "title": "Repair-Café",
                    "description": "Wir reparieren gemeinsam mitgebrachte Geräte.",
                }
            ],
            model,
            log_stream=StringIO(),
        )

        self.assertEqual(
            [{"uid": "event-1", "caption": "Gemeinsam defekte Geräte reparieren"}],
            results,
        )

    def test_invalid_improvement_falls_back_to_valid_first_caption(self) -> None:
        model = FakeModel(
            [
                '{"caption":"Gemeinsam defekte Geräte reparieren"}',
                '{"caption":"Wir reparieren heute gemeinsam alle mitgebrachten defekten Geräte im Café"}',
            ]
        )

        results = event_caption_worker.generate_captions(
            [
                {
                    "uid": "event-1",
                    "title": "Repair-Café",
                    "description": "Wir reparieren gemeinsam mitgebrachte Geräte.",
                }
            ],
            model,
            log_stream=StringIO(),
        )

        self.assertEqual(
            [{"uid": "event-1", "caption": "Gemeinsam defekte Geräte reparieren"}],
            results,
        )

    def test_failed_improvement_falls_back_to_valid_first_caption(self) -> None:
        model = FakeModel(
            [
                '{"caption":"Gemeinsam defekte Geräte reparieren"}',
                RuntimeError("Verbesserung fehlgeschlagen"),
            ]
        )

        results = event_caption_worker.generate_captions(
            [
                {
                    "uid": "event-1",
                    "title": "Repair-Café",
                    "description": "Wir reparieren gemeinsam mitgebrachte Geräte.",
                }
            ],
            model,
            log_stream=StringIO(),
        )

        self.assertEqual(
            [{"uid": "event-1", "caption": "Gemeinsam defekte Geräte reparieren"}],
            results,
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
