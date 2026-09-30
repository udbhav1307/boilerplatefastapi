"""The app's startup seeds the default roles once the database is ready."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from src.interfaces import main

pytestmark = pytest.mark.asyncio


async def test_startup_ensures_default_roles(monkeypatch: pytest.MonkeyPatch):
    fake_db = object()

    @asynccontextmanager
    async def fake_default_lifespan(app):
        yield

    @asynccontextmanager
    async def fake_session():
        yield fake_db

    ensure = AsyncMock()
    monkeypatch.setattr(main, "lifespan_factory", lambda settings: fake_default_lifespan)
    monkeypatch.setattr(main, "local_session", fake_session)
    monkeypatch.setattr(main, "ensure_default_roles", ensure)
    monkeypatch.setattr(main.settings, "PRODUCTION_SECURITY_VALIDATION_ENABLED", False)

    async with main.lifespan_with_security(main.app):
        ensure.assert_awaited_once_with(fake_db)
