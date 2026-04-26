"""Integration module for connecting memory to the proxy service."""

import json
from typing import Any

from loguru import logger

from api.services import ClaudeProxyService
from config.settings import Settings
from providers.base import BaseProvider

from .memory_manager import MemoryManager, MemoryMiddleware


class MemoryEnabledProxyService:
    """Wrapper around ClaudeProxyService that adds memory capabilities."""

    def __init__(
        self,
        base_service: ClaudeProxyService,
        settings: Settings,
        memory_manager: MemoryManager = None,
    ):
        """Initialize the memory-enabled wrapper.

        Args:
            base_service: The underlying proxy service.
            settings: Application settings.
            memory_manager: Optional memory manager instance.
        """
        self._base_service = base_service
        self._settings = settings
        self._memory = memory_manager or MemoryManager()
        self._middleware = MemoryMiddleware(self._memory)

        logger.info("Memory-enabled proxy service initialized")

    def create_message(self, request_data: Any) -> Any:
        """Create a message with memory integration.

        Args:
            request_data: MessagesRequest object.

        Returns:
            StreamingResponse or other response object.
        """
        # Extract or create session ID
        session_id = self._middleware.extract_session_id(request_data)
        if not session_id:
            session_id = self._memory.get_or_create_session()
        else:
            session_id = self._memory.get_or_create_session(session_id)

        # Inject memory context into request
        original_messages = getattr(request_data, "messages", [])
        if session_id and len(original_messages) > 0:
            # Build messages dict list for injection
            msg_dicts = []
            for m in original_messages:
                if hasattr(m, "model_dump"):
                    msg_dicts.append(m.model_dump())
                elif hasattr(m, "__dict__"):
                    msg_dicts.append(m.__dict__)
                else:
                    msg_dicts.append(dict(m))

            enhanced_msgs = self._middleware.inject_context(
                session_id, msg_dicts, n_recent=4
            )

            # Update request with enhanced messages
            if enhanced_msgs != msg_dicts:
                # Convert back to Message objects if needed
                from api.models.anthropic import Message

                new_messages = []
                for m in enhanced_msgs:
                    if isinstance(m, dict):
                        new_messages.append(Message(**m))
                    else:
                        new_messages.append(m)
                request_data.messages = new_messages

        # Store user message before sending
        user_content = ""
        if original_messages:
            last_msg = original_messages[-1]
            user_content = self._extract_content(last_msg)

        model = getattr(request_data, "model", None) or self._settings.model
        provider = self._settings.provider_type

        # Create the response
        response = self._base_service.create_message(request_data)

        # Return response with a wrapper to capture the stream
        return self._wrap_response(
            session_id, response, user_content, model, provider
        )

    def _extract_content(self, message: Any) -> str:
        """Extract text content from a message.

        Args:
            message: Message object or dict.

        Returns:
            Text content.
        """
        if hasattr(message, "content"):
            content = message.content
            if isinstance(content, str):
                return content
            elif isinstance(content, list):
                texts = []
                for item in content:
                    if hasattr(item, "text"):
                        texts.append(item.text)
                    elif isinstance(item, dict) and "text" in item:
                        texts.append(item["text"])
                return "\n".join(texts)
        elif isinstance(message, dict):
            content = message.get("content", "")
            if isinstance(content, str):
                return content
            elif isinstance(content, list):
                texts = []
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        texts.append(item["text"])
                return "\n".join(texts)
        return str(message)

    def _wrap_response(
        self,
        session_id: str,
        response: Any,
        user_message: str,
        model: str,
        provider: str,
    ) -> Any:
        """Wrap streaming response to capture content.

        Args:
            session_id: Session ID.
            response: Original response.
            user_message: User message content.
            model: Model used.
            provider: Provider used.

        Returns:
            Wrapped response.
        """
        from starlette.responses import StreamingResponse

        if not isinstance(response, StreamingResponse):
            return response

        # Capture original generator
        original_body = response.body_iterator

        async def capturing_generator():
            """Generator that captures and stores content."""
            full_content = []
            async for chunk in original_body:
                full_content.append(chunk)
                yield chunk

            # After stream completes, store the interaction
            assistant_text = self._extract_from_stream("".join(full_content))
            if assistant_text:
                self._memory.store_interaction(
                    session_id=session_id,
                    user_message=user_message,
                    assistant_response=assistant_text,
                    model=model,
                    provider=provider,
                )

        # Create new streaming response with capturing generator
        return StreamingResponse(
            capturing_generator(),
            media_type=response.media_type,
            headers=dict(response.headers),
        )

    def _extract_from_stream(self, content: str) -> str:
        """Extract assistant content from SSE stream.

        Args:
            content: Raw SSE stream content.

        Returns:
            Extracted text.
        """
        texts = []
        for line in content.split("\n"):
            if line.startswith("data: "):
                data = line[6:]
                if data in ("[DONE]", ""):
                    continue
                try:
                    parsed = json.loads(data)
                    # Handle Anthropic format
                    if isinstance(parsed, dict):
                        delta = parsed.get("delta", {})
                        if isinstance(delta, dict):
                            text = delta.get("text", "")
                            if text:
                                texts.append(text)
                except json.JSONDecodeError:
                    pass
        return "".join(texts)

    def count_tokens(self, request_data: Any) -> Any:
        """Delegate to base service for token counting."""
        return self._base_service.count_tokens(request_data)


def create_memory_enabled_service(
    settings: Settings,
    provider_getter: Any,
    token_counter: Any = None,
) -> MemoryEnabledProxyService:
    """Factory to create a memory-enabled proxy service.

    Args:
        settings: Application settings.
        provider_getter: Function to get provider instance.
        token_counter: Token counter function.

    Returns:
        MemoryEnabledProxyService instance.
    """
    from api.model_router import ModelRouter

    router = ModelRouter(settings)

    base_service = ClaudeProxyService(
        settings=settings,
        provider_getter=provider_getter,
        model_router=router,
        token_counter=token_counter,
    )

    return MemoryEnabledProxyService(
        base_service=base_service,
        settings=settings,
    )
