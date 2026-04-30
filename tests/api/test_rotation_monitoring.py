from config.settings import Settings

from api.rotation_engine import (
    FailureCategory,
    ProviderRotationEngine,
)
from api.rotation_health_store import RotationHealthStore
from api.rotation_monitoring import build_provider_rotation_status


def test_rotation_monitoring_reports_engine_snapshot_without_store():
    settings = Settings()
    settings.enable_provider_rotation = False
    settings.provider_rotation_profile = "stable-agentic"
    settings.provider_rotation_config = "config/model_rings.yaml"
    settings.provider_rotation_health_db = "memory_store/provider_health.db"

    engine = ProviderRotationEngine()
    engine.mark_failure(
        "groq/llama-3.3-70b-versatile",
        FailureCategory.RATE_LIMIT,
        message="RateLimitError",
        now=100.0,
    )

    status = build_provider_rotation_status(
        settings=settings,
        rotation_engine=engine,
        events_limit=10,
    )

    assert status["enabled"] is False
    assert status["profile"] == "stable-agentic"
    assert status["rings_loaded"] is False
    assert status["summary"]["total_models"] == 1
    assert status["summary"]["states"] == {"cooldown": 1}
    assert status["summary"]["total_failure_count"] == 1
    assert status["events"] == []


def test_rotation_monitoring_includes_recent_store_events(tmp_path):
    settings = Settings()
    settings.enable_provider_rotation = True
    settings.provider_rotation_profile = "fast-resilient"
    settings.provider_rotation_config = "config/model_rings.yaml"
    settings.provider_rotation_health_db = str(tmp_path / "provider_health.db")

    store = RotationHealthStore(settings.provider_rotation_health_db)
    engine = ProviderRotationEngine(health_store=store)
    engine.mark_failure(
        "groq/llama-3.3-70b-versatile",
        FailureCategory.RATE_LIMIT,
        message="RateLimitError",
        now=100.0,
    )

    status = build_provider_rotation_status(
        settings=settings,
        rotation_engine=engine,
        health_store=store,
        events_limit=5,
    )

    assert status["enabled"] is True
    assert status["summary"]["events_returned"] == 1
    assert status["events"][0]["model_ref"] == "groq/llama-3.3-70b-versatile"
    assert status["events"][0]["event_type"] == "failure"
    assert status["events"][0]["failure_category"] == "rate_limit"
