import pytest
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db import get_db
from app.main import app

# Tests are run on "<your database>_test", never on your real development database.
TEST_DB_NAME = f"{settings.database_name}_test"
TEST_DB_URL = settings.database_url.set(database=TEST_DB_NAME)


async def _ensure_test_database() -> None:
    """Create the _test database the first time (CREATE DATABASE needs AUTOCOMMIT)."""
    admin_engine = create_async_engine(
        settings.database_url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    async with admin_engine.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DB_NAME}
        )
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    await admin_engine.dispose()


@pytest.fixture(scope="session")
async def test_engine():
    assert TEST_DB_NAME.endswith("_test")  # safety guard for the days we start wiping tables
    await _ensure_test_database()
    engine = create_async_engine(TEST_DB_URL)
    yield engine
    await engine.dispose()


@pytest.fixture
async def client(test_engine):
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()