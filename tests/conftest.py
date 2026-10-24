import pytest
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.db import Base
from app.config import settings
from app.db import get_db
from app.main import app
from pydantic import EmailStr
from app.config import settings
import uuid
from app.models import Role

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
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture
async def db_session(test_engine, client):
    """A session for tests that need to look at, or change, rows directly."""
    async with async_sessionmaker(test_engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture
async def registered_user(client):
    response = await client.post(
        "/auth/register", json={"email": "asha@example.com", "password": "password123"}
    )
    return {**response.json(), "password": "password123"}


@pytest.fixture
async def tokens(client, registered_user):
    response = await client.post(
        "/auth/login",
        data={"username": registered_user["email"], "password": registered_user["password"]},
    )
    return response.json()

@pytest.fixture
def make_user(client):
    async def _make_user(email:EmailStr):
        response1=(await client.post("/auth/register",json={"email":email,"password":"password123"})).json()
        response2=(await client.post("/auth/login",data={"username":response1["email"],"password":"password123"})).json()
        headers={"Authorization": f"Bearer {response2["access_token"]}"}#need headers to be a dictionary not a raw string.
        return {"id":response1["id"],"email":response1["email"],"access_token":response2["access_token"],"refresh_token":response2["refresh_token"],"headers":headers}
    return _make_user

@pytest.fixture
async def upload_client(client,monkeypatch,tmp_path):
    monkeypatch.setattr(settings,"upload_dir",str(tmp_path))
    monkeypatch.setattr(settings,"max_upload_mb",1)
    yield client

#tmp_path is a built-in pytest fixture that provides a temporary directory for the duration of your tests as a pathlib.Path object, deletes this folder automatically later.
#monkeypatch is a built-in pytest fixture that allows you to safely modify environment variables, dictionaries and objects during the runtime of your tests.

@pytest.fixture
def make_workspace(client):
    async def _make_workspace(workspace_name:str,user_headers:dict):
        workspace=await client.post("/workspaces",headers=user_headers,json={'name':workspace_name})
        return workspace.json()
    return _make_workspace

@pytest.fixture#factory fixture like closure but for your tests 
def make_membership(client):
    async def _make_membership(workspace_id:uuid.UUID,role:Role,email:str,owner_headers:dict):
        membership=await client.post(f"/workspaces/{workspace_id}/members",headers=owner_headers,json={"email":email,"role":role})
        return membership.json()
    return _make_membership