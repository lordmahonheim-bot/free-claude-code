"""Configuration for the memory system."""

import os
import sys
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


class MemoryConfig:
    """Configuration settings for memory system."""

    # Default paths
    DEFAULT_DB_PATH = "memory_store/memory.db"
    DEFAULT_EXPORT_DIR = "memory_store/sessions"

    def __init__(self):
        """Initialize configuration from environment."""
        self.enabled = self._get_bool("MEMORY_ENABLED", True)
        self.db_path = Path(self._get_str("MEMORY_DB_PATH", self.DEFAULT_DB_PATH))
        self.export_dir = Path(self._get_str("MEMORY_EXPORT_DIR", self.DEFAULT_EXPORT_DIR))
        self.enable_markdown = self._get_bool("MEMORY_MARKDOWN", True)
        self.auto_summarize = self._get_bool("MEMORY_AUTO_SUMMARIZE", True)
        self.context_messages = self._get_int("MEMORY_CONTEXT_MESSAGES", 4)
        self.max_search_results = self._get_int("MEMORY_MAX_SEARCH_RESULTS", 5)

        # Resolve paths relative to project root
        if not self.db_path.is_absolute():
            project_root = Path(__file__).parent.parent
            self.db_path = project_root / self.db_path

        if not self.export_dir.is_absolute():
            project_root = Path(__file__).parent.parent
            self.export_dir = project_root / self.export_dir

        logger.debug(f"Memory config: enabled={self.enabled}, db_path={self.db_path}")

    @staticmethod
    def _get_bool(name: str, default: bool) -> bool:
        """Get boolean from environment."""
        value = os.getenv(name, "").lower()
        if value in ("1", "true", "yes", "on"):
            return True
        if value in ("0", "false", "no", "off"):
            return False
        return default

    @staticmethod
    def _get_str(name: str, default: str) -> str:
        """Get string from environment."""
        return os.getenv(name, default)

    @staticmethod
    def _get_int(name: str, default: int) -> int:
        """Get integer from environment."""
        try:
            return int(os.getenv(name, str(default)))
        except ValueError:
            return default

    def to_dict(self) -> dict[str, Any]:
        """Export config as dictionary."""
        return {
            "enabled": self.enabled,
            "db_path": str(self.db_path),
            "export_dir": str(self.export_dir),
            "enable_markdown": self.enable_markdown,
            "auto_summarize": self.auto_summarize,
            "context_messages": self.context_messages,
            "max_search_results": self.max_search_results,
        }
