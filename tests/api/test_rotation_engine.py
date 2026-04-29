import pytest

from providers.exceptions import (
    APIError,
    AuthenticationError,
    InvalidRequestError,
    OverloadedError,
    ProviderError,
    RateLimitError,
)

from api.rotation_engine import (
    FailureCategory,
    failure_category_from_exception,
    ModelCandidate,
    ModelRing,
    ProviderRotationEngine,
    RotationState,
)


def test_candidate_splits_provider_and_model():
    candidate = ModelCandidate("nvidia_nim/moonshotai/kimi-k2.5")

    assert candidate.provider_id == "nvidia_nim"
    assert candidate.provider_model == "moonshotai/kimi-k2.5"


def test_candidate_requires_provider_prefix():
    candidate = ModelCandidate("missing-prefix")

    with pytest.raises(ValueError, match="provider prefix"):
        _ = candidate.provider_id


def test_ring_requires_candidates():
    with pytest.raises(ValueError, match="at least one candidate"):
        ModelRing("empty", ())


def test_select_prefers_highest_scored_available_candidate():
    ring = ModelRing(
        "code",
        (
            ModelCandidate("groq/fast", priority=50),
            ModelCandidate("nvidia_nim/strong", priority=100),
        ),
    )
    engine = ProviderRotationEngine()

    selected = engine.select(ring, now=100.0)

    assert selected.model_ref == "nvidia_nim/strong"


def test_rate_limit_moves_candidate_to_cooldown_and_fallback_is_selected():
    ring = ModelRing(
        "code",
        (
            ModelCandidate("nvidia_nim/strong", priority=100),
            ModelCandidate("open_router/fallback", priority=90),
        ),
    )
    engine = ProviderRotationEngine(cooldown_seconds=30)

    engine.mark_failure(
        "nvidia_nim/strong",
        FailureCategory.RATE_LIMIT,
        message="429",
        now=100.0,
    )

    assert engine.health_for("nvidia_nim/strong").state == RotationState.COOLDOWN
    assert engine.select(ring, now=110.0).model_ref == "open_router/fallback"


def test_expired_cooldown_returns_candidate_as_degraded():
    ring = ModelRing(
        "code",
        (
            ModelCandidate("nvidia_nim/strong", priority=100),
            ModelCandidate("open_router/fallback", priority=50),
        ),
    )
    engine = ProviderRotationEngine(cooldown_seconds=30)

    engine.mark_failure("nvidia_nim/strong", FailureCategory.TIMEOUT, now=100.0)

    selected = engine.select(ring, now=131.0)

    assert selected.model_ref == "nvidia_nim/strong"
    assert engine.health_for("nvidia_nim/strong").state == RotationState.DEGRADED


def test_authentication_failure_disables_candidate():
    ring = ModelRing(
        "code",
        (
            ModelCandidate("nvidia_nim/bad-key", priority=100),
            ModelCandidate("open_router/fallback", priority=90),
        ),
    )
    engine = ProviderRotationEngine()

    engine.mark_failure(
        "nvidia_nim/bad-key",
        FailureCategory.AUTHENTICATION,
        message="401",
    )

    assert engine.health_for("nvidia_nim/bad-key").state == RotationState.DISABLED
    assert engine.select(ring, now=100.0).model_ref == "open_router/fallback"


def test_success_restores_active_state():
    engine = ProviderRotationEngine()

    engine.mark_failure("nvidia_nim/model", FailureCategory.OVERLOADED, now=100.0)
    engine.mark_success("nvidia_nim/model")

    health = engine.health_for("nvidia_nim/model")
    assert health.state == RotationState.ACTIVE
    assert health.success_count == 1
    assert health.last_failure is None
    assert health.last_error is None


def test_all_candidates_unavailable_raises_clear_error():
    ring = ModelRing(
        "code",
        (
            ModelCandidate("nvidia_nim/a"),
            ModelCandidate("open_router/b"),
        ),
    )
    engine = ProviderRotationEngine()
    engine.mark_failure("nvidia_nim/a", FailureCategory.QUOTA)
    engine.mark_failure("open_router/b", FailureCategory.MODEL_NOT_FOUND)

    with pytest.raises(RuntimeError, match="No available provider/model candidate"):
        engine.select(ring, now=100.0)


def test_snapshot_is_serializable_shape():
    engine = ProviderRotationEngine()
    engine.mark_failure("groq/fast", FailureCategory.RATE_LIMIT, message="429", now=10.0)

    snapshot = engine.snapshot()

    assert snapshot["groq/fast"]["state"] == "cooldown"
    assert snapshot["groq/fast"]["failure_count"] == 1
    assert snapshot["groq/fast"]["last_failure"] == "rate_limit"
    assert snapshot["groq/fast"]["last_error"] == "429"


def test_failure_category_maps_provider_exception_types():
    assert failure_category_from_exception(AuthenticationError("bad key")) == FailureCategory.AUTHENTICATION
    assert failure_category_from_exception(RateLimitError("too many")) == FailureCategory.RATE_LIMIT
    assert failure_category_from_exception(OverloadedError("overloaded")) == FailureCategory.OVERLOADED
    assert failure_category_from_exception(InvalidRequestError("bad request")) == FailureCategory.INVALID_REQUEST
    assert failure_category_from_exception(APIError("provider failed", status_code=500)) == FailureCategory.PROVIDER_ERROR


def test_failure_category_maps_status_codes():
    assert failure_category_from_exception(APIError("payment required", status_code=402)) == FailureCategory.QUOTA
    assert failure_category_from_exception(APIError("missing model", status_code=404)) == FailureCategory.MODEL_NOT_FOUND
    assert failure_category_from_exception(APIError("gateway timeout", status_code=504)) == FailureCategory.TIMEOUT
    assert failure_category_from_exception(APIError("bad gateway", status_code=502)) == FailureCategory.OVERLOADED


def test_failure_category_uses_message_fallbacks_for_provider_errors():
    assert failure_category_from_exception(ProviderError("insufficient credit")) == FailureCategory.QUOTA
    assert failure_category_from_exception(ProviderError("model_not_found")) == FailureCategory.MODEL_NOT_FOUND
    assert failure_category_from_exception(ProviderError("request timed out")) == FailureCategory.TIMEOUT


def test_failure_category_unknown_for_generic_exception():
    assert failure_category_from_exception(RuntimeError("boom")) == FailureCategory.UNKNOWN
