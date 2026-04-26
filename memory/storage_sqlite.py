"""SQLite storage backend for memory system."""

import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Handle missing loguru gracefully
try:
    from loguru import logger
except ImportError:
    class _FallbackLogger:
        def debug(self, *args, **kwargs): pass
        def info(self, *args, **kwargs): print(f"[INFO] {' '.join(str(a) for a in args)}", file=sys.stderr)
        def warning(self, *args, **kwargs): pass
        def error(self, *args, **kwargs): print(f"[ERROR] {' '.join(str(a) for a in args)}", file=sys.stderr)
    logger = _FallbackLogger()


class SQLiteStorage:
    """Manages SQLite database for conversation storage."""

    def __init__(self, db_path: Path | str = None):
        """Initialize SQLite storage.

        Args:
            db_path: Path to SQLite database file. Defaults to memory_store/memory.db
        """
        if db_path is None:
            db_path = Path(__file__).parent.parent / "memory_store" / "memory.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    summary TEXT
                );

                CREATE TABLE IF NOT EXISTS messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    model TEXT,
                    provider TEXT,
                    metadata TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS summaries (
                    summary_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL UNIQUE,
                    summary TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session
                    ON messages(session_id);
                CREATE INDEX IF NOT EXISTS idx_messages_timestamp
                    ON messages(timestamp);
                CREATE INDEX IF NOT EXISTS idx_messages_content
                    ON messages(content);
                """
            )
            conn.commit()
        logger.debug(f"SQLite database initialized at {self.db_path}")

    def create_session(self, session_id: str | None = None) -> str:
        """Create a new session.

        Args:
            session_id: Optional session ID. If None, generates UUID.

        Returns:
            The session ID.
        """
        if session_id is None:
            session_id = str(uuid.uuid4())

        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sessions (session_id, created_at, updated_at) VALUES (?, ?, ?)",
                (session_id, now, now),
            )
            conn.commit()
        logger.debug(f"Created session: {session_id}")
        return session_id

    def store_message(
        self,
        session_id: str,
        role: str,
        content: str,
        model: str | None = None,
        provider: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Store a message in the database.

        Args:
            session_id: The session ID.
            role: 'user' or 'assistant'.
            content: The message content.
            model: The model used.
            provider: The provider used.
            metadata: Optional metadata as dict.

        Returns:
            The message ID.
        """
        import json

        now = datetime.now(timezone.utc).isoformat()
        metadata_json = json.dumps(metadata) if metadata else None

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO messages
                   (session_id, timestamp, role, content, model, provider, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_id, now, role, content, model, provider, metadata_json),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            conn.commit()
            message_id = cursor.lastrowid

        logger.debug(f"Stored message {message_id} in session {session_id}")
        return message_id

    def get_session_messages(
        self, session_id: str, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Get messages for a session.

        Args:
            session_id: The session ID.
            limit: Optional limit on number of messages.

        Returns:
            List of message dictionaries.
        """
        import json

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            query = """SELECT message_id, timestamp, role, content, model, provider, metadata
                       FROM messages WHERE session_id = ? ORDER BY timestamp ASC"""
            params = [session_id]
            if limit:
                query += " LIMIT ?"
                params.append(limit)

            rows = conn.execute(query, params).fetchall()

        messages = []
        for row in rows:
            msg = dict(row)
            if msg.get("metadata"):
                try:
                    msg["metadata"] = json.loads(msg["metadata"])
                except json.JSONDecodeError:
                    pass
            messages.append(msg)

        return messages

    def get_recent_sessions(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get most recent sessions.

        Args:
            limit: Number of sessions to return.

        Returns:
            List of session dictionaries.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT s.session_id, s.created_at, s.updated_at, s.summary,
                          COUNT(m.message_id) as message_count
                   FROM sessions s
                   LEFT JOIN messages m ON s.session_id = m.session_id
                   GROUP BY s.session_id
                   ORDER BY s.updated_at DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()

        return [dict(row) for row in rows]

    def store_summary(self, session_id: str, summary: str) -> int:
        """Store or update a session summary.

        Args:
            session_id: The session ID.
            summary: The summary text.

        Returns:
            The summary ID.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO summaries (session_id, summary)
                   VALUES (?, ?)
                   ON CONFLICT(session_id)
                   DO UPDATE SET summary = excluded.summary, created_at = CURRENT_TIMESTAMP""",
                (session_id, summary),
            )
            conn.execute(
                "UPDATE sessions SET summary = ? WHERE session_id = ?",
                (summary, session_id),
            )
            conn.commit()
            return cursor.lastrowid

    def search_messages(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search messages using LIKE pattern.

        Args:
            query: The search query.
            limit: Maximum results to return.

        Returns:
            List of matching message dictionaries.
        """
        import json

        pattern = f"%{query}%"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT m.message_id, m.session_id, m.timestamp, m.role,
                          m.content, m.model, m.provider, m.metadata
                   FROM messages m
                   WHERE m.content LIKE ?
                   ORDER BY m.timestamp DESC
                   LIMIT ?""",
                (pattern, limit),
            ).fetchall()

        results = []
        for row in rows:
            msg = dict(row)
            if msg.get("metadata"):
                try:
                    msg["metadata"] = json.loads(msg["metadata"])
                except json.JSONDecodeError:
                    pass
            results.append(msg)

        return results

    def get_message_count(self, session_id: str | None = None) -> int:
        """Get message count.

        Args:
            session_id: Optional session ID. If None, returns total count.

        Returns:
            Number of messages.
        """
        with sqlite3.connect(self.db_path) as conn:
            if session_id:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE session_id = ?",
                    (session_id,),
                )
            else:
                cursor = conn.execute("SELECT COUNT(*) FROM messages")
            return cursor.fetchone()[0]
