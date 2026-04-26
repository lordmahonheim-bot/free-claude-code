"""Memory retriever for context injection."""

import sys
from typing import Any

# Handle missing loguru gracefully
try:
    from loguru import logger
except ImportError:
    class _FallbackLogger:
        def debug(self, *args, **kwargs): pass
        def info(self, *args, **kwargs): pass
        def warning(self, *args, **kwargs): pass
        def error(self, *args, **kwargs): pass
    logger = _FallbackLogger()

from .storage_sqlite import SQLiteStorage


class MemoryRetriever:
    """Retrieves relevant context from memory for injection into prompts."""

    def __init__(self, storage: SQLiteStorage = None):
        """Initialize the retriever.

        Args:
            storage: SQLiteStorage instance. Creates default if None.
        """
        self.storage = storage or SQLiteStorage()

    def get_recent_context(
        self,
        session_id: str,
        n_messages: int = 6,
        include_summary: bool = True,
    ) -> str:
        """Get recent conversation context as formatted string.

        Args:
            session_id: The session ID.
            n_messages: Number of recent messages to include.
            include_summary: Whether to include session summary.

        Returns:
            Formatted context string ready for injection.
        """
        messages = self.storage.get_session_messages(session_id)

        if not messages:
            return ""

        # Get last n messages
        recent = messages[-n_messages:] if len(messages) > n_messages else messages

        context_parts = []

        if include_summary:
            # Get session summary from first message's session info
            # For now, include a brief indicator
            context_parts.append(f"[Previous conversation history: {len(messages)} messages total]")

        context_parts.append("[MEMORY CONTEXT]")

        for msg in recent:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            # Truncate very long messages
            if len(content) > 2000:
                content = content[:2000] + "... [truncated]"
            context_parts.append(f"{role.upper()}: {content}")

        context_parts.append("[END MEMORY]")

        return "\n\n".join(context_parts)

    def search_for_context(
        self,
        query: str,
        current_session_id: str | None = None,
        n_results: int = 3,
    ) -> str:
        """Search memory for relevant context.

        Args:
            query: The search query.
            current_session_id: Current session to exclude from results.
            n_results: Number of results to include.

        Returns:
            Formatted context string.
        """
        results = self.storage.search_messages(query, limit=n_results * 2)

        if current_session_id:
            results = [r for r in results if r.get("session_id") != current_session_id]

        if not results:
            return ""

        results = results[:n_results]

        context_parts = ["[RELEVANT CONTEXT FROM PREVIOUS CONVERSATIONS]"]

        for r in results:
            role = r.get("role", "unknown")
            content = r.get("content", "")[:1000]  # Limit length
            context_parts.append(f"{role.upper()}: {content}")

        context_parts.append("[END RELEVANT CONTEXT]")

        return "\n\n".join(context_parts)

    def build_prompt_with_context(
        self,
        session_id: str,
        user_message: str,
        use_search_context: bool = False,
        n_recent: int = 4,
    ) -> str:
        """Build a full prompt with memory context.

        Args:
            session_id: The session ID.
            user_message: The current user message.
            use_search_context: Whether to search for related context.
            n_recent: Number of recent messages to include.

        Returns:
            Full prompt string with context.
        """
        parts = []

        # Add recent context
        recent_context = self.get_recent_context(session_id, n_messages=n_recent)
        if recent_context:
            parts.append(recent_context)
            parts.append("")

        # Add search context if enabled
        if use_search_context:
            search_context = self.search_for_context(user_message, session_id)
            if search_context:
                parts.append(search_context)
                parts.append("")

        parts.append("[CURRENT MESSAGE]")
        parts.append(f"USER: {user_message}")
        parts.append("[END CURRENT MESSAGE]")

        return "\n\n".join(parts)

    def get_context_dict(
        self,
        session_id: str,
        n_recent: int = 6,
    ) -> dict[str, Any]:
        """Get context as a dictionary for programmatic use.

        Args:
            session_id: The session ID.
            n_recent: Number of recent messages.

        Returns:
            Dictionary with context information.
        """
        messages = self.storage.get_session_messages(session_id)
        recent = messages[-n_recent:] if len(messages) > n_recent else messages

        return {
            "session_id": session_id,
            "total_messages": len(messages),
            "recent_messages": recent,
            "has_history": len(messages) > 0,
        }


class MemorySearch:
    """Command-line search functionality for memory."""

    def __init__(self, storage: SQLiteStorage = None):
        """Initialize search.

        Args:
            storage: SQLiteStorage instance.
        """
        self.storage = storage or SQLiteStorage()

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search messages.

        Args:
            query: Search query string.
            limit: Max results to return.

        Returns:
            List of matching messages.
        """
        logger.info(f"Searching memory for: {query}")
        results = self.storage.search_messages(query, limit=limit)
        logger.info(f"Found {len(results)} results")
        return results

    def format_results(self, results: list[dict[str, Any]]) -> str:
        """Format search results for display.

        Args:
            results: List of message dictionaries.

        Returns:
            Formatted string.
        """
        if not results:
            return "No results found."

        lines = [f"Found {len(results)} result(s):\n"]

        for i, r in enumerate(results, 1):
            session_short = r.get("session_id", "unknown")[:8]
            role = r.get("role", "unknown")
            timestamp = r.get("timestamp", "unknown")[:19]
            content = r.get("content", "")
            preview = content[:200] + "..." if len(content) > 200 else content

            lines.extend([
                f"{i}. Session: {session_short} | {timestamp} | {role}",
                f"   {preview}",
                "",
            ])

        return "\n".join(lines)

    def recent_sessions(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent sessions.

        Args:
            limit: Number of sessions.

        Returns:
            List of session dictionaries.
        """
        return self.storage.get_recent_sessions(limit)

    def format_sessions(self, sessions: list[dict[str, Any]]) -> str:
        """Format sessions for display.

        Args:
            sessions: List of session dictionaries.

        Returns:
            Formatted string.
        """
        if not sessions:
            return "No sessions found."

        lines = [f"Recent sessions ({len(sessions)} total):\n"]

        for s in sessions:
            sid = s.get("session_id", "unknown")[:12]
            created = s.get("created_at", "unknown")[:19]
            updated = s.get("updated_at", "unknown")[:19]
            msg_count = s.get("message_count", 0)
            summary = s.get("summary", "")

            lines.extend([
                f"Session: {sid}",
                f"  Created: {created}",
                f"  Updated: {updated}",
                f"  Messages: {msg_count}",
            ])
            if summary:
                lines.append(f"  Summary: {summary[:100]}...")
            lines.append("")

        return "\n".join(lines)
