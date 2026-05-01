"""SQLite persistence store for Persistent Memory Core V2."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from .schema import SCHEMA_SQL


class PersistentMemoryStore:
    """Durable SQLite store for C-f-C persistent memory."""

    def __init__(self, db_path: str | Path = "memory_store/persistent_memory_v2.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def _init_db(self) -> None:
        with self._connect() as con:
            con.executescript(SCHEMA_SQL)

    @staticmethod
    def _json(data: dict[str, Any] | None) -> str:
        return json.dumps(data or {}, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:16]}"

    def get_or_create_session(
        self,
        source_session_id: str | None = None,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        with self._connect() as con:
            if source_session_id:
                row = con.execute(
                    "SELECT id FROM memory_sessions WHERE source_session_id = ? LIMIT 1",
                    (source_session_id,),
                ).fetchone()
                if row:
                    return str(row["id"])

            session_id = self._id("sess")
            con.execute(
                """
                INSERT INTO memory_sessions(id, source_session_id, title, metadata_json)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, source_session_id, title, self._json(metadata)),
            )
            return session_id

    def store_turn(
        self,
        session_id: str,
        user_text: str,
        assistant_text: str = "",
        provider: str | None = None,
        model: str | None = None,
        status: str = "completed",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        turn_id = self._id("turn")
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO memory_turns(
                    id, session_id, user_text, assistant_text,
                    provider, model, status, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    turn_id,
                    session_id,
                    user_text or "",
                    assistant_text or "",
                    provider,
                    model,
                    status,
                    self._json(metadata),
                ),
            )
            con.execute(
                "UPDATE memory_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (session_id,),
            )
        return turn_id

    def add_event(self, kind: str, payload: dict[str, Any] | None = None) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT INTO memory_events(kind, payload_json) VALUES (?, ?)",
                (kind, self._json(payload)),
            )

    def recent_turns(self, limit: int = 6) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT * FROM memory_turns
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        pattern = f"%{query}%"
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT * FROM memory_turns
                WHERE user_text LIKE ? OR assistant_text LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (pattern, pattern, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> dict[str, int]:
        with self._connect() as con:
            return {
                "sessions": con.execute("SELECT COUNT(*) FROM memory_sessions").fetchone()[0],
                "turns": con.execute("SELECT COUNT(*) FROM memory_turns").fetchone()[0],
                "events": con.execute("SELECT COUNT(*) FROM memory_events").fetchone()[0],
            }
