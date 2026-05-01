from config.settings import Settings


def test_persistent_memory_v2_settings_defaults():
    settings = Settings()

    assert settings.enable_persistent_memory_v2 is False
    assert settings.persistent_memory_v2_db == "memory_store/persistent_memory_v2.db"
    assert settings.persistent_memory_v2_injection_limit == 6
    assert settings.persistent_memory_v2_max_context_chars == 12000


def test_persistent_memory_v2_settings_env_overrides(monkeypatch):
    monkeypatch.setenv("ENABLE_PERSISTENT_MEMORY_V2", "true")
    monkeypatch.setenv("PERSISTENT_MEMORY_V2_DB", "memory_store/custom_v2.db")
    monkeypatch.setenv("PERSISTENT_MEMORY_V2_INJECTION_LIMIT", "8")
    monkeypatch.setenv("PERSISTENT_MEMORY_V2_MAX_CONTEXT_CHARS", "9000")

    settings = Settings()

    assert settings.enable_persistent_memory_v2 is True
    assert settings.persistent_memory_v2_db == "memory_store/custom_v2.db"
    assert settings.persistent_memory_v2_injection_limit == 8
    assert settings.persistent_memory_v2_max_context_chars == 9000
