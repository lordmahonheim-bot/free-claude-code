"""Cloudflare Workers AI provider implementation."""

from typing import Any

from config.provider_catalog import CLOUDFLARE_DEFAULT_BASE
from core.anthropic import ReasoningReplayMode, build_base_request_body
from core.anthropic.conversion import OpenAIConversionError
from providers.base import ProviderConfig
from providers.exceptions import AuthenticationError, InvalidRequestError
from providers.openai_compat import OpenAIChatTransport


def _resolve_workers_ai_base_url(base_url: str, account_id: str) -> str:
    """Return the OpenAI-compatible Workers AI base URL.

    The OpenAI SDK appends /chat/completions, so the base URL must end at /ai/v1.
    """
    base = (base_url or CLOUDFLARE_DEFAULT_BASE).rstrip("/")
    if base.endswith("/ai/v1"):
        return base

    account = account_id.strip()
    if not account:
        raise AuthenticationError(
            "CLOUDFLARE_ACCOUNT_ID is not set. Add it to your .env file."
        )

    if "/accounts/" in base:
        return f"{base}/ai/v1"
    return f"{base}/accounts/{account}/ai/v1"


class CloudflareProvider(OpenAIChatTransport):
    """Cloudflare Workers AI provider using the OpenAI-compatible API."""

    def __init__(self, config: ProviderConfig, *, account_id: str):
        super().__init__(
            config,
            provider_name="CLOUDFLARE",
            base_url=_resolve_workers_ai_base_url(config.base_url, account_id),
            api_key=config.api_key,
        )

    def _build_request_body(
        self, request: Any, thinking_enabled: bool | None = None
    ) -> dict:
        """Build an OpenAI-compatible chat completion request body for Workers AI.

        KIMI K2.6 on Cloudflare spends completion budget on reasoning unless thinking is
        explicitly disabled. Workers AI also expects max_completion_tokens for this
        OpenAI-compatible endpoint.
        """
        try:
            body = build_base_request_body(
                request,
                reasoning_replay=ReasoningReplayMode.DISABLED,
            )
        except OpenAIConversionError as exc:
            raise InvalidRequestError(str(exc)) from exc

        if "max_tokens" in body and "max_completion_tokens" not in body:
            body["max_completion_tokens"] = body.pop("max_tokens")

        extra_body = body.setdefault("extra_body", {})
        chat_template_kwargs = extra_body.setdefault("chat_template_kwargs", {})
        chat_template_kwargs.setdefault("thinking", False)

        return body
