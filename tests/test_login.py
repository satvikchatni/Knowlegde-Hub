import jwt

from app.config import settings


async def test_login_success(client):
    reg = await client.post(
        "/auth/register", json={"email": "asha@example.com", "password": "password123"}
    )
    user = reg.json()
    response = await client.post(
        "/auth/login", data={"username": "asha@example.com", "password": "password123"}
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    assert payload["sub"] == user["id"]


async def test_login_wrong_password(client):

    response = await client.post(
        "/auth/login", data={"username": "asha@example.com", "password": "wrongpassword"}
    )
    assert response.status_code == 401


async def test_login_missing_fields(client):

    response = await client.post("/auth/login", data={"username": "asha@example.com"})
    assert response.status_code == 422


async def test_long_wrong_email(client):

    response = await client.post(
        "/auth/login", data={"username": "a" * 100, "password": "password123"}
    )
    assert response.status_code == 401


async def test_login_same_email(client):
    await client.post(
        "/auth/register", json={"email": "asha@example.com", "password": "password123"}
    )
    response = await client.post(
        "/auth/login", data={"username": "ASHA@example.com", "password": "password123"}
    )
    assert response.status_code == 200
