"""Provider rotation monitoring helpers."""

from __future__ import annotations

from typing import Any

from config.settings import Settings

from .rotation_engine import ProviderRotationEngine


def build_provider_rotation_status(
    *,
    settings: Settings,
    rotation_engine: ProviderRotationEngine,
    health_store: Any | None = None,
    model_rings_config: Any | None = None,
    events_limit: int = 50,
) -> dict[str, Any]:
    """Build a serializable provider-rotation monitoring payload."""
    health_snapshot = rotation_engine.snapshot()
    safe_events_limit = _normalize_limit(events_limit)
    events = _recent_events(health_store, limit=safe_events_limit)

    return {
        "enabled": bool(settings.enable_provider_rotation),
        "profile": settings.provider_rotation_profile,
        "config_path": settings.provider_rotation_config,
        "health_db": settings.provider_rotation_health_db,
        "rings_loaded": model_rings_config is not None,
        "ring": _ring_summary(settings, model_rings_config),
        "summary": _health_summary(health_snapshot, events_count=len(events)),
        "health": health_snapshot,
        "events": events,
    }


def _normalize_limit(value: int) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return 50
    return max(0, min(limit, 500))


def _recent_events(health_store: Any | None, *, limit: int) -> list[dict[str, Any]]:
    if health_store is None or limit <= 0:
        return []

    list_events = getattr(health_store, "list_events", None)
    if not callable(list_events):
        return []

    return list_events(limit=limit)


def _health_summary(
    health_snapshot: dict[str, dict[str, object]],
    *,
    events_count: int,
) -> dict[str, Any]:
    states: dict[str, int] = {}
    total_success_count = 0
    total_failure_count = 0

    for record in health_snapshot.values():
        state = str(record.get("state") or "unknown")
        states[state] = states.get(state, 0) + 1
        total_success_count += int(record.get("success_count") or 0)
        total_failure_count += int(record.get("failure_count") or 0)

    return {
        "total_models": len(health_snapshot),
        "states": states,
        "total_success_count": total_success_count,
        "total_failure_count": total_failure_count,
        "events_returned": events_count,
    }


def _ring_summary(
    settings: Settings,
    model_rings_config: Any | None,
) -> dict[str, Any] | None:
    if model_rings_config is None:
        return None

    try:
        profile = model_rings_config.get_profile(settings.provider_rotation_profile)
        ring = model_rings_config.get_ring(profile.default_ring)
    except Exception as exc:  # pragma: no cover - defensive monitoring fallback
        return {"error": type(exc).__name__}

    return {
        "profile": settings.provider_rotation_profile,
        "default_ring": profile.default_ring,
        "candidates": [
            {
                "model_ref": candidate.model_ref,
                "provider_id": candidate.provider_id,
                "provider_model": candidate.provider_model,
                "priority": candidate.priority,
                "weight": candidate.weight,
            }
            for candidate in ring.candidates
        ],
    }
