import sys
from io import StringIO
from types import ModuleType
from unittest.mock import ANY, Mock, patch
from uuid import uuid4

from django.core.management import call_command
from django.contrib.auth import get_user_model
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
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="USER001",
            email="user001@example.com",
            password="Bright-Mountain-42!",
        )
        self.client.force_authenticate(user=self.user)

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
                "user_id": "ANOTHER_USERS_ID",
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
    def test_fund_answer_preserves_rag_method_citations_evidence_and_usage(
        self,
        mock_run_chat,
    ):
        evidence = {
            "text": "The one-year scheme return was 12%.",
            "document": "HDFC Factsheet.pdf",
            "page": 64,
            "fund_name": "HDFC ELSS - Tax Saver Fund",
            "score": 0.87,
        }
        source = {
            "name": "HDFC Factsheet.pdf",
            "document": "HDFC Factsheet.pdf",
            "page": 64,
            "url": None,
        }
        usage = {
            "role": "answer",
            "model": "gemma4:31b",
            "requests": 2,
            "input_tokens": 1200,
            "output_tokens": 90,
            "input_reports": 2,
            "output_reports": 2,
            "estimated_cost": "Rates not configured",
        }
        mock_run_chat.return_value = {
            "success": True,
            "answer": "The one-year return was 12% [HDFC Factsheet.pdf, page 64].",
            "sources": [source],
            "retrieved_chunks": [evidence],
            "answer_method": "agent_plus_rag",
            "usage": [usage],
        }

        response = self.client.post(
            "/api/v1/chat/",
            {
                "user_id": "USER001",
                "message": "What was the one-year return for HDFC ELSS - Tax Saver Fund?",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["answer_method"], "agent_plus_rag")
        self.assertEqual(response.data["sources"][0]["page"], 64)
        self.assertEqual(response.data["retrieved_chunks"][0]["document"], "HDFC Factsheet.pdf")
        self.assertEqual(response.data["retrieved_chunks"][0]["page"], 64)
        self.assertEqual(response.data["usage"][0]["input_tokens"], 1200)

        conversation_id = response.data["conversation_id"]
        reopened = self.client.get(
            f"/api/v1/chat/conversations/{conversation_id}/?user_id=USER001"
        )
        self.assertEqual(reopened.status_code, 200)
        assistant_message = reopened.data["messages"][1]
        self.assertEqual(assistant_message["metadata"]["answer_method"], "agent_plus_rag")
        self.assertEqual(assistant_message["metadata"]["retrieved_chunks"][0]["page"], 64)
        self.assertEqual(assistant_message["metadata"]["usage"][0]["input_tokens"], 1200)

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

        other_user = get_user_model().objects.create_user(
            username="USER002",
            email="user002@example.com",
            password="Bright-Mountain-42!",
        )
        self.client.force_authenticate(user=other_user)

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

    def test_user_can_list_saved_conversations(self):
        older = Conversation.objects.create(user_id="USER001")
        ChatMessage.objects.create(
            conversation=older,
            role=ChatMessage.Role.USER,
            content="How many funds do I have?",
        )
        ChatMessage.objects.create(
            conversation=older,
            role=ChatMessage.Role.ASSISTANT,
            content="You have three funds.",
        )
        other_user = Conversation.objects.create(user_id="USER002")
        ChatMessage.objects.create(
            conversation=other_user,
            role=ChatMessage.Role.USER,
            content="This conversation is private.",
        )

        response = self.client.get(
            "/api/v1/chat/conversations/?user_id=USER001"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        summary = response.data["results"][0]
        self.assertEqual(str(summary["id"]), str(older.id))
        self.assertEqual(summary["title"], "How many funds do I have?")
        self.assertEqual(summary["message_count"], 2)

    def test_user_can_reopen_only_their_saved_conversation(self):
        conversation = Conversation.objects.create(user_id="USER001")
        ChatMessage.objects.create(
            conversation=conversation,
            role=ChatMessage.Role.USER,
            content="Do my funds overlap?",
        )
        ChatMessage.objects.create(
            conversation=conversation,
            role=ChatMessage.Role.ASSISTANT,
            content="HDFC Bank is a common holding.",
        )

        response = self.client.get(
            f"/api/v1/chat/conversations/{conversation.id}/?user_id=USER001"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(response.data["id"]), str(conversation.id))
        self.assertEqual(
            [
                (message["role"], message["content"])
                for message in response.data["messages"]
            ],
            [
                ("user", "Do my funds overlap?"),
                ("assistant", "HDFC Bank is a common holding."),
            ],
        )

        other_user = get_user_model().objects.create_user(
            username="USER002",
            email="user002@example.com",
            password="Bright-Mountain-42!",
        )
        self.client.force_authenticate(user=other_user)
        forbidden = self.client.get(
            f"/api/v1/chat/conversations/{conversation.id}/?user_id=USER002"
        )
        self.assertEqual(forbidden.status_code, 404)

    def test_rag_job_is_private_to_the_account_that_queued_it(self):
        queued = self.client.post(
            "/api/v1/rag/jobs/",
            {"question": "What is this fund's benchmark?", "fund_scope": "Example Fund"},
            format="json",
        )

        self.assertEqual(queued.status_code, 202)
        job = RagQuestionJob.objects.get(id=queued.data["job_id"])
        self.assertEqual(job.user_id, "USER001")

        other_user = get_user_model().objects.create_user(
            username="USER002",
            email="user002@example.com",
            password="Bright-Mountain-42!",
        )
        self.client.force_authenticate(user=other_user)
        status_response = self.client.get(queued.data["poll_url"])
        self.assertEqual(status_response.status_code, 404)
