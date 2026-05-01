"""SSE stream capture utilities for Persistent Memory Core V2."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class StreamCaptureResult:
    text: str = ""
    model: str | None = None
    stop_reason: str | None = None
    errors: list[str] = field(default_factory=list)


class SSEStreamCapture:
    """Collect assistant text from Anthropic-compatible SSE chunks."""

    def __init__(self) -> None:
        self.result = StreamCaptureResult()

    def feed_line(self, line: str | bytes) -> None:
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")

        line = line.strip()

        if not line.startswith("data:"):
            return

        raw = line.removeprefix("data:").strip()

        if not raw or raw == "[DONE]":
            return

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            self.result.errors.append(f"json_decode_error:{exc}")
            return

        event_type = payload.get("type")

        if event_type == "message_start":
            message = payload.get("message") or {}
            if isinstance(message, dict):
                self.result.model = message.get("model") or self.result.model

        if event_type == "content_block_delta":
            delta = payload.get("delta") or {}
            if isinstance(delta, dict) and delta.get("type") == "text_delta":
                self.result.text += delta.get("text") or ""

        if event_type == "message_delta":
            delta = payload.get("delta") or {}
            if isinstance(delta, dict):
                self.result.stop_reason = delta.get("stop_reason") or self.result.stop_reason

        if event_type == "error":
            self.result.errors.append(str(payload.get("error") or payload))

    def feed_lines(self, lines: Iterable[str | bytes]) -> StreamCaptureResult:
        for line in lines:
            self.feed_line(line)
        return self.result
