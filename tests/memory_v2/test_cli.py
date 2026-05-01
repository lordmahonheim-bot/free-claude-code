import json

from memory_v2.cli import main
from memory_v2.store import PersistentMemoryStore


def test_cli_stats_uses_configured_db(tmp_path, monkeypatch, capsys):
    db = tmp_path / "memory_v2.db"
    monkeypatch.setenv("PERSISTENT_MEMORY_DB", str(db))

    store = PersistentMemoryStore(db)
    session_id = store.get_or_create_session(source_session_id="cli-session")
    store.store_turn(
        session_id=session_id,
        user_text="Question CLI",
        assistant_text="Réponse CLI",
        provider="test_provider",
        model="test_model",
    )

    exit_code = main(["stats"])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["sessions"] == 1
    assert payload["turns"] == 1


def test_cli_search_returns_matching_turn(tmp_path, monkeypatch, capsys):
    db = tmp_path / "memory_v2.db"
    monkeypatch.setenv("PERSISTENT_MEMORY_DB", str(db))

    store = PersistentMemoryStore(db)
    session_id = store.get_or_create_session(source_session_id="cli-session")
    store.store_turn(
        session_id=session_id,
        user_text="Recherche mémoire persistante",
        assistant_text="Résultat trouvé",
        provider="test_provider",
        model="test_model",
    )

    exit_code = main(["search", "persistante"])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert len(payload) == 1
    assert payload[0]["user_text"] == "Recherche mémoire persistante"


def test_cli_recent_returns_recent_turns(tmp_path, monkeypatch, capsys):
    db = tmp_path / "memory_v2.db"
    monkeypatch.setenv("PERSISTENT_MEMORY_DB", str(db))

    store = PersistentMemoryStore(db)
    session_id = store.get_or_create_session(source_session_id="cli-session")
    store.store_turn(
        session_id=session_id,
        user_text="Tour récent",
        assistant_text="Réponse récente",
    )

    exit_code = main(["recent", "--limit", "1"])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert len(payload) == 1
    assert payload[0]["user_text"] == "Tour récent"
