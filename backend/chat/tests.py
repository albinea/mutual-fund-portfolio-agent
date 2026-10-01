from unittest.mock import patch
from uuid import uuid4

from rest_framework.test import APITestCase

from .models import ChatMessage, Conversation


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

        forbidden = self.client.get(
            f"/api/v1/chat/conversations/{conversation.id}/?user_id=USER002"
        )
        self.assertEqual(forbidden.status_code, 404)
