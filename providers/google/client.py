"""Google/Gemini provider implementation."""

from typing import Any

from config.provider_catalog import GOOGLE_DEFAULT_BASE
from core.anthropic import ReasoningReplayMode, build_base_request_body
from core.anthropic.conversion import OpenAIConversionError
from providers.base import ProviderConfig
from providers.exceptions import InvalidRequestError
from providers.openai_compat import OpenAIChatTransport


class GoogleProvider(OpenAIChatTransport):
    """Google Gemini provider using the OpenAI-compatible chat completions API."""

    def __init__(self, config: ProviderConfig):
        super().__init__(
            config,
            provider_name="GOOGLE",
            base_url=config.base_url or GOOGLE_DEFAULT_BASE,
            api_key=config.api_key,
        )

    def _build_request_body(
        self, request: Any, thinking_enabled: bool | None = None
    ) -> dict:
        """Build an OpenAI-compatible chat completion request body for Gemini."""
        try:
            return build_base_request_body(
                request,
                reasoning_replay=ReasoningReplayMode.DISABLED,
            )
        except OpenAIConversionError as exc:
            raise InvalidRequestError(str(exc)) from exc
