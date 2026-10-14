async def test_register_success(client):
    response = await client.post(
        "/auth/register", json={"email": "Asha@Example.com", "password": "password123"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "asha@example.com"   
    assert "password" not in body and "password_hash" not in body


async def test_short_password(client):
    response = await client.post(
        "/auth/register", json={"email": "asha@example.com", "password": "short"}
    )
    assert response.status_code == 422
    
    

async def  test_invalid_email(client):
    response = await client.post(
        "/auth/register", json={"email": "invalid-email", "password": "password123"}
    )
    assert response.status_code == 422
    
    

async def test_duplicate_email(client):
    response1 = await client.post(
        "/auth/register", json={"email": "asha@example.com", "password": "password123"}
    )
    assert response1.status_code == 201

    response2 = await client.post(
        "/auth/register", json={"email": "ASHA@example.com", "password": "password456"}
    )
    assert response2.status_code == 409
    body = response2.json()
    assert "Email already registered" in body["detail"]
