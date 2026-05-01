"""Middleware primitives for Persistent Memory Core V2."""

from __future__ import annotations

from typing import Any

from .config import MemoryV2Config
from .extractor import extract_last_user_text
from .injector import build_memory_context, inject_system_context
from .store import PersistentMemoryStore
from .stream_capture import StreamCaptureResult


class PersistentMemoryMiddleware:
    """Provider-neutral memory middleware for C-f-C.

    This class is intentionally independent from FastAPI, providers, and models.
    Proxy integration should call before_request before provider routing and
    store_completed_turn or store_stream_result after response completion.
    """

    def __init__(
        self,
        store: PersistentMemoryStore | None = None,
        config: MemoryV2Config | None = None,
    ) -> None:
        self.config = config or MemoryV2Config.from_env()
        self.store = store or PersistentMemoryStore(self.config.db_path)

    def before_request(
        self,
        request_payload: dict[str, Any],
        source_session_id: str | None = None,
    ) -> tuple[str | None, dict[str, Any]]:
        """Create session and inject recent memory context into request payload."""
        if not self.config.enabled:
            return None, dict(request_payload)

        session_id = self.store.get_or_create_session(
            source_session_id=source_session_id
        )

        recent = self.store.recent_turns(limit=self.config.injection_limit)
        context = build_memory_context(
            recent,
            max_chars=self.config.max_context_chars,
        )
        injected = inject_system_context(request_payload, context)

        self.store.add_event(
            "before_request",
            {
                "session_id": session_id,
                "context_chars": len(context),
                "turns_injected": len(recent),
            },
        )

        return session_id, injected

    def store_completed_turn(
        self,
        session_id: str,
        request_payload: Any,
        assistant_text: str,
        provider: str | None = None,
        model: str | None = None,
        status: str = "completed",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Persist a completed non-stream or already-reconstructed assistant turn."""
        user_text = extract_last_user_text(request_payload)

        turn_id = self.store.store_turn(
            session_id=session_id,
            user_text=user_text,
            assistant_text=assistant_text,
            provider=provider,
            model=model,
            status=status,
            metadata=metadata,
        )

        self.store.add_event(
            "store_completed_turn",
            {
                "session_id": session_id,
                "turn_id": turn_id,
                "status": status,
                "provider": provider,
                "model": model,
            },
        )

        return turn_id

    def store_stream_result(
        self,
        session_id: str,
        request_payload: Any,
        stream_result: StreamCaptureResult,
        provider: str | None = None,
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Persist a turn reconstructed from an SSE stream capture result."""
        if stream_result.errors:
            status = "failed"
        elif stream_result.stop_reason == "max_tokens":
            status = "truncated"
        elif not stream_result.text.strip():
            status = "empty"
        else:
            status = "completed"

        effective_model = model or stream_result.model

        turn_metadata = dict(metadata or {})
        turn_metadata.update(
            {
                "stop_reason": stream_result.stop_reason,
                "stream_errors": stream_result.errors,
            }
        )

        return self.store_completed_turn(
            session_id=session_id,
            request_payload=request_payload,
            assistant_text=stream_result.text,
            provider=provider,
            model=effective_model,
            status=status,
            metadata=turn_metadata,
        )
