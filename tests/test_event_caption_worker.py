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
    def test_argument_parser_accepts_classify_only(self) -> None:
        args = event_caption_worker.build_argument_parser().parse_args(
            ["--model", "model.gguf", "--classify-only"]
        )

        self.assertTrue(args.classify_only)

    def test_classify_only_returns_title_decision_without_caption_call(self) -> None:
        model = FakeModel(['{"activity":"generic","term":"common"}'])

        results = event_caption_worker.classify_events(
            [{"uid": "event-1", "title": "Tag des Lichts"}],
            model,
            log_stream=StringIO(),
        )

        self.assertEqual(
            [
                {
                    "uid": "event-1",
                    "title": "Tag des Lichts",
                    "activity": "generic",
                    "term": "common",
                    "needs_caption": True,
                }
            ],
            results,
        )
        self.assertEqual(1, len(model.calls))
        self.assertEqual(
            {"title": "Tag des Lichts"},
            json.loads(model.calls[0]["messages"][-1]["content"]),
        )
        self.assertEqual(
            event_caption_worker.CLASSIFICATION_RESPONSE_FORMAT,
            model.calls[0]["response_format"],
        )

    def test_classify_only_applies_combined_enum_threshold(self) -> None:
        model = FakeModel(['{"activity":"generic","term":"context_specific"}'])

        results = event_caption_worker.classify_events(
            [{"uid": "event-1", "title": "Offenes Lab-Treffen"}],
            model,
            log_stream=StringIO(),
        )

        self.assertTrue(results[0]["needs_caption"])

    def test_generates_one_result_per_event(self) -> None:
        model = FakeModel(
            [
                '{"activity":"missing","term":"common"}',
                '{"caption":"Kurze Vorträge zu vielfältigen Themen"}',
                '{"activity":"missing","term":"common"}',
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
        self.assertEqual(4, len(model.calls))

    def test_writes_each_completed_result_as_jsonl(self) -> None:
        model = FakeModel([])
        result_stream = StringIO()

        event_caption_worker.generate_captions(
            [
                {"uid": "event-1", "title": "Eins", "description": ""},
                {"uid": "event-2", "title": "Zwei", "description": ""},
            ],
            model,
            log_stream=StringIO(),
            result_stream=result_stream,
        )

        self.assertEqual(
            [
                {"uid": "event-1", "caption": ""},
                {"uid": "event-2", "caption": ""},
            ],
            [
                json.loads(line)
                for line in result_stream.getvalue().splitlines()
            ],
        )

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
                '{"activity":"missing","term":"common"}',
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

    def test_prompt_examples_contain_valid_json(self) -> None:
        classification_messages = [
            message
            for message in event_caption_worker.CLASSIFICATION_EXAMPLE_MESSAGES
            if message["role"] == "assistant"
        ]
        classification_payloads = [
            json.loads(message["content"]) for message in classification_messages
        ]
        self.assertTrue(
            all(
                payload["activity"] in event_caption_worker.ACTIVITY_VALUES
                and payload["term"] in event_caption_worker.TERM_VALUES
                for payload in classification_payloads
            )
        )
        self.assertTrue(
            any(
                payload["activity"] == "explicit" and payload["term"] == "common"
                for payload in classification_payloads
            )
        )
        self.assertTrue(
            any(
                payload["activity"] != "explicit" or payload["term"] != "common"
                for payload in classification_payloads
            )
        )

        caption_messages = [
            message
            for message in event_caption_worker.CAPTION_EXAMPLE_MESSAGES
            if message["role"] == "assistant"
        ]
        caption_payloads = [json.loads(message["content"]) for message in caption_messages]
        self.assertTrue(
            all(isinstance(payload["caption"], str) for payload in caption_payloads)
        )
        self.assertTrue(any(not payload["caption"] for payload in caption_payloads))
        self.assertTrue(any(payload["caption"] for payload in caption_payloads))

    def test_prompt_examples_do_not_overlap_holdout_titles(self) -> None:
        fixture_path = Path(__file__).parent / "fixtures" / "event-caption-events.json"
        holdout_titles = [
            event["title"].strip().casefold()
            for event in json.loads(fixture_path.read_text(encoding="utf-8"))
        ]
        example_titles = [
            json.loads(message["content"])["title"].strip().casefold()
            for messages in (
                event_caption_worker.CLASSIFICATION_EXAMPLE_MESSAGES,
                event_caption_worker.CAPTION_EXAMPLE_MESSAGES,
            )
            for message in messages
            if message["role"] == "user"
        ]

        for example_title in example_titles:
            for holdout_title in holdout_titles:
                self.assertNotIn(example_title, holdout_title)
                self.assertNotIn(holdout_title, example_title)

    def test_expected_classifications_match_holdout_fixture(self) -> None:
        fixture_dir = Path(__file__).parent / "fixtures"
        events = json.loads(
            (fixture_dir / "event-caption-events.json").read_text(encoding="utf-8")
        )
        expected = json.loads(
            (
                fixture_dir / "event-caption-expected-classifications.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            [event["title"] for event in events],
            [classification["title"] for classification in expected],
        )
        for classification in expected:
            self.assertIn(
                classification["activity"], event_caption_worker.ACTIVITY_VALUES
            )
            self.assertIn(classification["term"], event_caption_worker.TERM_VALUES)
            self.assertEqual(
                event_caption_worker.ACTIVITY_SCORES[classification["activity"]]
                + event_caption_worker.TERM_SCORES[classification["term"]]
                >= 2,
                classification["needs_caption"],
            )

    def test_requests_caption_json_schema_from_model(self) -> None:
        model = FakeModel(
            [
                '{"activity":"missing","term":"common"}',
                '{"caption":"Kreative Projekte gemeinsam entwickeln"}',
            ]
        )

        event_caption_worker.generate_captions(
            [{"uid": "event-1", "title": "Werkstatt", "description": "Projekte entwickeln"}],
            model,
            log_stream=StringIO(),
        )

        self.assertEqual(
            event_caption_worker.CLASSIFICATION_RESPONSE_FORMAT,
            model.calls[0]["response_format"],
        )
        classification_user_message = model.calls[0]["messages"][-1]["content"]
        self.assertEqual(
            {"title": "Werkstatt"},
            json.loads(classification_user_message),
        )

        self.assertEqual(
            event_caption_worker.CAPTION_RESPONSE_FORMAT,
            model.calls[1]["response_format"],
        )
        actual_user_message = model.calls[1]["messages"][-1]["content"]
        self.assertEqual(
            {
                "title": "Werkstatt",
                "description": "Projekte entwickeln",
            },
            json.loads(actual_user_message),
        )

    def test_returns_empty_caption_when_model_marks_title_as_sufficient(self) -> None:
        model = FakeModel(['{"activity":"explicit","term":"common"}'])

        results = event_caption_worker.generate_captions(
            [
                {
                    "uid": "event-1",
                    "title": "Arztbriefe erklärt",
                    "description": "Arztbriefe werden verständlich erklärt.",
                }
            ],
            model,
            log_stream=StringIO(),
        )

        self.assertEqual([{"uid": "event-1", "caption": ""}], results)
        self.assertEqual(1, len(model.calls))

    def test_generates_caption_when_terms_are_unclear(self) -> None:
        model = FakeModel(
            [
                '{"activity":"explicit","term":"unfamiliar"}',
                '{"caption":"Ein Daumenklavier aus Holz bauen"}',
            ]
        )

        results = event_caption_worker.generate_captions(
            [
                {
                    "uid": "event-1",
                    "title": "Kalimba-Werkstatt",
                    "description": "Ein Daumenklavier wird aus Holz gebaut.",
                }
            ],
            model,
            log_stream=StringIO(),
        )

        self.assertEqual(
            [{"uid": "event-1", "caption": "Ein Daumenklavier aus Holz bauen"}],
            results,
        )
        self.assertEqual(2, len(model.calls))

    def test_accepts_empty_caption_after_positive_decision(self) -> None:
        model = FakeModel(
            ['{"activity":"missing","term":"common"}', '{"caption":""}']
        )

        results = event_caption_worker.generate_captions(
            [
                {
                    "uid": "event-1",
                    "title": "Katzentag",
                    "description": "Katzen werden gestaltet.",
                }
            ],
            model,
            log_stream=StringIO(),
        )

        self.assertEqual([{"uid": "event-1", "caption": ""}], results)

    def test_rejects_caption_that_only_repeats_title(self) -> None:
        with self.assertRaisesRegex(ValueError, "Veranstaltungstitel"):
            event_caption_worker._validate_caption("Offene Bühne", "Offene Bühne")

    def test_accepts_caption_with_eight_words(self) -> None:
        event_caption_worker._validate_caption(
            "Wir entwirren Kabel, Klicks und alle digitalen Fragezeichen.",
            "Computersprechstunde",
        )

    def test_rejects_caption_with_nine_words(self) -> None:
        with self.assertRaisesRegex(ValueError, "3 bis 8"):
            event_caption_worker._validate_caption(
                "Wir entwirren Kabel, Klicks und wirklich alle digitalen Fragezeichen.",
                "Computersprechstunde",
            )

    def test_rejects_non_array_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "JSON-Array"):
            event_caption_worker.read_events(StringIO('{"uid": "event-1"}'))
