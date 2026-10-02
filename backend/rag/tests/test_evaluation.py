import unittest

from rag.evaluation.evaluate import _answer_metrics


class AnswerEvaluationMetricTests(unittest.TestCase):
    def test_wrong_page_is_incorrect_even_when_facts_and_grounding_pass(self):
        results = [
            {
                "answer": "The objective is long-term growth.",
                "answer_facts_match": True,
                "citation_page_match": True,
                "citation_present": True,
                "grounding_pass": True,
                "confidence": 0.9,
            },
            {
                "answer": "The objective is long-term growth.",
                "answer_facts_match": True,
                "citation_page_match": False,
                "citation_present": True,
                "grounding_pass": True,
                "confidence": 0.99,
            },
            {
                "answer": "I could not find sufficient evidence.",
                "answer_facts_match": False,
                "citation_page_match": False,
                "citation_present": False,
                "grounding_pass": False,
                "confidence": 0.2,
            },
        ]

        metrics = _answer_metrics(results)

        self.assertEqual(metrics["answer_grounded_accuracy"], 0.3333)
        self.assertEqual(metrics["confidence_brier_score"], 0.3434)
        self.assertEqual(metrics["high_confidence_error_rate_at_80"], 0.5)
        self.assertEqual(metrics["mean_confidence_on_incorrect_answers"], 0.595)
        self.assertEqual(metrics["overconfident_answer_count_at_80"], 1)

    def test_answer_metrics_are_unavailable_in_retrieval_only_runs(self):
        metrics = _answer_metrics(
            [{"answer": None, "confidence": None}]
        )

        self.assertIsNone(metrics["answer_grounded_accuracy"])
        self.assertIsNone(metrics["confidence_brier_score"])
        self.assertEqual(metrics["answered_questions"], 0)


if __name__ == "__main__":
    unittest.main()
