#!/usr/bin/env python3
"""CLI for memory management."""

import argparse
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from memory.retriever import MemorySearch
from memory.storage_sqlite import SQLiteStorage


class MemoryCLI:
    """Command-line interface for memory."""

    def __init__(self):
        """Initialize CLI."""
        self.storage = SQLiteStorage()
        self.search = MemorySearch(self.storage)

    def cmd_search(self, query: str, limit: int = 20) -> None:
        """Search command.

        Args:
            query: Search query.
            limit: Result limit.
        """
        results = self.search.search(query, limit)
        print(self.search.format_results(results))

    def cmd_sessions(self, limit: int = 10) -> None:
        """List recent sessions.

        Args:
            limit: Number of sessions.
        """
        sessions = self.search.recent_sessions(limit)
        print(self.search.format_sessions(sessions))

    def cmd_stats(self) -> None:
        """Show statistics."""
        total = self.storage.get_message_count()
        recent = self.search.recent_sessions(5)

        print(f"\nStatistiques de la mémoire")
        print(f"==========================")
        print(f"Total des messages : {total}")
        print(f"Sessions récentes : {len(recent)}")
        if recent:
            print(f"\nLatest session: {recent[0].get('session_id', 'N/A')[:8]}")
            print(f"  Created: {recent[0].get('created_at', 'N/A')}")
            print(f"  Messages: {recent[0].get('message_count', 0)}")

    def cmd_export(self, session_id: str = None) -> None:
        """Export session to Markdown.

        Args:
            session_id: Session ID (partial match OK).
        """
        from memory.exporter_md import MarkdownExporter
        from memory.memory_manager import MemoryManager

        exporter = MarkdownExporter()
        storage = SQLiteStorage()

        if session_id:
            # Try to find full session ID
            sessions = storage.get_recent_sessions(100)
            matches = [s for s in sessions if s.get("session_id", "").startswith(session_id)]
            if not matches:
                print(f"No session found matching: {session_id}")
                return
            sid = matches[0]["session_id"]
            messages = storage.get_session_messages(sid)
            path = exporter.export_session(sid, messages)
            print(f"Exported to: {path}")
        else:
            # Export recent sessions
            sessions = storage.get_recent_sessions(5)
            for s in sessions:
                sid = s["session_id"]
                messages = storage.get_session_messages(sid)
                path = exporter.export_session(sid, messages)
                print(f"Session {sid[:8]} exportée vers : {path}")

    def run(self, args: list[str] = None) -> None:
        """Run CLI.

        Args:
            args: Command line arguments.
        """
        parser = argparse.ArgumentParser(
            prog="memory",
            description="CLI de gestion de la mémoire pour free-claude-code",
        )
        subparsers = parser.add_subparsers(dest="command", help="Commandes")

        # Search command
        search_parser = subparsers.add_parser("search", help="Rechercher dans la mémoire")
        search_parser.add_argument("query", help="Terme de recherche")
        search_parser.add_argument(
            "-l", "--limit", type=int, default=20, help="Limite de résultats"
        )

        # Sessions command
        sessions_parser = subparsers.add_parser("sessions", help="Lister les sessions")
        sessions_parser.add_argument(
            "-l", "--limit", type=int, default=10, help="Limite de sessions"
        )

        # Stats command
        subparsers.add_parser("stats", help="Afficher les statistiques")

        # Export command
        export_parser = subparsers.add_parser("export", help="Exporter vers Markdown")
        export_parser.add_argument(
            "session_id", nargs="?", help="ID de session (partiel)"
        )

        parsed = parser.parse_args(args)

        if not parsed.command:
            parser.print_help()
            return

        if parsed.command == "search":
            self.cmd_search(parsed.query, parsed.limit)
        elif parsed.command == "sessions":
            self.cmd_sessions(parsed.limit)
        elif parsed.command == "stats":
            self.cmd_stats()
        elif parsed.command == "export":
            self.cmd_export(parsed.session_id)


def main():
    """Main entry point."""
    logger.remove()
    cli = MemoryCLI()
    cli.run()


if __name__ == "__main__":
    main()
