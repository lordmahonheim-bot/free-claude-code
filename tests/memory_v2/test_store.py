from memory_v2.store import PersistentMemoryStore


def test_store_persists_turns(tmp_path):
    db = tmp_path / "memory_v2.db"
    store = PersistentMemoryStore(db)

    session_id = store.get_or_create_session(
        source_session_id="claude-session-1",
        title="Test session",
    )
    same_session_id = store.get_or_create_session(
        source_session_id="claude-session-1",
    )

    turn_id = store.store_turn(
        session_id=session_id,
        user_text="Bonjour",
        assistant_text="Synthèse mémoire persistante",
        provider="test_provider",
        model="test_model",
        metadata={"purpose": "unit-test"},
    )

    store.add_event("test_event", {"turn_id": turn_id})

    assert session_id == same_session_id
    assert session_id.startswith("sess_")
    assert turn_id.startswith("turn_")

    stats = store.stats()
    assert stats["sessions"] == 1
    assert stats["turns"] == 1
    assert stats["events"] == 1

    results = store.search("Bonjour")
    assert len(results) == 1
    assert results[0]["assistant_text"] == "Synthèse mémoire persistante"
    assert results[0]["provider"] == "test_provider"
    assert results[0]["model"] == "test_model"
