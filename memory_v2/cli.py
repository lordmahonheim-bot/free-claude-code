"""CLI for Persistent Memory Core V2."""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from .config import MemoryV2Config
from .store import PersistentMemoryStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="memory-v2")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("stats", help="Show memory database statistics.")

    search_parser = subparsers.add_parser("search", help="Search memory turns.")
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=int, default=10)

    recent_parser = subparsers.add_parser("recent", help="Show recent memory turns.")
    recent_parser.add_argument("--limit", type=int, default=6)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = MemoryV2Config.from_env()
    store = PersistentMemoryStore(config.db_path)

    if args.command == "stats":
        print(json.dumps(store.stats(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "search":
        rows = store.search(args.query, limit=args.limit)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    if args.command == "recent":
        rows = store.recent_turns(limit=args.limit)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
