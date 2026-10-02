import os
import unittest
from unittest.mock import patch

from fundlens_rag.app.llm import get_llm


class OllamaConfigurationTests(unittest.TestCase):
    @patch("fundlens_rag.app.llm.ChatOllama")
    def test_configures_cloud_host_model_and_bearer_auth(self, chat_ollama):
        with patch.dict(
            os.environ,
            {
                "OLLAMA_MODEL": "gemma4:31b",
                "OLLAMA_BASE_URL": "https://ollama.com/",
                "OLLAMA_API_KEY": "test-key",
            },
        ):
            get_llm()

        chat_ollama.assert_called_once_with(
            model="gemma4:31b",
            temperature=0,
            base_url="https://ollama.com",
            client_kwargs={
                "headers": {"Authorization": "Bearer test-key"}
            },
        )

    @patch("fundlens_rag.app.llm.ChatOllama")
    def test_local_ollama_does_not_receive_cloud_api_key(self, chat_ollama):
        with patch.dict(
            os.environ,
            {
                "OLLAMA_MODEL": "local-model",
                "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
                "OLLAMA_API_KEY": "do-not-send-to-local",
            },
        ):
            get_llm()

        chat_ollama.assert_called_once_with(
            model="local-model",
            temperature=0,
            base_url="http://127.0.0.1:11434",
            client_kwargs={},
        )

    @patch("fundlens_rag.app.llm.ChatOllama")
    def test_requires_api_key_for_https_cloud(self, chat_ollama):
        with patch.dict(
            os.environ,
            {
                "OLLAMA_MODEL": "gemma4:31b",
                "OLLAMA_BASE_URL": "https://ollama.com",
                "OLLAMA_API_KEY": "",
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "OLLAMA_API_KEY is required"):
                get_llm()

        chat_ollama.assert_not_called()

    @patch("fundlens_rag.app.llm.ChatOllama")
    def test_rejects_remote_http_to_prevent_credential_leaks(self, chat_ollama):
        with patch.dict(
            os.environ,
            {
                "OLLAMA_MODEL": "remote-model",
                "OLLAMA_BASE_URL": "http://ollama.internal:11434",
                "OLLAMA_API_KEY": "test-key",
            },
        ):
            with self.assertRaisesRegex(ValueError, "must use HTTPS"):
                get_llm()

        chat_ollama.assert_not_called()


if __name__ == "__main__":
    unittest.main()
