"""Memory context construction and injection helpers."""

from __future__ import annotations

from typing import Any


MEMORY_HEADER = "## C-f-C Persistent Memory Context"


def build_memory_context(
    turns: list[dict[str, Any]],
    max_chars: int = 12000,
) -> str:
    """Build compact memory context from recent turns."""
    if not turns:
        return ""

    chunks: list[str] = [MEMORY_HEADER]

    for turn in reversed(turns):
        user_text = (turn.get("user_text") or "").strip()
        assistant_text = (turn.get("assistant_text") or "").strip()
        provider = turn.get("provider") or "unknown_provider"
        model = turn.get("model") or "unknown_model"
        status = turn.get("status") or "unknown_status"

        block = (
            f"\n- Provider/Model: {provider}/{model}\n"
            f"  Status: {status}\n"
            f"  User: {user_text[:1000]}\n"
            f"  Assistant: {assistant_text[:1200]}"
        )
        chunks.append(block)

    context = "\n".join(chunks).strip()

    if len(context) > max_chars:
        context = context[-max_chars:]
        context = MEMORY_HEADER + "\n" + context

    return context


def inject_system_context(
    request_payload: dict[str, Any],
    context: str,
) -> dict[str, Any]:
    """Return a copy of request_payload with memory context prepended to system."""
    payload = dict(request_payload)

    if not context:
        return payload

    existing = payload.get("system")

    if existing is None:
        payload["system"] = context
        return payload

    if isinstance(existing, str):
        payload["system"] = context + "\n\n" + existing
        return payload

    if isinstance(existing, list):
        payload["system"] = [{"type": "text", "text": context}] + existing
        return payload

    payload["system"] = context + "\n\n" + str(existing)
    return payload
