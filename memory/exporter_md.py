"""Markdown exporter for conversation sessions."""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path
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


class MarkdownExporter:
    """Exports conversation sessions to human-readable Markdown files."""

    def __init__(self, export_dir: Path | str = None):
        """Initialize the exporter.

        Args:
            export_dir: Directory for Markdown files. Defaults to memory_store/sessions.
        """
        if export_dir is None:
            export_dir = Path(__file__).parent.parent / "memory_store" / "sessions"
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_filename(self, session_id: str) -> str:
        """Create safe filename from session ID."""
        # Take first 8 chars of UUID for brevity
        safe_id = re.sub(r"[^a-zA-Z0-9-]", "", session_id)[:12]
        return f"session_{safe_id}.md"

    def _format_timestamp(self, ts: str) -> str:
        """Format ISO timestamp for readability."""
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except (ValueError, TypeError):
            return ts

    def export_session(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
        summary: str | None = None,
        created_at: str | None = None,
    ) -> Path:
        """Export a session to Markdown.

        Args:
            session_id: The session ID.
            messages: List of message dictionaries.
            summary: Optional session summary.
            created_at: Optional creation timestamp.

        Returns:
            Path to the exported file.
        """
        filename = self._sanitize_filename(session_id)
        filepath = self.export_dir / filename

        now = datetime.now(timezone.utc).isoformat()

        lines = [
            f"# Session: {session_id[:8]}\n",
            f"",
            f"**Created:** {self._format_timestamp(created_at or now)}",
            f"**Exported:** {self._format_timestamp(now)}",
            f"**Messages:** {len(messages)}",
            f"",
            "---",
            "",
        ]

        if summary:
            lines.extend([
                "## Summary",
                "",
                summary,
                "",
                "---",
                "",
            ])

        lines.extend([
            "## Conversation",
            "",
        ])

        for msg in messages:
            role = msg.get("role", "unknown").upper()
            timestamp = self._format_timestamp(msg.get("timestamp", ""))
            content = msg.get("content", "")
            model = msg.get("model")
            provider = msg.get("provider")

            # Header for message
            header_info = f" [{timestamp}]"
            if model:
                header_info += f" | Model: {model}"
            if provider:
                header_info += f" | Provider: {provider}"

            lines.extend([
                f"### {role}{header_info}",
                "",
                content,
                "",
                "---",
                "",
            ])

        filepath.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Exported session {session_id[:8]} to {filepath}")
        return filepath

    def append_message(
        self,
        session_id: str,
        message: dict[str, Any],
    ) -> Path | None:
        """Append a single message to existing session file.

        Args:
            session_id: The session ID.
            message: The message dictionary.

        Returns:
            Path to the file or None if file doesn't exist.
        """
        filename = self._sanitize_filename(session_id)
        filepath = self.export_dir / filename

        if not filepath.exists():
            return None

        content = filepath.read_text(encoding="utf-8")
        lines = content.splitlines()

        # Remove trailing separator if present
        while lines and lines[-1].strip() == "---":
            lines.pop()
        while lines and not lines[-1].strip():
            lines.pop()

        role = message.get("role", "unknown").upper()
        timestamp = self._format_timestamp(message.get("timestamp", ""))
        msg_content = message.get("content", "")
        model = message.get("model")
        provider = message.get("provider")

        header_info = f" [{timestamp}]"
        if model:
            header_info += f" | Model: {model}"
        if provider:
            header_info += f" | Provider: {provider}"

        new_lines = [
            "",
            f"### {role}{header_info}",
            "",
            msg_content,
            "",
            "---",
            "",
        ]

        lines.extend(new_lines)
        filepath.write_text("\n".join(lines), encoding="utf-8")
        logger.debug(f"Appended message to {filepath}")
        return filepath

    def update_summary(self, session_id: str, summary: str) -> bool:
        """Update the summary in an existing session file.

        Args:
            session_id: The session ID.
            summary: The new summary.

        Returns:
            True if successful, False if file doesn't exist.
        """
        filename = self._sanitize_filename(session_id)
        filepath = self.export_dir / filename

        if not filepath.exists():
            return False

        content = filepath.read_text(encoding="utf-8")

        # Simple replacement: add or update summary section
        summary_header = "## Summary"

        if summary_header in content:
            # Replace existing summary
            pattern = r"## Summary\n*\n.*?\n*(?=## Conversation)"
            import re
            new_section = f"## Summary\n\n{summary}\n\n"
            content = re.sub(pattern, new_section, content, flags=re.DOTALL)
        else:
            # Insert summary before Conversation section
            insert_marker = "## Conversation"
            summary_section = f"## Summary\n\n{summary}\n\n---\n\n"
            content = content.replace(insert_marker, summary_section + insert_marker)

        filepath.write_text(content, encoding="utf-8")
        logger.debug(f"Updated summary in {filepath}")
        return True

    def list_session_files(self) -> list[Path]:
        """List all session Markdown files.

        Returns:
            List of file paths.
        """
        if not self.export_dir.exists():
            return []
        return sorted(self.export_dir.glob("session_*.md"))

    def get_session_path(self, session_id: str) -> Path | None:
        """Get path to session file if it exists.

        Args:
            session_id: The session ID.

        Returns:
            Path or None if not found.
        """
        filename = self._sanitize_filename(session_id)
        filepath = self.export_dir / filename
        return filepath if filepath.exists() else None
