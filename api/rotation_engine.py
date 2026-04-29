"""Provider/model rotation primitives for resilient routing.

This module is intentionally independent from the live API service layer.
It models candidate selection, health state, cooldowns, and permanent
disable rules. Integration into ``api.services`` should happen only after
these primitives are covered by unit tests.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class RotationState(str, Enum):
    """Runtime availability state for a provider/model candidate."""

    ACTIVE = "active"
    DEGRADED = "degraded"
    COOLDOWN = "cooldown"
    DISABLED = "disabled"


class FailureCategory(str, Enum):
    """Normalized failure categories used by the rotation engine."""

    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    OVERLOADED = "overloaded"
    PROVIDER_ERROR = "provider_error"
    AUTHENTICATION = "authentication"
    QUOTA = "quota"
    MODEL_NOT_FOUND = "model_not_found"
    INVALID_REQUEST = "invalid_request"
    UNKNOWN = "unknown"


def failure_category_from_exception(exc: BaseException) -> FailureCategory:
    """Map C-f-C/provider exceptions to rotation failure categories.

    This function intentionally depends only on the public provider exception
    hierarchy and conservative status-code inspection, so the rotation engine
    can classify real runtime failures without importing service-layer code.
    """
    from providers.exceptions import (
        APIError,
        AuthenticationError,
        InvalidRequestError,
        OverloadedError,
        ProviderError,
        RateLimitError,
    )

    if isinstance(exc, AuthenticationError):
        return FailureCategory.AUTHENTICATION
    if isinstance(exc, RateLimitError):
        return FailureCategory.RATE_LIMIT
    if isinstance(exc, OverloadedError):
        return FailureCategory.OVERLOADED
    if isinstance(exc, InvalidRequestError):
        return FailureCategory.INVALID_REQUEST

    status_code = getattr(exc, "status_code", None)
    message = str(getattr(exc, "message", exc)).lower()

    if status_code in (401, 403):
        return FailureCategory.AUTHENTICATION
    if status_code == 429:
        return FailureCategory.RATE_LIMIT
    if status_code == 402:
        return FailureCategory.QUOTA
    if status_code == 404:
        return FailureCategory.MODEL_NOT_FOUND
    if status_code in (408, 504):
        return FailureCategory.TIMEOUT
    if status_code in (502, 503, 529):
        return FailureCategory.OVERLOADED

    if isinstance(exc, APIError):
        return FailureCategory.PROVIDER_ERROR
    if isinstance(exc, ProviderError):
        if "quota" in message or "billing" in message or "insufficient credit" in message:
            return FailureCategory.QUOTA
        if "model" in message and ("not found" in message or "not_found" in message):
            return FailureCategory.MODEL_NOT_FOUND
        if "timeout" in message or "timed out" in message:
            return FailureCategory.TIMEOUT
        return FailureCategory.PROVIDER_ERROR

    if "timeout" in message or "timed out" in message:
        return FailureCategory.TIMEOUT
    return FailureCategory.UNKNOWN


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    """A selectable provider/model candidate inside a rotation ring."""

    model_ref: str
    priority: int = 100
    weight: float = 1.0
    capabilities: tuple[str, ...] = ()

    @property
    def provider_id(self) -> str:
        """Return the provider prefix from ``provider/model`` references."""
        if "/" not in self.model_ref:
            raise ValueError("model_ref must include a provider prefix")
        return self.model_ref.split("/", 1)[0]

    @property
    def provider_model(self) -> str:
        """Return the provider-native model name without the provider prefix."""
        if "/" not in self.model_ref:
            raise ValueError("model_ref must include a provider prefix")
        return self.model_ref.split("/", 1)[1]


@dataclass(slots=True)
class HealthRecord:
    """Mutable runtime health for one candidate."""

    state: RotationState = RotationState.ACTIVE
    success_count: int = 0
    failure_count: int = 0
    cooldown_until: float = 0.0
    last_failure: FailureCategory | None = None
    last_error: str | None = None

    def is_available(self, *, now: float | None = None) -> bool:
        """Return whether the candidate can be selected now."""
        current = time.monotonic() if now is None else now
        if self.state == RotationState.DISABLED:
            return False
        if self.state == RotationState.COOLDOWN:
            return current >= self.cooldown_until
        return True

    def refresh_after_cooldown(self, *, now: float | None = None) -> None:
        """Move expired cooldown records back to degraded state."""
        current = time.monotonic() if now is None else now
        if self.state == RotationState.COOLDOWN and current >= self.cooldown_until:
            self.state = RotationState.DEGRADED
            self.cooldown_until = 0.0


@dataclass(slots=True)
class ModelRing:
    """A named group of ordered candidates for one task class."""

    name: str
    candidates: tuple[ModelCandidate, ...]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ring name must be non-empty")
        if not self.candidates:
            raise ValueError("ring must contain at least one candidate")


@dataclass(slots=True)
class ProviderRotationEngine:
    """Select candidates and update their runtime health."""

    cooldown_seconds: float = 60.0
    degraded_penalty: float = 25.0
    _health: dict[str, HealthRecord] = field(default_factory=dict)

    def health_for(self, model_ref: str) -> HealthRecord:
        """Return the mutable health record for a model reference."""
        return self._health.setdefault(model_ref, HealthRecord())

    def select(self, ring: ModelRing, *, now: float | None = None) -> ModelCandidate:
        """Select the best currently available candidate from a ring."""
        current = time.monotonic() if now is None else now
        available: list[tuple[float, ModelCandidate]] = []

        for candidate in ring.candidates:
            health = self.health_for(candidate.model_ref)
            health.refresh_after_cooldown(now=current)
            if not health.is_available(now=current):
                continue
            available.append((self._score(candidate, health), candidate))

        if not available:
            raise RuntimeError(f"No available provider/model candidate for ring '{ring.name}'")

        available.sort(key=lambda item: item[0], reverse=True)
        return available[0][1]

    def mark_success(self, model_ref: str) -> None:
        """Record a successful call and restore active state after recovery."""
        health = self.health_for(model_ref)
        health.success_count += 1
        health.last_error = None
        health.last_failure = None
        health.cooldown_until = 0.0
        health.state = RotationState.ACTIVE

    def mark_failure(
        self,
        model_ref: str,
        category: FailureCategory,
        *,
        message: str | None = None,
        now: float | None = None,
    ) -> None:
        """Record a failure and update state according to severity."""
        current = time.monotonic() if now is None else now
        health = self.health_for(model_ref)
        health.failure_count += 1
        health.last_failure = category
        health.last_error = message

        if category in {
            FailureCategory.AUTHENTICATION,
            FailureCategory.QUOTA,
            FailureCategory.MODEL_NOT_FOUND,
            FailureCategory.INVALID_REQUEST,
        }:
            health.state = RotationState.DISABLED
            health.cooldown_until = 0.0
            return

        if category in {
            FailureCategory.RATE_LIMIT,
            FailureCategory.TIMEOUT,
            FailureCategory.OVERLOADED,
            FailureCategory.PROVIDER_ERROR,
            FailureCategory.UNKNOWN,
        }:
            health.state = RotationState.COOLDOWN
            health.cooldown_until = current + self.cooldown_seconds
            return

    def snapshot(self) -> dict[str, dict[str, object]]:
        """Return a serializable health snapshot for logs or monitoring."""
        return {
            model_ref: {
                "state": record.state.value,
                "success_count": record.success_count,
                "failure_count": record.failure_count,
                "cooldown_until": record.cooldown_until,
                "last_failure": record.last_failure.value if record.last_failure else None,
                "last_error": record.last_error,
            }
            for model_ref, record in sorted(self._health.items())
        }

    def _score(self, candidate: ModelCandidate, health: HealthRecord) -> float:
        score = float(candidate.priority) * float(candidate.weight)
        score += float(health.success_count)
        score -= float(health.failure_count) * 5.0
        if health.state == RotationState.DEGRADED:
            score -= self.degraded_penalty
        return score
