"""Configuration for Persistent Memory Core V2."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class MemoryV2Config:
    enabled: bool = False
    db_path: str = "memory_store/persistent_memory_v2.db"
    injection_limit: int = 6
    max_context_chars: int = 12000

    @classmethod
    def from_env(cls) -> "MemoryV2Config":
        return cls(
            enabled=_env_bool(
                "ENABLE_PERSISTENT_MEMORY_V2",
                os.getenv("ENABLE_PERSISTENT_MEMORY", "false"),
            ),
            db_path=os.getenv(
                "PERSISTENT_MEMORY_V2_DB",
                os.getenv(
                    "PERSISTENT_MEMORY_DB",
                    "memory_store/persistent_memory_v2.db",
                ),
            ),
            injection_limit=int(
                os.getenv("PERSISTENT_MEMORY_V2_INJECTION_LIMIT", "6")
            ),
            max_context_chars=int(
                os.getenv("PERSISTENT_MEMORY_V2_MAX_CONTEXT_CHARS", "12000")
            ),
        )
