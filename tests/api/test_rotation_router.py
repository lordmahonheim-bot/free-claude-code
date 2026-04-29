import pytest

from api.model_router import ModelRouter, ResolvedModel
from api.models.anthropic import Message, MessagesRequest, TokenCountRequest
from api.rotation_router import RotationRouter, resolved_from_candidate
from config.settings import Settings
from api.rotation_engine import (
    FailureCategory,
    ModelCandidate,
    ModelRing,
    ProviderRotationEngine,
)


@pytest.fixture
def settings():
    settings = Settings()
    settings.model = "nvidia_nim/fallback-model"
    settings.model_opus = None
    settings.model_sonnet = None
    settings.model_haiku = None
    settings.enable_model_thinking = True
    settings.enable_opus_thinking = None
    settings.enable_sonnet_thinking = None
    settings.enable_haiku_thinking = None
    return settings


def test_resolved_from_candidate_preserves_original_and_thinking():
    resolved = ResolvedModel(
        original_model="claude-opus",
        provider_id="nvidia_nim",
        provider_model="old-model",
        provider_model_ref="nvidia_nim/old-model",
        thinking_enabled=True,
    )
    candidate = ModelCandidate("open_router/deepseek/deepseek-v4-pro")

    updated = resolved_from_candidate(resolved, candidate)

    assert updated.original_model == "claude-opus"
    assert updated.provider_id == "open_router"
    assert updated.provider_model == "deepseek/deepseek-v4-pro"
    assert updated.provider_model_ref == "open_router/deepseek/deepseek-v4-pro"
    assert updated.thinking_enabled is True


def test_rotation_router_routes_messages_request_to_selected_candidate(settings):
    request = MessagesRequest(
        model="claude-opus-4-20250514",
        max_tokens=100,
        messages=[Message(role="user", content="hello")],
    )
    base_routed = ModelRouter(settings).resolve_messages_request(request)
    ring = ModelRing(
        "code",
        (
            ModelCandidate("open_router/deepseek/deepseek-v4-pro", priority=100),
            ModelCandidate("groq/llama-3.3-70b-versatile", priority=50),
        ),
    )

    rotated = RotationRouter(ProviderRotationEngine()).route_messages_request(
        base_routed,
        ring,
        now=100.0,
    )

    assert rotated.request.model == "deepseek/deepseek-v4-pro"
    assert rotated.resolved.provider_id == "open_router"
    assert rotated.resolved.provider_model == "deepseek/deepseek-v4-pro"
    assert rotated.resolved.provider_model_ref == "open_router/deepseek/deepseek-v4-pro"
    assert rotated.resolved.original_model == "claude-opus-4-20250514"
    assert base_routed.request.model == "fallback-model"
    assert request.model == "claude-opus-4-20250514"


def test_rotation_router_falls_back_when_primary_candidate_is_in_cooldown(settings):
    request = MessagesRequest(
        model="claude-opus-4-20250514",
        max_tokens=100,
        messages=[Message(role="user", content="hello")],
    )
    base_routed = ModelRouter(settings).resolve_messages_request(request)
    ring = ModelRing(
        "code",
        (
            ModelCandidate("open_router/deepseek/deepseek-v4-pro", priority=100),
            ModelCandidate("nvidia_nim/moonshotai/kimi-k2.5", priority=90),
        ),
    )
    engine = ProviderRotationEngine(cooldown_seconds=60)
    engine.mark_failure(
        "open_router/deepseek/deepseek-v4-pro",
        FailureCategory.RATE_LIMIT,
        now=100.0,
    )

    rotated = RotationRouter(engine).route_messages_request(
        base_routed,
        ring,
        now=110.0,
    )

    assert rotated.request.model == "moonshotai/kimi-k2.5"
    assert rotated.resolved.provider_id == "nvidia_nim"
    assert rotated.resolved.provider_model_ref == "nvidia_nim/moonshotai/kimi-k2.5"


def test_rotation_router_routes_token_count_request(settings):
    request = TokenCountRequest(
        model="claude-3-haiku-20240307",
        messages=[Message(role="user", content="hello")],
    )
    base_routed = ModelRouter(settings).resolve_token_count_request(request)
    ring = ModelRing(
        "fast",
        (
            ModelCandidate("groq/llama-3.3-70b-versatile", priority=100),
        ),
    )

    rotated = RotationRouter(ProviderRotationEngine()).route_token_count_request(
        base_routed,
        ring,
        now=100.0,
    )

    assert rotated.request.model == "llama-3.3-70b-versatile"
    assert rotated.resolved.provider_id == "groq"
    assert rotated.resolved.provider_model_ref == "groq/llama-3.3-70b-versatile"


def test_rotation_router_raises_when_ring_has_no_available_candidate(settings):
    request = MessagesRequest(
        model="claude-opus-4-20250514",
        max_tokens=100,
        messages=[Message(role="user", content="hello")],
    )
    base_routed = ModelRouter(settings).resolve_messages_request(request)
    ring = ModelRing(
        "code",
        (
            ModelCandidate("open_router/deepseek/deepseek-v4-pro", priority=100),
        ),
    )
    engine = ProviderRotationEngine()
    engine.mark_failure(
        "open_router/deepseek/deepseek-v4-pro",
        FailureCategory.QUOTA,
    )

    with pytest.raises(RuntimeError, match="No available provider/model candidate"):
        RotationRouter(engine).route_messages_request(base_routed, ring, now=100.0)
