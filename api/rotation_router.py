"""Rotation-aware routing helpers.

This module bridges the existing ``ModelRouter`` output with the standalone
``ProviderRotationEngine``. It is intentionally side-effect free and is not
wired into ``ClaudeProxyService`` yet.
"""

from __future__ import annotations

from dataclasses import replace

from api.model_router import (
    ResolvedModel,
    RoutedMessagesRequest,
    RoutedTokenCountRequest,
)
from providers.rotation import ModelCandidate, ModelRing, ProviderRotationEngine


def resolved_from_candidate(
    resolved: ResolvedModel, candidate: ModelCandidate
) -> ResolvedModel:
    """Return a ``ResolvedModel`` updated with a selected rotation candidate."""
    return replace(
        resolved,
        provider_id=candidate.provider_id,
        provider_model=candidate.provider_model,
        provider_model_ref=candidate.model_ref,
    )


class RotationRouter:
    """Apply a rotation engine decision to already-routed requests."""

    def __init__(self, engine: ProviderRotationEngine):
        self._engine = engine

    def route_messages_request(
        self,
        routed: RoutedMessagesRequest,
        ring: ModelRing,
        *,
        now: float | None = None,
    ) -> RoutedMessagesRequest:
        """Return a messages request routed to the selected ring candidate."""
        candidate = self._engine.select(ring, now=now)
        resolved = resolved_from_candidate(routed.resolved, candidate)
        request = routed.request.model_copy(
            update={"model": candidate.provider_model}, deep=True
        )
        return RoutedMessagesRequest(request=request, resolved=resolved)

    def route_token_count_request(
        self,
        routed: RoutedTokenCountRequest,
        ring: ModelRing,
        *,
        now: float | None = None,
    ) -> RoutedTokenCountRequest:
        """Return a token-count request routed to the selected ring candidate."""
        candidate = self._engine.select(ring, now=now)
        resolved = resolved_from_candidate(routed.resolved, candidate)
        request = routed.request.model_copy(
            update={"model": candidate.provider_model}, deep=True
        )
        return RoutedTokenCountRequest(request=request, resolved=resolved)
