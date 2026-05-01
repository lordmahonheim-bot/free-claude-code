"""Configuration for Persistent Memory Core V2."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryV2Config:
    enabled: bool = True
    db_path: str = "memory_store/persistent_memory_v2.db"
    injection_limit: int = 6
    max_context_chars: int = 12000

    @classmethod
    def from_env(cls) -> "MemoryV2Config":
        return cls(
            enabled=os.getenv("ENABLE_PERSISTENT_MEMORY", "true").lower()
            in {"1", "true", "yes", "on"},
            db_path=os.getenv(
                "PERSISTENT_MEMORY_DB",
                "memory_store/persistent_memory_v2.db",
            ),
            injection_limit=int(
                os.getenv("PERSISTENT_MEMORY_INJECTION_LIMIT", "6")
            ),
            max_context_chars=int(
                os.getenv("PERSISTENT_MEMORY_MAX_CONTEXT_CHARS", "12000")
            ),
        )
