import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.llm import generate_response
from app.usage import UsageTracker


class UsageTrackingTests(unittest.TestCase):
    def test_generate_response_records_answer_model_calls_and_tokens(self):
        model = SimpleNamespace(
            model="gemma4:31b",
            invoke=lambda prompt: SimpleNamespace(
                content='{"answer":"Grounded answer. [SOURCE 1]","confidence":0.7}',
                usage_metadata={"input_tokens": 120, "output_tokens": 24},
            ),
        )
        tracker = UsageTracker()

        response = generate_response("question", llm=model, usage_tracker=tracker)

        self.assertEqual(response.answer, "Grounded answer. [SOURCE 1]")
        self.assertEqual(
            tracker.snapshot(),
            [
                {
                    "role": "answer",
                    "model": "gemma4:31b",
                    "requests": 1,
                    "input_tokens": 120,
                    "output_tokens": 24,
                    "input_reports": 1,
                    "output_reports": 1,
                }
            ],
        )

    def test_failed_provider_call_still_counts_as_an_api_attempt(self):
        def fail(prompt):
            raise RuntimeError("provider unavailable")

        tracker = UsageTracker()
        model = SimpleNamespace(model="answer-model", invoke=fail)

        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            generate_response("question", llm=model, usage_tracker=tracker)

        self.assertEqual(tracker.snapshot()[0]["requests"], 1)
        self.assertEqual(tracker.snapshot()[0]["input_reports"], 0)

    def test_cost_uses_explicit_rates_and_is_not_guessed(self):
        tracker = UsageTracker()
        tracker.record_request("answer", "text-model")
        tracker.record_usage(
            "answer",
            "text-model",
            input_tokens=1_000_000,
            output_tokens=500_000,
        )

        with patch.dict(
            os.environ,
            {
                "OLLAMA_TEXT_INPUT_USD_PER_1M_TOKENS": "0.2",
                "OLLAMA_TEXT_OUTPUT_USD_PER_1M_TOKENS": "0.6",
            },
        ):
            row = UsageTracker.display_rows(tracker.snapshot())[0]

        self.assertEqual(row["Estimated cost (USD)"], "$0.50000000")

        with patch.dict(
            os.environ,
            {
                "OLLAMA_TEXT_INPUT_USD_PER_1M_TOKENS": "",
                "OLLAMA_TEXT_OUTPUT_USD_PER_1M_TOKENS": "",
            },
        ):
            row = UsageTracker.display_rows(tracker.snapshot())[0]
        self.assertEqual(row["Estimated cost (USD)"], "Rates not configured")

    def test_session_merge_adds_counts_per_model_without_crossing_roles(self):
        existing = [
            {
                "role": "answer",
                "model": "shared-model",
                "requests": 1,
                "input_tokens": 10,
                "output_tokens": 5,
                "input_reports": 1,
                "output_reports": 1,
            }
        ]
        incoming = [
            {
                "role": "answer",
                "model": "shared-model",
                "requests": 1,
                "input_tokens": 20,
                "output_tokens": 7,
                "input_reports": 1,
                "output_reports": 1,
            },
            {
                "role": "vision",
                "model": "shared-model",
                "requests": 1,
                "input_tokens": 30,
                "output_tokens": 8,
                "input_reports": 1,
                "output_reports": 1,
            },
        ]

        merged = UsageTracker.merge_snapshots(existing, incoming)

        self.assertEqual(len(merged), 2)
        answer = next(record for record in merged if record["role"] == "answer")
        self.assertEqual(answer["requests"], 2)
        self.assertEqual(answer["input_tokens"], 30)


if __name__ == "__main__":
    unittest.main()
