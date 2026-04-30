import sqlite3

from api.rotation_engine import FailureCategory, HealthRecord, RotationState
from api.rotation_health_store import RotationHealthStore


def test_load_missing_health_database_returns_empty_dict(tmp_path):
    store = RotationHealthStore(tmp_path / "provider_health.db")

    assert store.load(now=100.0) == {}


def test_save_and_load_health_records_roundtrip(tmp_path):
    path = tmp_path / "provider_health.db"
    store = RotationHealthStore(path)

    health = {
        "nvidia_nim/model": HealthRecord(
            state=RotationState.ACTIVE,
            success_count=2,
            failure_count=1,
            last_failure=None,
            last_error=None,
        )
    }

    store.save(health, now=100.0)
    loaded = store.load(now=200.0)

    record = loaded["nvidia_nim/model"]
    assert record.state == RotationState.ACTIVE
    assert record.success_count == 2
    assert record.failure_count == 1
    assert record.last_failure is None
    assert record.last_error is None


def test_cooldown_is_persisted_as_remaining_seconds(tmp_path):
    path = tmp_path / "provider_health.db"
    store = RotationHealthStore(path)

    health = {
        "groq/fast": HealthRecord(
            state=RotationState.COOLDOWN,
            failure_count=1,
            cooldown_until=130.0,
            last_failure=FailureCategory.RATE_LIMIT,
            last_error="RateLimitError",
        )
    }

    store.save(health, now=100.0)

    with sqlite3.connect(path) as conn:
        row = conn.execute(
            """
            SELECT cooldown_remaining_seconds, last_failure, last_error
            FROM provider_health_current
            WHERE model_ref = 'groq/fast'
            """
        ).fetchone()

    assert row[0] == 30.0
    assert row[1] == "rate_limit"
    assert row[2] == "RateLimitError"

    loaded = store.load(now=500.0)
    record = loaded["groq/fast"]

    assert record.state == RotationState.COOLDOWN
    assert record.cooldown_until == 530.0
    assert record.last_failure == FailureCategory.RATE_LIMIT


def test_expired_cooldown_loads_as_degraded(tmp_path):
    path = tmp_path / "provider_health.db"

    store = RotationHealthStore(path)
    store.save(
        {
            "groq/fast": HealthRecord(
                state=RotationState.COOLDOWN,
                failure_count=1,
                cooldown_until=100.0,
                last_failure=FailureCategory.TIMEOUT,
                last_error="TimeoutError",
            )
        },
        now=100.0,
    )

    loaded = store.load(now=200.0)
    record = loaded["groq/fast"]

    assert record.state == RotationState.DEGRADED
    assert record.cooldown_until == 0.0
    assert record.last_failure == FailureCategory.TIMEOUT


def test_failure_event_is_recorded(tmp_path):
    path = tmp_path / "provider_health.db"
    store = RotationHealthStore(path)
    record = HealthRecord(
        state=RotationState.COOLDOWN,
        failure_count=1,
        last_failure=FailureCategory.OVERLOADED,
        last_error="OverloadedError",
    )

    store.record_failure_event(
        "nvidia_nim/model",
        record,
        failure_category=FailureCategory.OVERLOADED,
        error_type="OverloadedError",
    )

    with sqlite3.connect(path) as conn:
        row = conn.execute(
            """
            SELECT model_ref, event_type, state, failure_category, error_type
            FROM provider_health_events
            """
        ).fetchone()

    assert row == (
        "nvidia_nim/model",
        "failure",
        "cooldown",
        "overloaded",
        "OverloadedError",
    )


def test_success_event_is_recorded(tmp_path):
    path = tmp_path / "provider_health.db"
    store = RotationHealthStore(path)
    record = HealthRecord(state=RotationState.ACTIVE, success_count=1)

    store.record_success_event("google/gemini", record)

    with sqlite3.connect(path) as conn:
        row = conn.execute(
            """
            SELECT model_ref, event_type, state, failure_category, error_type
            FROM provider_health_events
            """
        ).fetchone()

    assert row == ("google/gemini", "success", "active", None, None)


def test_corrupt_health_database_returns_empty_dict(tmp_path):
    path = tmp_path / "provider_health.db"
    path.write_text("not sqlite", encoding="utf-8")

    assert RotationHealthStore(path).load(now=100.0) == {}


def test_unknown_failure_category_loads_as_unknown(tmp_path):
    path = tmp_path / "provider_health.db"
    store = RotationHealthStore(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as conn:
        store._ensure_schema(conn)
        conn.execute(
            """
            INSERT INTO provider_health_current (
                model_ref,
                state,
                success_count,
                failure_count,
                cooldown_remaining_seconds,
                last_failure,
                last_error,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "provider/model",
                "disabled",
                0,
                1,
                0,
                "future_category",
                "future error",
                "2026-01-01T00:00:00+00:00",
            ),
        )

    loaded = store.load(now=100.0)

    assert loaded["provider/model"].last_failure == FailureCategory.UNKNOWN


def test_list_events_returns_recent_events_newest_first(tmp_path):
    path = tmp_path / "provider_health.db"
    store = RotationHealthStore(path)

    store.record_success_event(
        "google/gemini",
        HealthRecord(state=RotationState.ACTIVE, success_count=1),
    )
    store.record_failure_event(
        "groq/fast",
        HealthRecord(
            state=RotationState.COOLDOWN,
            failure_count=1,
            last_failure=FailureCategory.RATE_LIMIT,
            last_error="RateLimitError",
        ),
        failure_category=FailureCategory.RATE_LIMIT,
        error_type="RateLimitError",
    )

    events = store.list_events(limit=1)

    assert len(events) == 1
    assert events[0]["model_ref"] == "groq/fast"
    assert events[0]["event_type"] == "failure"
    assert events[0]["failure_category"] == "rate_limit"


def test_list_events_missing_database_returns_empty_list(tmp_path):
    store = RotationHealthStore(tmp_path / "missing.db")

    assert store.list_events(limit=10) == []
