import sys
from io import StringIO
from types import ModuleType
from unittest.mock import ANY, Mock, patch
from uuid import uuid4

from django.core.management import call_command
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from .models import ChatMessage, Conversation, RagQuestionJob
from .services import run_fundlens_rag


class IndexFactsheetsCommandTests(SimpleTestCase):
    @patch("chat.management.commands.index_factsheets.ensure_factsheets_indexed")
    def test_indexes_new_factsheets_and_reports_them(self, mock_index):
        mock_index.return_value = ["New fund factsheet.pdf"]
        output = StringIO()

        call_command("index_factsheets", stdout=output)

        mock_index.assert_called_once_with()
        self.assertIn("Indexed 1 new factsheet(s)", output.getvalue())
        self.assertIn("New fund factsheet.pdf", output.getvalue())

    @patch("chat.management.commands.index_factsheets.ensure_factsheets_indexed")
    def test_reports_when_every_factsheet_is_already_indexed(self, mock_index):
        mock_index.return_value = []
        output = StringIO()

        call_command("index_factsheets", stdout=output)

        self.assertIn("No new factsheets to index", output.getvalue())


class FundLensRagServiceAdapterTests(SimpleTestCase):
    def test_django_adapter_forwards_to_the_single_rag_service(self):
        mock_answer = Mock()
        mock_answer.return_value = {"success": True, "answer": "Evidence-backed."}

        service_module = ModuleType("fundlens_rag.service")
        service_module.answer_fundlens_question = mock_answer
        with patch.dict(sys.modules, {"fundlens_rag.service": service_module}):
            result = run_fundlens_rag(
                "Question about this fund",
                "HDFC Example Fund",
                prompt_version="v1",
                top_k=4,
                usage_tracker=None,
            )

        self.assertEqual(result["answer"], "Evidence-backed.")
        mock_answer.assert_called_once_with(
            question="Question about this fund",
            fund_scope="HDFC Example Fund",
            prompt_version="v1",
            top_k=4,
            usage_tracker=None,
        )


class ChatApiTests(APITestCase):
    @patch("chat.views.run_chat")
    def test_new_conversation_starts_with_empty_server_context(
        self,
        mock_run_chat,
    ):
        mock_run_chat.return_value = {
            "success": True,
            "answer": "Your portfolio has two funds.",
            "sources": [],
        }

        response = self.client.post(
            "/api/v1/chat/",
            {
                "user_id": "USER001",
                "message": "How many funds do I have?",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["answer"],
            "Your portfolio has two funds.",
        )
        self.assertIn("conversation_id", response.data)
        conversation = Conversation.objects.get(id=response.data["conversation_id"])
        self.assertEqual(conversation.user_id, "USER001")
        self.assertEqual(
            list(
                conversation.messages.values_list("role", "content")
            ),
            [
                (ChatMessage.Role.USER, "How many funds do I have?"),
                (ChatMessage.Role.ASSISTANT, "Your portfolio has two funds."),
            ],
        )

        mock_run_chat.assert_called_once_with(
            message="How many funds do I have?",
            user_id="USER001",
            conversation_context=[],
        )

    @patch("chat.views.run_chat")
    def test_follow_up_uses_saved_conversation_context(self, mock_run_chat):
        mock_run_chat.side_effect = [
            {
                "success": True,
                "answer": "You have three mutual funds.",
                "sources": [],
            },
            {
                "success": True,
                "answer": "HDFC Bank has the highest overlap.",
                "sources": [],
            },
        ]

        first_response = self.client.post(
            "/api/v1/chat/",
            {
                "user_id": "USER001",
                "message": "How many funds do I have?",
            },
            format="json",
        )

        self.assertEqual(first_response.status_code, 200)
        conversation_id = first_response.data["conversation_id"]

        second_response = self.client.post(
            "/api/v1/chat/",
            {
                "user_id": "USER001",
                "conversation_id": conversation_id,
                "message": "Which company has the highest overlap?",
            },
            format="json",
        )

        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(
            second_response.data["answer"],
            "HDFC Bank has the highest overlap.",
        )

        second_call = mock_run_chat.call_args_list[1]
        self.assertEqual(
            second_call.kwargs["conversation_context"],
            [
                {"role": "user", "content": "How many funds do I have?"},
                {
                    "role": "assistant",
                    "content": "You have three mutual funds.",
                },
            ],
        )

    @patch("chat.views.run_chat")
    def test_different_user_cannot_access_conversation(self, mock_run_chat):
        mock_run_chat.return_value = {
            "success": True,
            "answer": "You have three mutual funds.",
            "sources": [],
        }
        first_response = self.client.post(
            "/api/v1/chat/",
            {"user_id": "USER001", "message": "How many funds do I have?"},
            format="json",
        )

        response = self.client.post(
            "/api/v1/chat/",
            {
                "user_id": "USER002",
                "conversation_id": first_response.data["conversation_id"],
                "message": "Show the earlier messages.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        mock_run_chat.assert_called_once()

    @patch("chat.views.run_chat")
    def test_unknown_conversation_returns_not_found(self, mock_run_chat):
        response = self.client.post(
            "/api/v1/chat/",
            {
                "user_id": "USER001",
                "conversation_id": str(uuid4()),
                "message": "Continue our conversation.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        mock_run_chat.assert_not_called()

    def test_invalid_chat_requests_return_bad_request(self):
        invalid_payloads = [
            {},
            {"user_id": "", "message": "How many funds do I have?"},
            {"user_id": "USER001", "message": ""},
        ]

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/api/v1/chat/",
                    payload,
                    format="json",
                )
                self.assertEqual(response.status_code, 400)


class RagAnswerApiTests(APITestCase):
    URL = "/api/v1/rag/answer/"

    @staticmethod
    def _result() -> dict:
        return {
            "success": True,
            "error_code": None,
            "answer": "The 1-year SIP value was ₹1.23 lacs. [SOURCE 1]",
            "draft_answer": None,
            "confidence": 0.8,
            "fund_name": "HDFC Medium to Long Term Fund",
            "answer_method": "rag_only",
            "visual_fallback_triggered": False,
            "visual_fallback_used": False,
            "table_answer_used": False,
            "grounding_error": None,
            "sources": [
                {
                    "document": "HDFC MF Factsheet - August 2026.pdf",
                    "page": 87,
                    "source_url": "file:///private/server/path/factsheet.pdf",
                    "labels": ["SOURCE 1"],
                }
            ],
            "retrieved_chunks": [
                {
                    "text": "1 year SIP market value = 1.23 lacs",
                    "document": "HDFC MF Factsheet - August 2026.pdf",
                    "page": 87,
                    "source_url": "file:///private/server/path/factsheet.pdf",
                    "score": 0.91,
                    "fund_name": "HDFC Medium to Long Term Fund",
                    "document_type": "factsheet",
                    "published_date": None,
                }
            ],
            "usage": [
                {
                    "role": "answer",
                    "model": "test-model",
                    "requests": 1,
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "input_reports": 1,
                    "output_reports": 1,
                }
            ],
            "indexed_documents": [],
        }

    @patch("chat.rag_views.run_fundlens_rag")
    def test_returns_grounded_answer_chunks_citations_and_usage(self, mock_run):
        mock_run.return_value = self._result()

        response = self.client.post(
            self.URL,
            {
                "question": "  What was the SIP value?  ",
                "fund_scope": "HDFC Medium to Long Term Fund",
                "top_k": 3,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["answer_method"], "rag_only")
        self.assertEqual(response.data["sources"][0]["page"], 87)
        self.assertEqual(
            response.data["retrieved_chunks"][0]["text"],
            "1 year SIP market value = 1.23 lacs",
        )
        self.assertEqual(response.data["usage"][0]["input_tokens"], 100)
        self.assertIn("estimated_cost", response.data["usage"][0])
        self.assertNotIn("source_url", response.data["sources"][0])
        self.assertNotIn("source_url", response.data["retrieved_chunks"][0])
        mock_run.assert_called_once_with(
            question="What was the SIP value?",
            fund_scope="HDFC Medium to Long Term Fund",
            top_k=3,
            usage_tracker=ANY,
        )

    @patch("chat.rag_views.run_fundlens_rag")
    def test_evidence_gap_is_a_normal_response_not_a_service_outage(self, mock_run):
        result = self._result()
        result.update(
            {
                "success": False,
                "error_code": "no_retrieved_chunks",
                "answer": "I could not find sufficient evidence.",
                "confidence": 0.0,
                "sources": [],
                "retrieved_chunks": [],
            }
        )
        mock_run.return_value = result

        response = self.client.post(
            self.URL,
            {"question": "Question about a fund"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error_code"], "no_retrieved_chunks")

    @patch("chat.rag_views.run_fundlens_rag")
    def test_invalid_question_or_top_k_is_rejected(self, mock_run):
        for payload in (
            {"question": "   "},
            {"question": "Question", "top_k": 11},
        ):
            with self.subTest(payload=payload):
                response = self.client.post(self.URL, payload, format="json")
                self.assertEqual(response.status_code, 400)

        mock_run.assert_not_called()

    @patch("chat.rag_views.run_fundlens_rag")
    def test_service_failure_returns_safe_503(self, mock_run):
        def fail_with_recorded_attempt(**kwargs):
            kwargs["usage_tracker"].record_request("answer", "test-model")
            raise RuntimeError("private failure detail")

        mock_run.side_effect = fail_with_recorded_attempt
        response = self.client.post(
            self.URL,
            {"question": "Question about a fund"},
            format="json",
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["error_code"], "rag_unavailable")
        self.assertNotIn("private failure detail", response.data["answer"])
        self.assertEqual(response.data["usage"][0]["requests"], 1)


class RagJobApiEndToEndTests(APITestCase):
    CREATE_URL = "/api/v1/rag/jobs/"

    @patch("chat.rag_jobs.run_fundlens_rag")
    def test_fund_question_job_returns_citation_and_evidence_for_chat_panel(self, mock_run):
        mock_run.return_value = RagAnswerApiTests._result()

        accepted = self.client.post(
            self.CREATE_URL,
            {
                "question": "What was the 1-year SIP market value?",
                "fund_scope": "HDFC Medium to Long Term Fund",
                "top_k": 3,
            },
            format="json",
        )

        self.assertEqual(accepted.status_code, 202)
        self.assertEqual(accepted.data["status"], RagQuestionJob.Status.QUEUED)
        mock_run.assert_not_called()

        # Exercise the same separate worker process used outside request handling.
        call_command("run_rag_worker", "--once", stdout=StringIO())
        mock_run.assert_called_once_with(
            question="What was the 1-year SIP market value?",
            fund_scope="HDFC Medium to Long Term Fund",
            top_k=3,
            usage_tracker=ANY,
        )

        completed = self.client.get(accepted.data["poll_url"])
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.data["status"], RagQuestionJob.Status.COMPLETED)
        self.assertIn("[SOURCE 1]", completed.data["result"]["answer"])
        self.assertEqual(
            completed.data["result"]["sources"][0]["page"],
            87,
        )
        # These are the exact retrieved-chunk fields rendered by the React evidence panel.
        self.assertEqual(
            completed.data["result"]["retrieved_chunks"][0]["text"],
            "1 year SIP market value = 1.23 lacs",
        )
        self.assertEqual(
            completed.data["result"]["retrieved_chunks"][0]["document"],
            "HDFC MF Factsheet - August 2026.pdf",
        )

    def test_job_is_queued_without_running_model_and_can_be_polled(self):
        response = self.client.post(
            self.CREATE_URL,
            {"question": "What is this fund's objective?"},
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["status"], RagQuestionJob.Status.QUEUED)
        self.assertEqual(
            self.client.get(response.data["poll_url"]).data["status"],
            RagQuestionJob.Status.QUEUED,
        )

    def test_invalid_job_request_is_rejected(self):
        response = self.client.post(
            self.CREATE_URL,
            {"question": "  ", "top_k": 0},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(RagQuestionJob.objects.count(), 0)

    @patch("chat.rag_jobs.run_fundlens_rag", side_effect=RuntimeError("secret detail"))
    def test_worker_failure_is_reported_safely(self, mock_run):
        accepted = self.client.post(
            self.CREATE_URL,
            {"question": "Question about a fund"},
            format="json",
        )

        call_command("run_rag_worker", "--once", stdout=StringIO())
        response = self.client.get(accepted.data["poll_url"])

        self.assertEqual(response.data["status"], RagQuestionJob.Status.FAILED)
        self.assertEqual(response.data["result"]["error_code"], "rag_unavailable")
        self.assertNotIn("secret detail", response.data["result"]["answer"])
