from unittest.mock import patch

from rest_framework.test import APITestCase


class ChatApiTests(APITestCase):
    @patch("chat.views.run_chat")
    def test_chat_forwards_message_identity_and_context(self, mock_run_chat):
        mock_run_chat.return_value = {"success": True, "answer": "Your portfolio has two funds.", "sources": []}

        response = self.client.post(
            "/api/v1/chat/",
            {
                "user_id": "USER001",
                "message": "How many funds do I have?",
                "conversation_context": [{"role": "user", "content": "Hello"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["answer"], "Your portfolio has two funds.")
        mock_run_chat.assert_called_once_with(
            message="How many funds do I have?",
            user_id="USER001",
            conversation_context=[{"role": "user", "content": "Hello"}],
        )

    def test_chat_rejects_invalid_context(self):
        response = self.client.post(
            "/api/v1/chat/",
            {"user_id": "USER001", "message": "Hello", "conversation_context": [{"role": "system", "content": "x"}]},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
