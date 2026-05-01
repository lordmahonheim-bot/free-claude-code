from memory_v2.config import MemoryV2Config


def test_memory_v2_config_defaults_disabled(monkeypatch):
    monkeypatch.delenv("ENABLE_PERSISTENT_MEMORY_V2", raising=False)
    monkeypatch.delenv("ENABLE_PERSISTENT_MEMORY", raising=False)
    monkeypatch.delenv("PERSISTENT_MEMORY_V2_DB", raising=False)
    monkeypatch.delenv("PERSISTENT_MEMORY_DB", raising=False)

    config = MemoryV2Config.from_env()

    assert config.enabled is False
    assert config.db_path == "memory_store/persistent_memory_v2.db"
    assert config.injection_limit == 6
    assert config.max_context_chars == 12000


def test_memory_v2_config_env_overrides(monkeypatch):
    monkeypatch.setenv("ENABLE_PERSISTENT_MEMORY_V2", "true")
    monkeypatch.setenv("PERSISTENT_MEMORY_V2_DB", "memory_store/custom_v2.db")
    monkeypatch.setenv("PERSISTENT_MEMORY_V2_INJECTION_LIMIT", "9")
    monkeypatch.setenv("PERSISTENT_MEMORY_V2_MAX_CONTEXT_CHARS", "3456")

    config = MemoryV2Config.from_env()

    assert config.enabled is True
    assert config.db_path == "memory_store/custom_v2.db"
    assert config.injection_limit == 9
    assert config.max_context_chars == 3456


def test_memory_v2_config_legacy_db_env_fallback(monkeypatch):
    monkeypatch.setenv("ENABLE_PERSISTENT_MEMORY", "true")
    monkeypatch.delenv("ENABLE_PERSISTENT_MEMORY_V2", raising=False)
    monkeypatch.setenv("PERSISTENT_MEMORY_DB", "memory_store/legacy_env_name.db")
    monkeypatch.delenv("PERSISTENT_MEMORY_V2_DB", raising=False)

    config = MemoryV2Config.from_env()

    assert config.enabled is True
    assert config.db_path == "memory_store/legacy_env_name.db"
