from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.models import RefreshToken
from app.security import hash_token


async def test_login_returns_both_tokens(tokens):
    assert tokens["access_token"] and tokens["refresh_token"]
    assert tokens["token_type"] == "bearer"


async def test_database_stores_only_the_hash(db_session, tokens):
    rows = (await db_session.scalars(select(RefreshToken))).all()
    assert len(rows) == 1
    assert rows[0].token_hash == hash_token(tokens["refresh_token"])
    assert rows[0].token_hash != tokens["refresh_token"]


async def test_refresh_rotates_the_token(client, tokens):
    response = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 200
    new = response.json()
    assert new["refresh_token"] != tokens["refresh_token"]
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {new['access_token']}"})
    assert me.status_code == 200


async def test_reusing_an_old_refresh_token_ends_the_whole_session(client, tokens):
    first = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    newest = first.json()["refresh_token"]

    reuse = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reuse.status_code == 401

    # the thief's reuse also killed the newer token from the same login
    after = await client.post("/auth/refresh", json={"refresh_token": newest})
    assert after.status_code == 401


async def test_refresh_with_unknown_token(client):
    response = await client.post("/auth/refresh", json={"refresh_token": "nope"})
    assert response.status_code == 401


async def test_refresh_with_expired_token(client, db_session, tokens):
    await db_session.execute(
        update(RefreshToken).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db_session.commit()
    response = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 401


async def test_logout_revokes_the_session(client, tokens):
    response = await client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 204
    after = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert after.status_code == 401


async def test_logout_with_unknown_token_is_not_an_error(client):
    response = await client.post("/auth/logout", json={"refresh_token": "nope"})
    assert response.status_code == 204
