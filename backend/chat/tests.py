from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class ChatApiTests(APITestCase):
    url = reverse("chat")

    @patch("chat.views.run_chat")
    def test_chat_returns_agent_response(self, mock_run_chat):
        mock_run_chat.return_value = {
            "success": True,
            "answer": "Your portfolio has overlapping holdings.",
            "sources": [{"name": "Mock portfolio store"}],
            "tool_trace": [{"tool": "calculate_fund_overlap", "success": True}],
            "metadata": {"iterations": 2, "tool_calls": 1},
        }

        payload = {
            "user_id": "USER001",
            "message": "Do my mutual funds overlap?",
            "conversation_context": [
                {"role": "user", "content": "Show my portfolio first."}
            ],
        }

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(
            response.data["tool_trace"][0]["tool"],
            "calculate_fund_overlap",
        )
        mock_run_chat.assert_called_once_with(**payload)

    def test_chat_rejects_invalid_request(self):
        response = self.client.post(
            self.url,
            {"user_id": "USER001", "message": ""},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("message", response.data)

    @patch("chat.views.run_chat")
    def test_chat_preserves_structured_agent_failure(self, mock_run_chat):
        mock_run_chat.return_value = {
            "success": False,
            "error_code": "OLLAMA_NOT_CONFIGURED",
            "answer": "Set OLLAMA_API_KEY and OLLAMA_MODEL before using the agent endpoint.",
            "sources": [],
            "tool_trace": [],
            "metadata": {"iterations": 0, "tool_calls": 0},
        }

        response = self.client.post(
            self.url,
            {
                "user_id": "USER001",
                "message": "Show my portfolio.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error_code"], "OLLAMA_NOT_CONFIGURED")