"""Memory manager - orchestrates storage, export, and retrieval."""

import re
import sys
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

# Handle missing loguru gracefully
try:
    from loguru import logger
except ImportError:
    class _FallbackLogger:
        def debug(self, *args, **kwargs): pass
        def info(self, *args, **kwargs): pass
        def warning(self, *args, **kwargs): pass
        def error(self, *args, **kwargs): print(f"[ERROR] {' '.join(str(a) for a in args)}", file=sys.stderr)
    logger = _FallbackLogger()

from .exporter_md import MarkdownExporter
from .retriever import MemoryRetriever
from .storage_sqlite import SQLiteStorage


class SessionTracker:
    """Tracks active sessions with thread-safe operations."""

    def __init__(self):
        """Initialize the tracker."""
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def get_or_create(self, session_hint: str | None = None) -> str:
        """Get existing session or create new one.

        Args:
            session_hint: Optional hint for session ID.

        Returns:
            The session ID.
        """
        with self._lock:
            if session_hint and session_hint in self._sessions:
                self._sessions[session_hint]["last_active"] = datetime.now(timezone.utc)
                return session_hint

            session_id = session_hint or str(uuid.uuid4())
            self._sessions[session_id] = {
                "created": datetime.now(timezone.utc),
                "last_active": datetime.now(timezone.utc),
            }
            return session_id

    def get_active_session(self) -> str | None:
        """Get the most recently active session ID.

        Returns:
            Session ID or None if no active sessions.
        """
        with self._lock:
            if not self._sessions:
                return None
            sorted_sessions = sorted(
                self._sessions.items(),
                key=lambda x: x[1]["last_active"],
                reverse=True,
            )
            return sorted_sessions[0][0]


class MemoryManager:
    """Main memory orchestrator - integrates with the proxy."""

    def __init__(
        self,
        storage: SQLiteStorage = None,
        exporter: MarkdownExporter = None,
        retriever: MemoryRetriever = None,
        enable_export: bool = True,
    ):
        """Initialize the memory manager.

        Args:
            storage: SQLite storage instance.
            exporter: Markdown exporter instance.
            retriever: Memory retriever instance.
            enable_export: Whether to enable Markdown export.
        """
        self.storage = storage or SQLiteStorage()
        self.exporter = exporter if exporter else MarkdownExporter()
        self.retriever = retriever if retriever else MemoryRetriever(self.storage)
        self.enable_export = enable_export

        self._tracker = SessionTracker()
        self._summary_callback: Callable[[str, list[dict]], str] | None = None

        logger.info("Memory manager initialized")

    def set_summary_generator(
        self, callback: Callable[[str, list[dict]], str]
    ) -> None:
        """Set callback for generating session summaries.

        Args:
            callback: Function that takes (session_id, messages) and returns summary string.
        """
        self._summary_callback = callback

    def get_or_create_session(self, session_id: str | None = None) -> str:
        """Get or create a session.

        Args:
            session_id: Optional existing session ID.

        Returns:
            The session ID.
        """
        if not session_id:
            session_id = self._tracker.get_active_session()
            if not session_id:
                session_id = str(uuid.uuid4())

        sid = self._tracker.get_or_create(session_id)
        # Ensure exists in storage
        self.storage.create_session(sid)
        return sid

    def store_interaction(
        self,
        session_id: str,
        user_message: str,
        assistant_response: str,
        model: str | None = None,
        provider: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[int, int]:
        """Store a complete user/assistant interaction.

        Args:
            session_id: The session ID.
            user_message: User's message content.
            assistant_response: Assistant's response content.
            model: Model used.
            provider: Provider used.
            metadata: Optional metadata.

        Returns:
            Tuple of (user_message_id, assistant_message_id).
        """
        # Ensure session exists
        self.storage.create_session(session_id)

        # Store user message
        user_id = self.storage.store_message(
            session_id=session_id,
            role="user",
            content=user_message,
            model=model,
            provider=provider,
            metadata=metadata,
        )

        # Extract text from assistant response (if structured)
        assistant_text = self._extract_text(assistant_response)

        # Store assistant message
        assistant_id = self.storage.store_message(
            session_id=session_id,
            role="assistant",
            content=assistant_text,
            model=model,
            provider=provider,
            metadata=metadata,
        )

        logger.debug(f"Stored interaction in session {session_id[:8]}")

        # Update markdown export if enabled
        if self.enable_export:
            self._export_message(session_id)

        return user_id, assistant_id

    def _extract_text(self, content: str | dict | list) -> str:
        """Extract text content from various formats.

        Args:
            content: Content that might be string, dict, or list of blocks.

        Returns:
            Extracted text.
        """
        if isinstance(content, str):
            return content

        if isinstance(content, dict):
            if "content" in content:
                return self._extract_text(content["content"])
            return str(content)

        if isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text" and "text" in item:
                        texts.append(item["text"])
                    elif "content" in item:
                        texts.append(self._extract_text(item["content"]))
                elif isinstance(item, str):
                    texts.append(item)
            return "\n".join(texts)

        return str(content)

    def _export_message(self, session_id: str) -> None:
        """Export or append message to markdown.

        Args:
            session_id: The session ID.
        """
        if not self.enable_export:
            return

        messages = self.storage.get_session_messages(session_id)
        if not messages:
            return

        # Check if file exists
        filepath = self.exporter.get_session_path(session_id)

        if filepath:
            # Append latest message
            self.exporter.append_message(session_id, messages[-1])
        else:
            # Create new file with full session
            self.exporter.export_session(session_id, messages)

    def get_context_for_prompt(
        self,
        session_id: str,
        user_message: str,
        n_recent: int = 4,
    ) -> str:
        """Get memory context for injection into prompt.

        Args:
            session_id: The session ID.
            user_message: Current user message.
            n_recent: Number of recent messages to include.

        Returns:
            Formatted context string.
        """
        return self.retriever.build_prompt_with_context(
            session_id=session_id,
            user_message=user_message,
            use_search_context=False,
            n_recent=n_recent,
        )

    def generate_session_summary(self, session_id: str) -> str | None:
        """Generate and store summary for a session.

        Args:
            session_id: The session ID.

        Returns:
            The summary text or None.
        """
        messages = self.storage.get_session_messages(session_id)
        if not messages:
            logger.warning(f"No messages found for session {session_id}")
            return None

        if self._summary_callback:
            try:
                summary = self._summary_callback(session_id, messages)
            except Exception as e:
                logger.error(f"Summary callback failed: {e}")
                summary = self._auto_summary(messages)
        else:
            summary = self._auto_summary(messages)

        # Store summary
        self.storage.store_summary(session_id, summary)

        # Update markdown
        if self.enable_export:
            self.exporter.update_summary(session_id, summary)

        logger.info(f"Generated summary for session {session_id[:8]}")
        return summary

    def _auto_summary(self, messages: list[dict[str, Any]]) -> str:
        """Generate automatic summary from messages.

        Args:
            messages: List of messages.

        Returns:
            Summary string.
        """
        topics = []
        user_count = sum(1 for m in messages if m.get("role") == "user")
        assistant_count = sum(1 for m in messages if m.get("role") == "assistant")

        # Extract key topics from first user message
        if messages:
            first_user = next(
                (m for m in messages if m.get("role") == "user"), None
            )
            if first_user:
                content = first_user.get("content", "")[:100]
                topics.append(f"Started with: {content}...")

        # Extract any tool mentions
        tool_mentions = []
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, str):
                if "tool" in content.lower():
                    tool_mentions.append("tool usage")
                    break

        summary_parts = [
            f"Session with {user_count} user messages and {assistant_count} assistant responses.",
        ]

        if topics:
            summary_parts.append(topics[0])

        if tool_mentions:
            summary_parts.append(f"Includes: {', '.join(tool_mentions)}")

        return " ".join(summary_parts)

    def end_session(self, session_id: str) -> str | None:
        """End a session and generate summary.

        Args:
            session_id: The session ID.

        Returns:
            Summary text or None.
        """
        return self.generate_session_summary(session_id)


# =============================================================================
# Integration helper for the proxy
# =============================================================================

class MemoryMiddleware:
    """Middleware to integrate memory with the proxy service."""

    def __init__(self, memory_manager: MemoryManager = None):
        """Initialize middleware.

        Args:
            memory_manager: MemoryManager instance.
        """
        self.memory = memory_manager or MemoryManager()

    def inject_context(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
        n_recent: int = 4,
    ) -> list[dict[str, Any]]:
        """Inject memory context into message list.

        Args:
            session_id: The session ID.
            messages: Current messages list.
            n_recent: Number of recent messages to include from memory.

        Returns:
            Modified messages list with context.
        """
        # Get existing messages for context building
        memory_messages = self.memory.storage.get_session_messages(session_id)
        if not memory_messages or len(memory_messages) <= 0:
            return messages

        # Build context
        context = self.memory.get_context_for_prompt(
            session_id, "", n_recent=n_recent
        )

        if not context:
            return messages

        # Inject as system message at start
        context_msg = {
            "role": "system",
            "content": f"Previous conversation context:\n{context}",
        }

        # Find existing system message or insert new one
        result = messages.copy()
        system_found = False

        for msg in result:
            if msg.get("role") == "system":
                msg["content"] = msg.get("content", "") + "\n\n" + context
                system_found = True
                break

        if not system_found:
            result.insert(0, context_msg)

        return result

    def extract_session_id(self, request_data: Any) -> str | None:
        """Extract or generate session ID from request.

        Args:
            request_data: Request data object.

        Returns:
            Session ID or None.
        """
        # Check metadata in request
        if hasattr(request_data, "metadata") and request_data.metadata:
            meta = request_data.metadata
            if isinstance(meta, dict):
                session_id = meta.get("session_id") or meta.get("conversation_id")
                if session_id:
                    return session_id

        # Generate deterministic from message content hash
        if hasattr(request_data, "messages") and request_data.messages:
            msgs = request_data.messages
            if msgs:
                # Use content of first user message for hash
                first_content = ""
                for m in msgs:
                    if hasattr(m, "role") and m.role == "user":
                        first_content = str(getattr(m, "content", ""))
                        break
                    elif isinstance(m, dict) and m.get("role") == "user":
                        first_content = str(m.get("content", ""))
                        break

                if first_content:
                    import hashlib
                    short_hash = hashlib.sha256(first_content.encode()).hexdigest()[:16]
                    return f"conv_{short_hash}"

        return None

    def store_exchange(
        self,
        session_id: str,
        request_data: Any,
        response_data: Any,
        model: str | None = None,
        provider: str | None = None,
    ) -> tuple[int, int]:
        """Store a request/response exchange.

        Args:
            session_id: The session ID.
            request_data: Request data.
            response_data: Response data.
            model: Model used.
            provider: Provider used.

        Returns:
            Tuple of message IDs.
        """
        # Extract user message from last message in request
        user_content = ""
        if hasattr(request_data, "messages") and request_data.messages:
            msgs = request_data.messages
            if msgs:
                last = msgs[-1]
                if hasattr(last, "content"):
                    user_content = str(last.content)
                elif isinstance(last, dict):
                    user_content = str(last.get("content", ""))

        # Extract assistant response
        assistant_text = ""
        if response_data:
            assistant_text = self.memory._extract_text(response_data)

        return self.memory.store_interaction(
            session_id=session_id,
            user_message=user_content,
            assistant_response=assistant_text,
            model=model,
            provider=provider,
        )
