"""Simple hooks for integrating memory into the proxy."""

import re
import json
import uuid
from datetime import datetime, timezone
from typing import Any
from collections.abc import Iterator

from starlette.responses import StreamingResponse

# Import handles loguru mock internally
from .storage_sqlite import SQLiteStorage
from .config import MemoryConfig

# Import Anthropic SSE builder for Bonjour synthesis
from core.anthropic.sse import SSEBuilder

MEMORY_ENABLED = True

def _debug_memory_log(message: str) -> None:
    """Temporary file logger for memory hook diagnostics."""
    try:
        from datetime import datetime
        from pathlib import Path
        log_path = Path("memory_store/debug_memory.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} | {message}\n")
    except Exception:
        pass

# Global storage instance (lazy init)
_storage_instance = None

def _get_storage():
    """Get or create storage instance."""
    global _storage_instance
    if _storage_instance is None and SQLiteStorage is not None:
        config = MemoryConfig()
        _storage_instance = SQLiteStorage(config.db_path)
    return _storage_instance


def _extract_text_content(message: Any) -> str:
    """Extract text from message content."""
    if hasattr(message, "content"):
        content = message.content
    elif isinstance(message, dict):
        content = message.get("content", "")
    else:
        return str(message)

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    texts.append(block.get("text", ""))
                elif "text" in block:
                    texts.append(block["text"])
            elif hasattr(block, "text"):
                texts.append(block.text)
        return "\n".join(texts)

    return str(content)


def _is_bonjour_start(user_message: str) -> bool:
    """Detect if message starts with 'Bonjour' (case-insensitive, strip whitespace)."""
    if not user_message:
        return False
    user_str = str(user_message).strip()
    pattern = re.compile(r'^bonjour\b', re.IGNORECASE)
    return bool(pattern.match(user_str))



def _get_last_user_message(request_data: Any) -> tuple[str | None, str | None]:
    """Extract session_id and user message from request."""
    messages = getattr(request_data, "messages", None)
    if not messages:
        return None, None

    # Find last user message
    last_user = None
    for msg in reversed(messages):
        if isinstance(msg, dict):
            role = msg.get("role")
        else:
            role = getattr(msg, "role", None)
        if role == "user":
            last_user = msg
            break

    if not last_user:
        return None, None

    content = _extract_text_content(last_user)

    # Try to get session_id from metadata
    session_id = None
    meta = getattr(request_data, "metadata", None)
    if isinstance(meta, dict):
        session_id = meta.get("session_id") or meta.get("conversation_id")

    # Generate from content hash if not found
    if not session_id and content:
        import hashlib
        short_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        session_id = f"conv_{short_hash}"

    return session_id, content


def before_request(request_data: Any, n_context: int = 4) -> str | None:
    """Hook to run before processing a request.

    Injects memory context and returns session_id for later use.

    Args:
        request_data: The MessagesRequest object
        n_context: Number of recent messages to inject as context

    Returns:
        Session ID or None
    """
    _debug_memory_log("before_request called")
    if not MEMORY_ENABLED:
        _debug_memory_log("before_request disabled")
        return None

    session_id, user_message = _get_last_user_message(request_data)
    _debug_memory_log(f"bonjour_debug session_id={session_id} user_message_repr={repr(user_message)[:100]} user_message_type={type(user_message).__name__}")
    if not session_id:
        return None


    storage = _get_storage()
    if storage is None:
        return session_id

    # Ensure session exists
    storage.create_session(session_id)

    # Get previous context
    if n_context > 0:
        prev_messages = storage.get_session_messages(session_id)
        if len(prev_messages) >= 2:  # At least one exchange
            recent = prev_messages[-n_context * 2:]  # Pairs of user/assistant

            # Build context string
            context_parts = ["[MEMORY CONTEXT]"]
            for msg in recent:
                role = msg.get("role", "unknown").upper()
                content = msg.get("content", "")[:500]  # Limit length
                context_parts.append(f"{role}: {content}")
            context_parts.append("[END MEMORY]")

            context_str = "\n\n".join(context_parts)

            # Inject into system message
            system = getattr(request_data, "system", None)
            if system:
                if isinstance(system, str):
                    request_data.system = f"{context_str}\n\n{system}"
                elif isinstance(system, list):
                    from api.models.anthropic import SystemContent
                    system.insert(0, SystemContent(type="text", text=context_str))
            else:
                # Check if messages list has room for system message
                messages = getattr(request_data, "messages", [])
                if messages and hasattr(messages[0], "role"):
                    if messages[0].role == "user":
                        # No system message, inject in first message
                        from api.models.anthropic import ContentBlockText

                        first_content = getattr(messages[0], "content", "")
                        if isinstance(first_content, str):
                            # Wrap in content blocks
                            messages[0].content = [
                                ContentBlockText(type="text", text=context_str),
                                ContentBlockText(type="text", text=first_content),
                            ]

    _debug_memory_log(f"before_request session_id={session_id}")
    return session_id


class ResponseCapture:
    """Captures streaming response for storage."""

    def __init__(self, session_id: str, user_message: str, model: str, provider: str):
        self.session_id = session_id
        self.user_message = user_message
        self.model = model
        self.provider = provider
        self.chunks = []
        self.done = False

    def capture(self, chunk: str) -> str:
        """Capture a chunk and return it unchanged."""
        if not self.done:
            self.chunks.append(chunk)
            if "event: message_stop" in chunk or '[DONE]' in chunk:
                self.finalize()
        return chunk

    def finalize(self) -> None:
        """Store captured chunks once when the stream ends."""
        _debug_memory_log(f"finalize called chunks={len(self.chunks)} done={self.done}")
        if self.done:
            return
        self.done = True
        if self.chunks:
            self._store()

    def _store(self) -> None:
        """Store the captured interaction."""
        _debug_memory_log(f"_store called chunks={len(self.chunks)}")
        if not MEMORY_ENABLED:
            return

        storage = _get_storage()
        if storage is None:
            return

        full_text = "".join(self.chunks)

        # Temporary diagnostic: dump a limited sample of the captured stream.
        try:
            sample_path = __import__("pathlib").Path("memory_store/debug_last_stream.txt")
            sample_path.parent.mkdir(parents=True, exist_ok=True)
            sample_path.write_text(full_text[:12000], encoding="utf-8")
        except Exception:
            pass

        assistant_text = self._extract_sse_text(full_text)
        _debug_memory_log(f"_store assistant_text_len={len(assistant_text)} user_len={len(self.user_message)}")

        # Always store the user message. Even if assistant parsing fails,
        # the session must remain visible and debuggable.
        _debug_memory_log("storing user message")
        storage.store_message(
            session_id=self.session_id,
            role="user",
            content=self.user_message,
            model=self.model,
            provider=self.provider,
        )

        # Store assistant only if we successfully parsed text from the stream.
        if assistant_text:
            _debug_memory_log("storing assistant message")
            storage.store_message(
                session_id=self.session_id,
                role="assistant",
                content=assistant_text,
                model=self.model,
                provider=self.provider,
            )

    def _extract_sse_text(self, content: str) -> str:
        """Extract assistant text from Anthropic-compatible SSE stream."""
        texts = []

        for line in content.splitlines():
            if not line.startswith("data: "):
                continue

            data = line[6:].strip()
            if not data or data == "[DONE]":
                continue

            try:
                parsed = json.loads(data)
            except (json.JSONDecodeError, ValueError):
                continue

            if not isinstance(parsed, dict):
                continue

            event_type = parsed.get("type")

            # Real observed format:
            # {"type":"content_block_delta","delta":{"type":"text_delta","text":"..."}}
            if event_type == "content_block_delta":
                delta = parsed.get("delta", {})
                if isinstance(delta, dict):
                    text = delta.get("text")
                    if isinstance(text, str) and text:
                        texts.append(text)
                continue

            # Initial block may contain text, usually empty.
            if event_type == "content_block_start":
                block = parsed.get("content_block", {})
                if isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str) and text:
                        texts.append(text)
                continue

            # Fallback for other provider shapes.
            delta = parsed.get("delta")
            if isinstance(delta, dict):
                text = delta.get("text")
                if isinstance(text, str) and text:
                    texts.append(text)

            content_block = parsed.get("content_block")
            if isinstance(content_block, dict):
                text = content_block.get("text")
                if isinstance(text, str) and text:
                    texts.append(text)

        return "".join(texts)


def after_response(
    session_id: str | None,
    response: Any,
    request_data: Any,
    model: str | None = None,
    provider: str | None = None,
) -> Any:
    """Hook to run after getting response.

    Wraps the response to capture streaming content.

    Args:
        session_id: From before_request
        response: The response object
        request_data: Original request
        model: Model used
        provider: Provider used

    Returns:
        Wrapped response
    """
    _debug_memory_log(f"after_response called session_id={session_id}")
    if not MEMORY_ENABLED or not session_id:
        _debug_memory_log("after_response skipped disabled_or_no_session")
        return response

    # Get user message
    _, user_message = _get_last_user_message(request_data)
    if not user_message:
        _debug_memory_log("after_response skipped no_user_message")
        return response

    # Only wrap StreamingResponse
    from starlette.responses import StreamingResponse

    if not isinstance(response, StreamingResponse):
        # For non-streaming, store directly
        storage = _get_storage()
        if storage:
            storage.store_message(
                session_id=session_id,
                role="user",
                content=user_message,
                model=model,
                provider=provider,
            )
            # Extract from response body
            assistant_text = str(response.body) if hasattr(response, "body") else ""
            if assistant_text:
                storage.store_message(
                    session_id=session_id,
                    role="assistant",
                    content=assistant_text,
                    model=model,
                    provider=provider,
                )
        return response

    # Wrap for streaming capture
    capture = ResponseCapture(session_id, user_message, model or "unknown", provider or "unknown")
    original_iterator = response.body_iterator

    async def wrapping_iterator():
        try:
            async for chunk in original_iterator:
                if isinstance(chunk, bytes):
                    text = chunk.decode("utf-8", errors="replace")
                else:
                    text = str(chunk)
                # Memory is non-blocking: never interrupt the stream
                try:
                    capture.capture(text)
                except Exception:
                    pass  # Logged in ResponseCapture, stream continues
                yield chunk
        finally:
            try:
                capture.finalize()
            except Exception:
                pass  # Memory must never break streaming

    # Create new response with wrapped iterator
    return StreamingResponse(
        wrapping_iterator(),
        media_type=response.media_type,
        headers=dict(response.headers),
    )


# =============================================================================
# BONJOUR SHORT-CIRCUIT: Local synthesis response
# =============================================================================

def _build_bonjour_synthesis_text(storage) -> str:
    """Build factual synthesis text from real memory data.

    Returns structured markdown synthesis based entirely on SQLite data.
    """
    lines = []
    topics_found: list[str] = []

    # Header
    lines.append("# Synthèse des dernières sessions C-f-C\n")

    # Section 1: Dernières sessions
    lines.append("## 1. Dernières sessions\n")
    recent_sessions = storage.get_recent_sessions(limit=5)
    if not recent_sessions:
        lines.append("Aucune session précédente exploitable trouvée dans la mémoire consultée.\n")
    else:
        lines.append(f"**{len(recent_sessions)} session(s) récente(s) en mémoire**\n\n")
        for i, session in enumerate(recent_sessions, 1):
            sid = session.get("session_id", "unknown")[:8]
            updated = str(session.get("updated_at", "inconnue"))[:19]
            msg_count = session.get("message_count", 0)
            summary = session.get("summary", "")
            summary_preview = f" — {summary[:50]}..." if summary else ""
            lines.append(f"{i}. **Session `{sid}`** — {updated} — {msg_count} message(s){summary_preview}\n")

    # Section 2: Sujets travaillés
    lines.append("\n## 2. Sujets travaillés\n")
    if not recent_sessions:
        lines.append("_Aucune donnée disponible_\n")
    else:
        for session in recent_sessions[:3]:
            messages = storage.get_session_messages(session.get("session_id"), limit=5)
            for msg in messages:
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if content and len(content) > 3:
                        first_line = content.split("\n")[0][:80]
                        if first_line and first_line not in topics_found:
                            topics_found.append(first_line)
                            break
            if len(topics_found) >= 3:
                break
        if topics_found:
            for topic in topics_found:
                lines.append(f"- {topic}\n")
        else:
            lines.append("_Aucun sujet utilisateur identifiable_\n")

    # Section 3: Décisions prises
    lines.append("\n## 3. Décisions prises\n")
    decisions: list[str] = []
    if recent_sessions:
        for session in recent_sessions[:2]:
            messages = storage.get_session_messages(session.get("session_id"), limit=10)
            for msg in messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if isinstance(content, str) and "assistant" in role:
                    lower = content.lower()
                    if any(k in lower for k in ["implémenté", "ajouté", "modifié", "créé", "fixé", "résolu"]):
                        first_sent = content.split(".")[0][:100]
                        if len(first_sent) > 10:
                            decisions.append(first_sent)
                            break

    if decisions:
        for d in decisions[:3]:
            lines.append(f"- {d}\n")
    else:
        if recent_sessions:
            lines.append("_Aucune décision explicite identifiée dans les échanges_\n")
        else:
            lines.append("_Aucune donnée_\n")

    # Section 4: Problèmes ouverts
    lines.append("\n## 4. Problèmes ouverts\n")
    issues: list[str] = []
    if recent_sessions:
        for session in recent_sessions[:2]:
            messages = storage.get_session_messages(session.get("session_id"), limit=10)
            for msg in messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if isinstance(content, str):
                    lower = content.lower()
                    if any(k in lower for k in ["erreur", "bug", "fail", "todo", "fixme", "à faire", "à corriger"]):
                        first_sent = content.split(".")[0][:100]
                        if len(first_sent) > 10:
                            issues.append(first_sent)
                            break

    if issues:
        for issue in issues[:2]:
            lines.append(f"- {issue}\n")
    else:
        lines.append("Aucun problème explicite détecté automatiquement dans les sessions consultées.\n")

    # Section 5: Action recommandée
    lines.append("\n## 5. Prochaine action recommandée\n")
    if recent_sessions:
        last_session = recent_sessions[0]
        last_sid = last_session.get("session_id", "unknown")[:8]
        last_topic = topics_found[0] if topics_found else "dernier sujet"
        lines.append(f"Reprendre la session la plus récente (`{last_sid}`) sur : _{last_topic}_\n")
    else:
        lines.append("Démarrer une session de travail pour construire l'historique C-f-C.\n")

    return "".join(lines)


def _generate_bonjour_sse_stream(synthesis_text: str, model: str) -> Iterator[str]:
    """Generate Anthropic SSE stream using official SSEBuilder.

    Yields SSE event strings ready for StreamingResponse.
    """
    message_id = f"msg_{uuid.uuid4().hex[:24]}"
    builder = SSEBuilder(message_id=message_id, model=model, input_tokens=10)

    # message_start
    yield builder.message_start()

    # content_block_start for text block
    yield builder.start_text_block()

    # Emit text chunks
    chunk_size = 400
    for i in range(0, len(synthesis_text), chunk_size):
        chunk = synthesis_text[i:i+chunk_size]
        yield builder.emit_text_delta(chunk)

    # Stop text block
    yield builder.stop_text_block()

    # message_delta with stop_reason
    output_tokens = len(synthesis_text.split())
    yield builder.message_delta("end_turn", output_tokens)

    # message_stop
    yield builder.message_stop()


def _create_bonjour_response(request_data: Any) -> StreamingResponse | None:
    """Create Bonjour synthesis response if message starts with 'Bonjour'.

    Returns StreamingResponse to short-circuit to local synthesis,
    or None to proceed with normal provider flow.

    Args:
        request_data: The MessagesRequest object

    Returns:
        StreamingResponse for local synthesis, or None for normal flow
    """
    _debug_memory_log("bonjour_shortcircuit_checking")

    if not MEMORY_ENABLED:
        _debug_memory_log("bonjour_shortcircuit_disabled")
        return None

    # Extract last user message
    session_id, user_message = _get_last_user_message(request_data)
    if not user_message:
        _debug_memory_log("bonjour_shortcircuit_no_message")
        return None

    # Check if starts with Bonjour
    is_bonjour = _is_bonjour_start(user_message)
    _debug_memory_log(f"bonjour_check result={is_bonjour}")

    if not is_bonjour:
        return None

    _debug_memory_log("bonjour_detected")

    storage = _get_storage()
    if not storage:
        _debug_memory_log("bonjour_memory_none")
        return None

    try:
        _debug_memory_log("bonjour_memory_loading")
        synthesis_text = _build_bonjour_synthesis_text(storage)
        _debug_memory_log("bonjour_memory_loaded")

        model = getattr(request_data, "model", "claude-opus-4-20250514")

        # Generate SSE stream
        def sse_generator():
            for chunk in _generate_bonjour_sse_stream(synthesis_text, model):
                # Encode for streaming
                if isinstance(chunk, str):
                    yield chunk.encode("utf-8")

        _debug_memory_log("bonjour_response_built")

        response = StreamingResponse(
            sse_generator(),
            media_type="text/event-stream",
            headers={
                "X-Accel-Buffering": "no",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

        _debug_memory_log(f"bonjour_short_circuit_returned session_id={session_id}")
        return response

    except Exception as e:
        _debug_memory_log(f"bonjour_error {e}")
        return None
