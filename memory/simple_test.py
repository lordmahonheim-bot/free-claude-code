#!/usr/bin/env python3
"""Simple test for memory storage without external dependencies."""

import sys
import os
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock loguru if not available
class MockLogger:
    def debug(self, *args, **kwargs): pass
    def info(self, *args, **kwargs): print(f"[INFO] {' '.join(str(a) for a in args)}")
    def warning(self, *args, **kwargs): pass
    def error(self, *args, **kwargs): print(f"[ERROR] {' '.join(str(a) for a in args)}")
    def remove(self, *args, **kwargs): pass

sys.modules['loguru'] = type(sys)('loguru')
sys.modules['loguru'].logger = MockLogger()

from memory.storage_sqlite import SQLiteStorage


def test_storage():
    """Test basic storage functionality."""
    print("=" * 50)
    print("Testing SQLite Storage")
    print("=" * 50)

    # Use temp location
    test_db = Path(__file__).parent / "test_memory.db"
    if test_db.exists():
        test_db.unlink()

    storage = SQLiteStorage(test_db)

    # Create session
    session_id = storage.create_session()
    print(f"Created session: {session_id[:8]}...")

    # Store messages
    user_id = storage.store_message(
        session_id=session_id,
        role="user",
        content="Bonjour, comment ça va?",
        model="claude-sonnet-4",
        provider="anthropic",
    )
    print(f"Stored user message: id={user_id}")

    assistant_id = storage.store_message(
        session_id=session_id,
        role="assistant",
        content="Bonjour! Je vais bien, merci. Comment puis-je vous aider?",
        model="claude-sonnet-4",
        provider="anthropic",
    )
    print(f"Stored assistant message: id={assistant_id}")

    # Retrieve messages
    messages = storage.get_session_messages(session_id)
    print(f"\nRetrieved {len(messages)} messages:")
    for i, msg in enumerate(messages, 1):
        print(f"  {i}. [{msg['role']}] {msg['content'][:50]}...")

    # Search
    results = storage.search_messages("comment", limit=5)
    print(f"\nSearch 'comment': {len(results)} results")

    # Summary
    import json
    storage.store_summary(session_id, "Test conversation about greetings")
    print("\nStored session summary")

    # Stats
    count = storage.get_message_count()
    print(f"\nTotal messages in DB: {count}")

    # Cleanup
    test_db.unlink()
    print("\nTest DB cleaned up")

    print("\n✓ All storage tests passed!")


if __name__ == "__main__":
    test_storage()
