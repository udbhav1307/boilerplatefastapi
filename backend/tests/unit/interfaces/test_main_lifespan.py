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
    monkeypatch.setattr(main, "lifespan_factory", lambda settings, **kwargs: fake_default_lifespan)
    monkeypatch.setattr(main, "local_session", fake_session)
    monkeypatch.setattr(main, "ensure_default_roles", ensure)
    monkeypatch.setattr(main.settings, "PRODUCTION_SECURITY_VALIDATION_ENABLED", False)

    async with main.lifespan_with_security(main.app):
        ensure.assert_awaited_once_with(fake_db)


@pytest.mark.parametrize("create_tables", [True, False])
async def test_startup_respects_create_tables_on_startup(monkeypatch: pytest.MonkeyPatch, create_tables: bool):
    """CREATE_TABLES_ON_STARTUP=false must stop startup from creating tables; migrations own the schema."""
    received: dict = {}

    @asynccontextmanager
    async def fake_default_lifespan(app):
        yield

    @asynccontextmanager
    async def fake_session():
        yield object()

    def fake_factory(settings, **kwargs):
        received.update(kwargs)
        return fake_default_lifespan

    monkeypatch.setattr(main, "lifespan_factory", fake_factory)
    monkeypatch.setattr(main, "local_session", fake_session)
    monkeypatch.setattr(main, "ensure_default_roles", AsyncMock())
    monkeypatch.setattr(main.settings, "PRODUCTION_SECURITY_VALIDATION_ENABLED", False)
    monkeypatch.setattr(main.settings, "CREATE_TABLES_ON_STARTUP", create_tables)

    async with main.lifespan_with_security(main.app):
        pass

    assert received.get("create_tables_on_startup") is create_tables
