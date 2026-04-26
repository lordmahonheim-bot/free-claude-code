#!/usr/bin/env python3
"""Test script for memory system."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.memory_manager import MemoryManager
from memory.retriever import MemorySearch


def test_basic_storage():
    """Test basic storage and retrieval."""
    print("=" * 50)
    print("Test 1: Basic Storage")
    print("=" * 50)

    memory = MemoryManager()

    session_id = memory.get_or_create_session()
    print(f"Created session: {session_id[:8]}...")

    # Store some interactions
    memory.store_interaction(
        session_id=session_id,
        user_message="Quelle est la capitale de la France?",
        assistant_response="La capitale de la France est Paris.",
        model="claude-sonnet-4",
        provider="anthropic",
    )

    memory.store_interaction(
        session_id=session_id,
        user_message="Et celle de l'Allemagne?",
        assistant_response="La capitale de l'Allemagne est Berlin.",
        model="claude-sonnet-4",
        provider="anthropic",
    )

    memory.store_interaction(
        session_id=session_id,
        user_message="Merci pour ces informations.",
        assistant_response="Je vous en prie! N'hésitez pas si vous avez d'autres questions.",
        model="claude-sonnet-4",
        provider="anthropic",
    )

    print(f"✓ Stored 3 interactions in session {session_id[:8]}")

    # Retrieve messages
    messages = memory.storage.get_session_messages(session_id)
    print(f"✓ Retrieved {len(messages)} messages from database")

    for i, msg in enumerate(messages, 1):
        content_preview = msg['content'][:50] + "..." if len(msg['content']) > 50 else msg['content']
        print(f"  {i}. [{msg['role']}] {content_preview}")

    # Generate summary
    summary = memory.generate_session_summary(session_id)
    print(f"\n✓ Generated summary: {summary[:100]}...")

    return session_id


def test_search(session_id: str):
    """Test search functionality."""
    print("\n" + "=" * 50)
    print("Test 2: Search")
    print("=" * 50)

    search = MemorySearch()

    # Search for content
    queries = ["capitale", "France", "Allemagne", "Berlin"]

    for query in queries:
        results = search.search(query, limit=5)
        print(f"✓ Search '{query}': {len(results)} result(s)")

    print("\nDetailed search for 'capitale':")
    results = search.search("capitale", limit=5)
    print(search.format_results(results))


def test_context_injection(session_id: str):
    """Test context injection."""
    print("\n" + "=" * 50)
    print("Test 3: Context Injection")
    print("=" * 50)

    memory = MemoryManager()

    context = memory.get_context_for_prompt(
        session_id=session_id,
        user_message="Donne-moi un autre exemple de capitale européenne.",
        n_recent=4,
    )

    print("Generated context prompt:")
    print("-" * 50)
    print(context)
    print("-" * 50)


def test_sessions_list():
    """Test listing sessions."""
    print("\n" + "=" * 50)
    print("Test 4: Sessions List")
    print("=" * 50)

    search = MemorySearch()
    sessions = search.recent_sessions(limit=5)

    print("Recent sessions:")
    print(search.format_sessions(sessions))


def test_md_export(session_id: str):
    """Test Markdown export."""
    print("\n" + "=" * 50)
    print("Test 5: Markdown Export")
    print("=" * 50)

    from memory.exporter_md import MarkdownExporter

    exporter = MarkdownExporter()
    messages = MemoryManager().storage.get_session_messages(session_id)

    path = exporter.export_session(session_id, messages)
    print(f"✓ Exported to: {path}")

    # Read and display file
    content = path.read_text()
    print("\nFile content (first 500 chars):")
    print(content[:500])


def test_cli():
    """Test CLI functionality."""
    print("\n" + "=" * 50)
    print("Test 6: CLI Commands")
    print("=" * 50)

    from memory.cli import MemoryCLI

    cli = MemoryCLI()

    print("Running 'stats' command:")
    cli.cmd_stats()

    print("\nRunning 'search' command:")
    results = cli.search.search("France")
    print(cli.search.format_results(results))


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("Memory System Test Suite")
    print("=" * 60)

    # Run tests
    session_id = test_basic_storage()
    test_search(session_id)
    test_context_injection(session_id)
    test_sessions_list()
    test_md_export(session_id)
    test_cli()

    print("\n" + "=" * 60)
    print("All tests completed successfully!")
    print("=" * 60)
    print(f"\nSession ID: {session_id}")
    print("Check memory_store/ for generated files.")


if __name__ == "__main__":
    main()
