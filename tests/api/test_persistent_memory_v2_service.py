import pytest

from api.services import ClaudeProxyService
from config.settings import Settings
from memory_v2.store import PersistentMemoryStore


async def _stream_from(chunks):
    for chunk in chunks:
        yield chunk


def _settings(tmp_path, enabled=True):
    settings = Settings()
    settings.enable_persistent_memory_v2 = enabled
    settings.persistent_memory_v2_db = str(tmp_path / "persistent_memory_v2.db")
    settings.persistent_memory_v2_injection_limit = 4
    settings.persistent_memory_v2_max_context_chars = 12000
    settings.provider_rotation_health_db = str(tmp_path / "provider_health.db")
    return settings


def _service(settings):
    return ClaudeProxyService(
        settings,
        provider_getter=lambda _provider_id: None,
    )


@pytest.mark.asyncio
async def test_memory_v2_capture_stream_persists_completed_turn(tmp_path):
    settings = _settings(tmp_path, enabled=True)
    service = _service(settings)

    request = {
        "messages": [
            {"role": "user", "content": "Bonjour mémoire V2"},
        ],
    }
    session_id, injected_request = service._memory_v2.before_request(request)

    chunks = [
        'data: {"type":"message_start","message":{"model":"actual-model"}}',
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Réponse "}}',
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"persistée"}}',
        'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}',
    ]

    observed = [
        chunk
        async for chunk in service._memory_v2_capture_stream(
            _stream_from(chunks),
            session_id=session_id,
            request_payload=injected_request,
            provider="test_provider",
            model="configured-model",
        )
    ]

    assert observed == chunks

    store = PersistentMemoryStore(settings.persistent_memory_v2_db)
    rows = store.search("Bonjour mémoire V2")
    assert len(rows) == 1
    assert rows[0]["assistant_text"] == "Réponse persistée"
    assert rows[0]["provider"] == "test_provider"
    assert rows[0]["model"] == "configured-model"
    assert rows[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_memory_v2_capture_stream_passthrough_when_disabled(tmp_path):
    settings = _settings(tmp_path, enabled=False)
    service = _service(settings)

    chunks = [
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"OK"}}',
    ]

    observed = [
        chunk
        async for chunk in service._memory_v2_capture_stream(
            _stream_from(chunks),
            session_id=None,
            request_payload={"messages": [{"role": "user", "content": "No store"}]},
            provider="test_provider",
            model="test_model",
        )
    ]

    assert observed == chunks
    assert service._memory_v2 is None
