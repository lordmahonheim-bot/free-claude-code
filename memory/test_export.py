#!/usr/bin/env python3
"""Test Markdown export."""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock loguru
class MockLogger:
    def debug(self, *args, **kwargs): pass
    def info(self, *args, **kwargs): print(f"[INFO] {' '.join(str(a) for a in args)}")
    def warning(self, *args, **kwargs): pass
    def error(self, *args, **kwargs): print(f"[ERROR] {' '.join(str(a) for a in args)}")

sys.modules['loguru'] = type(sys)('loguru')
sys.modules['loguru'].logger = MockLogger()

from memory.exporter_md import MarkdownExporter


def test_exporter():
    """Test Markdown export."""
    print("=" * 50)
    print("Testing Markdown Export")
    print("=" * 50)

    export_dir = Path(__file__).parent / "test_sessions"
    export_dir.mkdir(exist_ok=True)

    exporter = MarkdownExporter(export_dir)

    # Create test messages
    session_id = "test-session-12345"
    messages = [
        {
            "role": "user",
            "content": "Quelle est la capitale de la France?",
            "timestamp": "2024-01-15T10:30:00+00:00",
            "model": "claude-sonnet-4",
            "provider": "anthropic",
        },
        {
            "role": "assistant",
            "content": "La capitale de la France est Paris.",
            "timestamp": "2024-01-15T10:30:05+00:00",
            "model": "claude-sonnet-4",
            "provider": "anthropic",
        },
    ]

    # Export session
    path = exporter.export_session(
        session_id=session_id,
        messages=messages,
        summary="Conversation sur les capitales européennes",
        created_at="2024-01-15T10:30:00+00:00",
    )

    print(f"Exported to: {path}")

    # Display content
    content = path.read_text()
    print("\nFile preview:")
    print("-" * 40)
    print(content[:800])
    print("...")

    # Test search
    print("\nSearching for session file:")
    found = exporter.get_session_path(session_id)
    print(f"  Found: {found}")

    # Cleanup
    path.unlink()
    export_dir.rmdir()
    print("\n✓ Export test passed!")


if __name__ == "__main__":
    test_exporter()
