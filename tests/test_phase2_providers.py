import os
import unittest
from unittest.mock import patch

from APP.providers.chat import AzureOpenAIChatProvider, OpenAIChatProvider, _as_v1_base_url, build_default_chat_provider


class AsV1BaseUrlTests(unittest.TestCase):
    def test_strips_trailing_responses_path(self):
        endpoint = "https://example-resource.services.ai.azure.com/api/projects/example/openai/v1/responses"
        self.assertEqual(
            _as_v1_base_url(endpoint),
            "https://example-resource.services.ai.azure.com/api/projects/example/openai/v1",
        )

    def test_leaves_bare_v1_base_untouched(self):
        endpoint = "https://example-resource.services.ai.azure.com/api/projects/example/openai/v1"
        self.assertEqual(_as_v1_base_url(endpoint), endpoint)

    def test_strips_trailing_slash(self):
        endpoint = "https://example-resource.services.ai.azure.com/openai/v1/responses/"
        self.assertEqual(
            _as_v1_base_url(endpoint),
            "https://example-resource.services.ai.azure.com/openai/v1",
        )


class BuildDefaultChatProviderTests(unittest.TestCase):
    def test_prefers_azure_when_configured(self):
        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_ENDPOINT": "https://example.services.ai.azure.com/openai/v1/responses",
                "AZURE_OPENAI_MODEL": "gpt-5-mini",
            },
        ):
            provider = build_default_chat_provider()
        self.assertIsInstance(provider, AzureOpenAIChatProvider)
        self.assertEqual(provider.chat_model, "gpt-5-mini")

    def test_falls_back_to_openai_when_azure_not_configured(self):
        with patch.dict(os.environ, {}, clear=False):
            for key in ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"):
                os.environ.pop(key, None)
            provider = build_default_chat_provider()
        self.assertIsInstance(provider, OpenAIChatProvider)

    def test_provider_client_construction_is_lazy(self):
        # Constructing a provider must not itself validate credentials or
        # touch the network — only actually calling .complete()/.client does.
        provider = AzureOpenAIChatProvider(api_key="", endpoint="https://example.com/openai/v1", model="gpt-5-mini")
        self.assertIsNone(provider._client)


if __name__ == "__main__":
    unittest.main()
