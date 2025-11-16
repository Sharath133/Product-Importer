import asyncio
import os
import sys
from pathlib import Path
from typing import AsyncGenerator, Tuple

import pytest
import pytest_asyncio
from fakeredis import FakeRedis
from fakeredis.aioredis import FakeRedis as FakeAsyncRedis
from httpx import AsyncClient

TEST_ROOT = Path(__file__).resolve().parents[1]
if str(TEST_ROOT) not in sys.path:
    sys.path.append(str(TEST_ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from backend.app.database import AsyncSessionLocal, Base, engine, get_session  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app import progress_manager  # noqa: E402


@pytest.fixture(scope="session")
def event_loop() -> asyncio.AbstractEventLoop:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def empty_database() -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session(empty_database):
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def api_client(empty_database):
    async def override_get_session():
        async with AsyncSessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def fakeredis_clients(monkeypatch) -> Tuple[FakeRedis, FakeAsyncRedis]:
    sync_client = FakeRedis(decode_responses=True)
    async_client = FakeAsyncRedis(decode_responses=True)

    def _sync_factory() -> FakeRedis:
        return sync_client

    def _async_factory() -> FakeAsyncRedis:
        return async_client

    monkeypatch.setattr(progress_manager, "_sync_client", _sync_factory)
    monkeypatch.setattr(progress_manager, "_async_client", _async_factory)
    return sync_client, async_client

