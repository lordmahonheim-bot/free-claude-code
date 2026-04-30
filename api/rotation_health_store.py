"""SQLite persistence for provider rotation health.

The rotation engine uses time.monotonic() for in-process cooldown decisions.
Monotonic timestamps are not stable across process restarts, so this store
persists cooldowns as remaining seconds and reconstructs monotonic deadlines
when records are loaded.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from api.rotation_engine import FailureCategory, HealthRecord, RotationState


SCHEMA_VERSION = 1


class RotationHealthStore:
    """Persist provider/model health records to SQLite."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self, *, now: float | None = None) -> dict[str, HealthRecord]:
        """Load current health records from SQLite.

        Missing databases are treated as an empty state.
        """
        if not self.path.exists():
            return {}

        current = time.monotonic() if now is None else now

        try:
            with self._connect() as conn:
                self._ensure_schema(conn)
                rows = conn.execute(
                    """
                    SELECT
                        model_ref,
                        state,
                        success_count,
                        failure_count,
                        cooldown_remaining_seconds,
                        last_failure,
                        last_error
                    FROM provider_health_current
                    ORDER BY model_ref
                    """
                ).fetchall()
        except sqlite3.DatabaseError:
            return {}

        health: dict[str, HealthRecord] = {}
        for row in rows:
            record = self._record_from_row(row, now=current)
            if record is not None:
                health[str(row["model_ref"])] = record
        return health

    def save(
        self,
        health: dict[str, HealthRecord],
        *,
        now: float | None = None,
    ) -> None:
        """Persist the current health snapshot."""
        current = time.monotonic() if now is None else now
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as conn:
            self._ensure_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM provider_health_current")
            for model_ref, record in sorted(health.items()):
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
                        model_ref,
                        record.state.value,
                        int(record.success_count),
                        int(record.failure_count),
                        self._cooldown_remaining(record, now=current),
                        record.last_failure.value if record.last_failure else None,
                        record.last_error,
                        _utc_now_iso(),
                    ),
                )
            conn.commit()

    def record_success_event(self, model_ref: str, record: HealthRecord) -> None:
        """Append a success event for monitoring and future scoring."""
        self._append_event(
            model_ref=model_ref,
            event_type="success",
            state=record.state,
            failure_category=None,
            error_type=None,
        )

    def record_failure_event(
        self,
        model_ref: str,
        record: HealthRecord,
        *,
        failure_category: FailureCategory | None,
        error_type: str | None,
    ) -> None:
        """Append a failure event for monitoring and future scoring."""
        self._append_event(
            model_ref=model_ref,
            event_type="failure",
            state=record.state,
            failure_category=failure_category,
            error_type=error_type,
        )

    def list_events(
        self,
        *,
        limit: int = 50,
        model_ref: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return recent provider-health events for monitoring."""
        try:
            safe_limit = max(0, min(int(limit), 500))
        except (TypeError, ValueError):
            safe_limit = 50

        if safe_limit <= 0 or not self.path.exists():
            return []

        try:
            with self._connect() as conn:
                self._ensure_schema(conn)
                params: list[Any] = []
                where_clause = ""
                if model_ref is not None:
                    where_clause = "WHERE model_ref = ?"
                    params.append(model_ref)
                params.append(safe_limit)
                rows = conn.execute(
                    f"""
                    SELECT
                        id,
                        model_ref,
                        event_type,
                        state,
                        failure_category,
                        error_type,
                        created_at
                    FROM provider_health_events
                    {where_clause}
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    params,
                ).fetchall()
        except sqlite3.DatabaseError:
            return []

        return [dict(row) for row in rows]

    def _append_event(
        self,
        *,
        model_ref: str,
        event_type: str,
        state: RotationState,
        failure_category: FailureCategory | None,
        error_type: str | None,
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as conn:
            self._ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO provider_health_events (
                    model_ref,
                    event_type,
                    state,
                    failure_category,
                    error_type,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    model_ref,
                    event_type,
                    state.value,
                    failure_category.value if failure_category else None,
                    error_type,
                    _utc_now_iso(),
                ),
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS provider_health_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO provider_health_meta (key, value)
            VALUES ('schema_version', ?)
            """,
            (str(SCHEMA_VERSION),),
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS provider_health_current (
                model_ref TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                success_count INTEGER NOT NULL DEFAULT 0,
                failure_count INTEGER NOT NULL DEFAULT 0,
                cooldown_remaining_seconds REAL NOT NULL DEFAULT 0,
                last_failure TEXT,
                last_error TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS provider_health_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_ref TEXT NOT NULL,
                event_type TEXT NOT NULL,
                state TEXT NOT NULL,
                failure_category TEXT,
                error_type TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_provider_health_events_model_ref
            ON provider_health_events(model_ref)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_provider_health_events_created_at
            ON provider_health_events(created_at)
            """
        )
        conn.commit()

    def _record_from_row(
        self,
        row: sqlite3.Row,
        *,
        now: float,
    ) -> HealthRecord | None:
        try:
            state = RotationState(str(row["state"]))
        except ValueError:
            return None

        last_failure = _parse_failure_category(row["last_failure"])
        cooldown_remaining = _safe_float(row["cooldown_remaining_seconds"])

        cooldown_until = 0.0
        if state == RotationState.COOLDOWN:
            if cooldown_remaining <= 0:
                state = RotationState.DEGRADED
            else:
                cooldown_until = now + cooldown_remaining

        return HealthRecord(
            state=state,
            success_count=max(0, _safe_int(row["success_count"])),
            failure_count=max(0, _safe_int(row["failure_count"])),
            cooldown_until=cooldown_until,
            last_failure=last_failure,
            last_error=_safe_optional_str(row["last_error"]),
        )

    def _cooldown_remaining(self, record: HealthRecord, *, now: float) -> float:
        if record.state != RotationState.COOLDOWN:
            return 0.0
        return max(0.0, float(record.cooldown_until) - now)


def _parse_failure_category(value: Any) -> FailureCategory | None:
    if value is None:
        return None
    try:
        return FailureCategory(str(value))
    except ValueError:
        return FailureCategory.UNKNOWN


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
