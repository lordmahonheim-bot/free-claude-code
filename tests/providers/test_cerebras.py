from unittest.mock import MagicMock, patch

import pytest

from config.provider_catalog import CEREBRAS_DEFAULT_BASE
from providers.base import ProviderConfig
from providers.cerebras import CerebrasProvider


class MockMessage:
    def __init__(self, role, content):
        self.role = role
        self.content = content


class MockRequest:
    def __init__(self, **kwargs):
        self.model = "test-model"
        self.messages = [MockMessage("user", "Hello")]
        self.max_tokens = 100
        self.temperature = 0.5
        self.top_p = 0.9
        self.system = "System prompt"
        self.stop_sequences = ["STOP"]
        self.tools = []
        self.tool_choice = None
        self.metadata = None
        self.extra_body = {}
        self.thinking = MagicMock()
        self.thinking.enabled = True
        for key, value in kwargs.items():
            setattr(self, key, value)


@pytest.fixture
def provider_config():
    return ProviderConfig(
        api_key="test_key",
        base_url=CEREBRAS_DEFAULT_BASE,
        rate_limit=40,
        rate_window=60,
        max_concurrency=5,
    )


def test_init(provider_config):
    with patch("providers.openai_compat.AsyncOpenAI") as mock_openai:
        provider = CerebrasProvider(provider_config)
        assert provider._api_key == "test_key"
        assert provider._base_url == CEREBRAS_DEFAULT_BASE
        mock_openai.assert_called_once()


def test_build_request_body(provider_config):
    provider = CerebrasProvider(provider_config)
    req = MockRequest()
    body = provider._build_request_body(req)

    assert body["model"] == "test-model"
    assert body["temperature"] == 0.5
    assert body["top_p"] == 0.9
    assert body["max_tokens"] == 100
    assert len(body["messages"]) == 2
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][0]["content"] == "System prompt"
    assert body["messages"][1]["role"] == "user"


def test_build_request_body_disables_reasoning_replay(provider_config):
    provider = CerebrasProvider(provider_config)
    req = MockRequest()
    body = provider._build_request_body(req)

    assert "extra_body" not in body or "reasoning_budget" not in body.get("extra_body", {})
