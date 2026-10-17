
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import delete

from app.config import settings
from app.models import User


def make_token(sub, expires_in=timedelta(minutes=15), key=None):
    payload = {"sub": str(sub), "exp": datetime.now(UTC) + expires_in}
    return jwt.encode(payload, key or settings.secret_key, algorithm=settings.algorithm)


async def test_me_with_valid_token(client, registered_user, tokens):
    response = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == registered_user["email"]


async def test_me_without_token(client):
    response = await client.get("/auth/me")
    assert response.status_code == 401


async def test_me_with_garbage_token(client):
    response = await client.get("/auth/me", headers={"Authorization": "Bearer not.a.token"})
    assert response.status_code == 401


async def test_me_with_expired_token(client, registered_user):
    token = make_token(registered_user["id"], expires_in=timedelta(minutes=-1))
    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_me_with_token_signed_by_someone_else(client, registered_user):
    token = make_token(registered_user["id"], key="x" * 50)
    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_me_with_token_for_unknown_user(client):
    response = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {make_token(uuid.uuid4())}"}
    )
    assert response.status_code == 401


async def test_me_after_user_deleted(client, db_session, registered_user, tokens):
    await db_session.execute(delete(User))
    await db_session.commit()
    response = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert response.status_code == 401