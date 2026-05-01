from unittest.mock import Mock, patch

import pytest

from api.routes import create_message
from config.settings import Settings


class DummyRequestData:
    model = "claude-3-opus-20240229"


class DummyService:
    def create_message(self, request_data):
        return {"ok": True}


@pytest.mark.asyncio
async def test_legacy_memory_hooks_are_skipped_when_memory_v2_enabled():
    settings = Settings()
    settings.enable_persistent_memory_v2 = True

    with patch("api.routes.MEMORY_HOOKS_AVAILABLE", True), \
        patch("api.routes.before_request") as before_request, \
        patch("api.routes.after_response") as after_response:
        result = await create_message(
            request_data=DummyRequestData(),
            service=DummyService(),
            settings=settings,
            _auth=None,
        )

    assert result == {"ok": True}
    before_request.assert_not_called()
    after_response.assert_not_called()


@pytest.mark.asyncio
async def test_legacy_memory_hooks_still_run_when_memory_v2_disabled():
    settings = Settings()
    settings.enable_persistent_memory_v2 = False

    after_response_result = {"legacy": True}

    with patch("api.routes.MEMORY_HOOKS_AVAILABLE", True), \
        patch("memory.hooks._create_bonjour_response", return_value=None), \
        patch("api.routes.before_request", return_value="session-1") as before_request, \
        patch("api.routes.after_response", return_value=after_response_result) as after_response:
        result = await create_message(
            request_data=DummyRequestData(),
            service=DummyService(),
            settings=settings,
            _auth=None,
        )

    assert result == after_response_result
    before_request.assert_called_once()
    after_response.assert_called_once()
