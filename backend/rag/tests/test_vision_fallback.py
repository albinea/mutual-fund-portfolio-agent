import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fundlens_rag.app.vision_fallback import (
    _get_ollama_cloud_client,
    extract_visual_evidence,
    should_use_visual_fallback,
)
from fundlens_rag.app.usage import UsageTracker
from fundlens_rag.rag.grounding import GroundingError


class VisionFallbackGateTests(unittest.TestCase):
    def test_does_not_use_vision_for_a_confident_normal_answer(self):
        self.assertFalse(
            should_use_visual_fallback(
                answer="The fund reports the stated value. [SOURCE 1]",
                confidence=0.8,
            )
        )

    def test_uses_vision_for_an_abstention_or_grounding_failure(self):
        self.assertTrue(
            should_use_visual_fallback(
                answer="I could not find sufficient evidence.",
                confidence=0.9,
            )
        )
        self.assertTrue(
            should_use_visual_fallback(
                answer="An answer without valid citation.",
                confidence=0.9,
                grounding_error=GroundingError("invalid source"),
            )
        )

    def test_uses_vision_for_low_confidence(self):
        self.assertTrue(
            should_use_visual_fallback(
                answer="A tentative answer. [SOURCE 1]",
                confidence=0.2,
            )
        )


class OllamaVisionFallbackTests(unittest.TestCase):
    QUESTION = (
        "What was the market value on August 31, 2026 for the 1-year SIP "
        "of HDFC Medium to Long Term Fund?"
    )

    @staticmethod
    def _chunk(pdf_path: Path, page: int = 87) -> dict:
        return {
            "text": "Page has SIP performance information but the cell is unreadable.",
            "document": pdf_path.name,
            "page": page,
            "source_url": pdf_path.resolve().as_uri(),
            "score": 0.81,
        }

    @staticmethod
    def _response(
        *,
        found: bool,
        subject: str,
        heading: str,
        evidence: str,
        prompt_eval_count: int | None = None,
        eval_count: int | None = None,
    ):
        content = json.dumps(
            {
                "found_evidence": found,
                "page_subject": subject,
                "section_or_table": heading,
                "evidence": evidence,
            }
        )
        return SimpleNamespace(
            message=SimpleNamespace(content=content),
            prompt_eval_count=prompt_eval_count,
            eval_count=eval_count,
        )

    def test_returns_visual_text_with_original_pdf_citation_metadata(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf") as temporary_pdf:
            pdf_path = Path(temporary_pdf.name).resolve()
            page_evidence = self._response(
                found=True,
                subject="HDFC Medium to Long Term Fund",
                heading="SIP PERFORMANCE - Regular Plan Growth Option",
                evidence=(
                    "Market Value as on August 31, 2026 (Rs. in Lacs); "
                    "1 year SIP = 1.23"
                ),
                prompt_eval_count=800,
                eval_count=70,
            )
            client = MagicMock()
            client.chat.return_value = page_evidence
            usage_tracker = UsageTracker()

            with (
                patch("fundlens_rag.rag.factsheets.find_factsheets", return_value=[pdf_path]),
                patch("fundlens_rag.app.vision_fallback._render_pdf_page", return_value=b"jpeg-page"),
                patch.dict(os.environ, {"OLLAMA_VISION_MODEL": "qwen3-vl:235b-cloud"}),
            ):
                result = extract_visual_evidence(
                    question=self.QUESTION,
                    retrieved_chunks=[self._chunk(pdf_path)],
                    client=client,
                    usage_tracker=usage_tracker,
                )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["document"], pdf_path.name)
        self.assertEqual(result[0]["page"], 87)
        self.assertEqual(result[0]["source_url"], pdf_path.as_uri())
        self.assertTrue(result[0]["visual_fallback"])
        self.assertIn("1 year SIP = 1.23", result[0]["text"])
        self.assertEqual(client.chat.call_args.kwargs["model"], "qwen3-vl:235b-cloud")
        self.assertEqual(
            client.chat.call_args.kwargs["messages"][0]["images"],
            [b"jpeg-page"],
        )
        self.assertEqual(usage_tracker.snapshot()[0]["requests"], 1)
        self.assertEqual(usage_tracker.snapshot()[0]["input_tokens"], 800)
        self.assertEqual(usage_tracker.snapshot()[0]["output_tokens"], 70)

    def test_skips_a_wrong_fund_page_and_checks_the_next_candidate(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf") as temporary_pdf:
            pdf_path = Path(temporary_pdf.name).resolve()
            wrong_fund = self._response(
                found=True,
                subject="HDFC ELSS Tax Saver Fund",
                heading="SIP performance",
                evidence="ELSS equity linked savings scheme; 1 year SIP market value 9.99.",
            )
            right_fund = self._response(
                found=True,
                subject="HDFC Medium to Long Term Fund",
                heading="SIP PERFORMANCE - Regular Plan Growth Option",
                evidence=(
                    "Market Value as on August 31, 2026 (Rs. in Lacs); "
                    "1 year SIP = 1.23"
                ),
            )
            client = MagicMock()
            client.chat.side_effect = [wrong_fund, right_fund]
            chunks = [self._chunk(pdf_path, 64), self._chunk(pdf_path, 87)]

            with (
                patch("fundlens_rag.rag.factsheets.find_factsheets", return_value=[pdf_path]),
                patch("fundlens_rag.app.vision_fallback._render_pdf_page", return_value=b"jpeg-page"),
            ):
                result = extract_visual_evidence(
                    question=self.QUESTION,
                    retrieved_chunks=chunks,
                    client=client,
                )

        self.assertEqual(result[0]["page"], 87)
        self.assertEqual(client.chat.call_count, 2)

    def test_does_not_return_a_page_when_model_cannot_find_the_requested_evidence(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf") as temporary_pdf:
            pdf_path = Path(temporary_pdf.name).resolve()
            client = MagicMock()
            client.chat.return_value = self._response(
                found=False,
                subject="HDFC Medium to Long Term Fund",
                heading="SIP performance",
                evidence="",
            )

            with (
                patch("fundlens_rag.rag.factsheets.find_factsheets", return_value=[pdf_path]),
                patch("fundlens_rag.app.vision_fallback._render_pdf_page", return_value=b"jpeg-page"),
            ):
                result = extract_visual_evidence(
                    question=self.QUESTION,
                    retrieved_chunks=[self._chunk(pdf_path)],
                    client=client,
                )

        self.assertEqual(result, [])

    def test_skips_source_urls_outside_the_local_factsheet_directory(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf") as temporary_pdf:
            pdf_path = Path(temporary_pdf.name).resolve()
            chunk = self._chunk(pdf_path)
            chunk["source_url"] = "https://example.invalid/factsheet.pdf"
            client = MagicMock()

            with patch("fundlens_rag.rag.factsheets.find_factsheets", return_value=[pdf_path]):
                result = extract_visual_evidence(
                    question=self.QUESTION,
                    retrieved_chunks=[chunk],
                    client=client,
                )

        self.assertEqual(result, [])
        client.chat.assert_not_called()

    def test_direct_cloud_client_uses_bearer_authentication(self):
        with (
            patch.dict(
                os.environ,
                {
                    "OLLAMA_BASE_URL": "https://ollama.com",
                    "OLLAMA_API_KEY": "test-key",
                },
            ),
            patch("fundlens_rag.app.vision_fallback.Client") as client_factory,
        ):
            _get_ollama_cloud_client()

        self.assertEqual(
            client_factory.call_args.kwargs["host"],
            "https://ollama.com",
        )
        self.assertEqual(
            client_factory.call_args.kwargs["headers"],
            {"Authorization": "Bearer test-key"},
        )

    def test_direct_cloud_client_requires_an_api_key(self):
        with patch.dict(
            os.environ,
            {
                "OLLAMA_BASE_URL": "https://ollama.com",
                "OLLAMA_API_KEY": "",
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "OLLAMA_API_KEY is required"):
                _get_ollama_cloud_client()


if __name__ == "__main__":
    unittest.main()
