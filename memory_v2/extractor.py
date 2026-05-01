"""Provider-neutral text extraction helpers for Persistent Memory Core V2."""

from __future__ import annotations

from typing import Any


def extract_text_from_content(content: Any) -> str:
    """Extract text from plain strings, dicts, or Anthropic-style content blocks."""
    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text

        nested = content.get("content")
        if isinstance(nested, str):
            return nested

        return ""

    if isinstance(content, list):
        parts: list[str] = []

        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue

            if isinstance(item, dict):
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])

        return "\n".join(part for part in parts if part)

    return ""


def extract_last_user_text(request_data: Any) -> str:
    """Extract the latest user message from dict or Pydantic-like request objects."""
    messages = getattr(request_data, "messages", None)

    if messages is None and isinstance(request_data, dict):
        messages = request_data.get("messages")

    if not messages:
        return ""

    for message in reversed(messages):
        role = getattr(message, "role", None)
        content = getattr(message, "content", None)

        if isinstance(message, dict):
            role = message.get("role")
            content = message.get("content")

        if role == "user":
            return extract_text_from_content(content).strip()

    return ""
