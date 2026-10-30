import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.openai_access import validate_api_key_and_list_models


class OpenAIModelDiscoveryTests(unittest.TestCase):
    @patch("src.openai_access.OpenAI")
    def test_returns_available_chat_models_and_excludes_non_chat_models(self, openai_client):
        openai_client.return_value.models.list.return_value.data = [
            SimpleNamespace(id="gpt-4o-mini"),
            SimpleNamespace(id="o3-mini"),
            SimpleNamespace(id="text-embedding-3-small"),
            SimpleNamespace(id="gpt-4o-realtime-preview"),
            SimpleNamespace(id="dall-e-3"),
        ]

        models = validate_api_key_and_list_models("test-key")

        self.assertEqual(models, ["gpt-4o-mini", "o3-mini"])
        openai_client.assert_called_once_with(api_key="test-key", timeout=20, max_retries=0)

    @patch("src.openai_access.OpenAI")
    def test_rejects_accounts_without_supported_chat_models(self, openai_client):
        openai_client.return_value.models.list.return_value.data = [
            SimpleNamespace(id="text-embedding-3-small"),
        ]

        with self.assertRaisesRegex(ValueError, "no supported chat models"):
            validate_api_key_and_list_models("test-key")


if __name__ == "__main__":
    unittest.main()