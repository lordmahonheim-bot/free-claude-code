from memory_v2.config import MemoryV2Config
from memory_v2.middleware import PersistentMemoryMiddleware
from memory_v2.store import PersistentMemoryStore
from memory_v2.stream_capture import StreamCaptureResult


def test_before_request_injects_recent_memory(tmp_path):
    store = PersistentMemoryStore(tmp_path / "memory_v2.db")
    config = MemoryV2Config(
        enabled=True,
        db_path=str(tmp_path / "memory_v2.db"),
        injection_limit=3,
        max_context_chars=12000,
    )
    middleware = PersistentMemoryMiddleware(store=store, config=config)

    old_session = store.get_or_create_session(source_session_id="old")
    store.store_turn(
        session_id=old_session,
        user_text="Décision ancienne",
        assistant_text="Réponse ancienne",
        provider="nvidia_nim",
        model="model-a",
    )

    request = {
        "messages": [{"role": "user", "content": "Nouvelle question"}],
    }

    session_id, injected = middleware.before_request(
        request,
        source_session_id="new-session",
    )

    assert session_id is not None
    assert "system" in injected
    assert "C-f-C Persistent Memory Context" in injected["system"]
    assert "Décision ancienne" in injected["system"]
    assert "system" not in request
    assert store.stats()["sessions"] == 2
    assert store.stats()["events"] == 1


def test_store_completed_turn_persists_user_and_assistant(tmp_path):
    store = PersistentMemoryStore(tmp_path / "memory_v2.db")
    middleware = PersistentMemoryMiddleware(store=store)
    session_id = store.get_or_create_session(source_session_id="session-1")

    request = {
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "Bonjour"}]},
        ]
    }

    turn_id = middleware.store_completed_turn(
        session_id=session_id,
        request_payload=request,
        assistant_text="Réponse persistée",
        provider="test_provider",
        model="test_model",
    )

    rows = store.search("Bonjour")
    assert turn_id.startswith("turn_")
    assert len(rows) == 1
    assert rows[0]["user_text"] == "Bonjour"
    assert rows[0]["assistant_text"] == "Réponse persistée"
    assert rows[0]["provider"] == "test_provider"
    assert rows[0]["model"] == "test_model"


def test_store_stream_result_marks_failed_when_errors_exist(tmp_path):
    store = PersistentMemoryStore(tmp_path / "memory_v2.db")
    middleware = PersistentMemoryMiddleware(store=store)
    session_id = store.get_or_create_session(source_session_id="session-1")

    request = {
        "messages": [{"role": "user", "content": "Question stream"}],
    }
    stream_result = StreamCaptureResult(
        text="Réponse partielle",
        model="stream-model",
        stop_reason=None,
        errors=["provider_error"],
    )

    middleware.store_stream_result(
        session_id=session_id,
        request_payload=request,
        stream_result=stream_result,
        provider="stream_provider",
    )

    rows = store.search("Question stream")
    assert len(rows) == 1
    assert rows[0]["assistant_text"] == "Réponse partielle"
    assert rows[0]["provider"] == "stream_provider"
    assert rows[0]["model"] == "stream-model"
    assert rows[0]["status"] == "failed"


def test_disabled_middleware_does_not_inject(tmp_path):
    store = PersistentMemoryStore(tmp_path / "memory_v2.db")
    config = MemoryV2Config(
        enabled=False,
        db_path=str(tmp_path / "memory_v2.db"),
    )
    middleware = PersistentMemoryMiddleware(store=store, config=config)

    request = {"messages": [{"role": "user", "content": "Bonjour"}]}
    session_id, injected = middleware.before_request(request)

    assert session_id is None
    assert injected == request
    assert injected is not request


def test_store_stream_result_marks_truncated_on_max_tokens(tmp_path):
    store = PersistentMemoryStore(tmp_path / "memory_v2.db")
    middleware = PersistentMemoryMiddleware(store=store)
    session_id = store.get_or_create_session(source_session_id="session-truncated")

    request = {
        "messages": [{"role": "user", "content": "Question tronquée"}],
    }
    stream_result = StreamCaptureResult(
        text=" ",
        model="stream-model",
        stop_reason="max_tokens",
        errors=[],
    )

    middleware.store_stream_result(
        session_id=session_id,
        request_payload=request,
        stream_result=stream_result,
        provider="stream_provider",
    )

    rows = store.search("Question tronquée")
    assert len(rows) == 1
    assert rows[0]["assistant_text"] == " "
    assert rows[0]["status"] == "truncated"


def test_store_stream_result_marks_empty_when_no_text(tmp_path):
    store = PersistentMemoryStore(tmp_path / "memory_v2.db")
    middleware = PersistentMemoryMiddleware(store=store)
    session_id = store.get_or_create_session(source_session_id="session-empty")

    request = {
        "messages": [{"role": "user", "content": "Question vide"}],
    }
    stream_result = StreamCaptureResult(
        text="   ",
        model="stream-model",
        stop_reason="end_turn",
        errors=[],
    )

    middleware.store_stream_result(
        session_id=session_id,
        request_payload=request,
        stream_result=stream_result,
        provider="stream_provider",
    )

    rows = store.search("Question vide")
    assert len(rows) == 1
    assert rows[0]["assistant_text"] == "   "
    assert rows[0]["status"] == "empty"
