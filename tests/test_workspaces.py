import pytest

from app.models import ranking


async def test_create_workspace(client, make_user):
    user = await make_user("satvikchatni@example.com")
    response = await client.post(
        "/workspaces", json={"name": "myworkspace"}, headers=user["headers"]
    )  # headers are required for authorization purposes.
    assert response.status_code == 201
    assert response.json()["role"] == "owner"


async def test_create_workspace_with_empty_name(client, make_user):
    user = await make_user("satvik@example.com")
    response = await client.post("/workspaces", json={"name": "     "}, headers=user["headers"])
    assert response.status_code == 422


async def test_create_workspace_with_long_name(client, make_user):
    user = await make_user("satvik@example.com")
    response = await client.post("/workspaces", json={"name": 101 * "a"}, headers=user["headers"])
    assert response.status_code == 422


async def test_create_workspace_with_no_token(client, make_user):
    user = await make_user("satvik@example.com")

    response = await client.post("/workspaces", json={"name": "no-token-unauthorized-user"})
    assert response.status_code == 401


async def test_new_workspace_in_creators_list(client, make_user):
    user = await make_user("satvik@example.com")
    response1 = await client.post(
        "/workspaces", json={"name": "newworkspace"}, headers=user["headers"]
    )
    assert response1.status_code == 201
    response2 = await client.get("/workspaces", headers=user["headers"])
    assert response2.status_code == 200
    workspace_names = [ws["name"] for ws in response2.json()]
    assert response1.json()["name"] in workspace_names


async def test_new_user_gets_empty_list(client, make_user):
    user = await make_user("maria@example.com")
    response = await client.get("/workspaces", headers=user["headers"])
    assert response.status_code == 200
    assert response.json() == []


async def test_two_users_create_workspaces(client, make_user):
    user1 = await make_user("maria@example.com")
    user2 = await make_user("satvik@example.com")
    response1 = await client.post(
        "/workspaces", json={"name": "mariasws"}, headers=user1["headers"]
    )
    response2 = await client.post(
        "/workspaces", json={"name": "satviksws"}, headers=user2["headers"]
    )
    assert response1.status_code == 201
    assert response2.status_code == 201
    response3 = await client.get("/workspaces", headers=user1["headers"])
    response4 = await client.get("/workspaces", headers=user2["headers"])
    assert response3.status_code == 200
    assert response4.status_code == 200
    assert response3.json() != response4.json()
    marias_workspace_names = [ws["name"] for ws in response3.json()]
    assert "satviksws" not in marias_workspace_names


async def test_get_one_workspace(client, make_user):
    user = await make_user("satvik@example.com")
    response1 = await client.post("/workspaces", json={"name": "hehe"}, headers=user["headers"])
    assert response1.status_code == 201
    workspace_id = response1.json()["id"]
    response2 = await client.get(f"/workspaces/{workspace_id}", headers=user["headers"])
    assert response2.status_code == 200
    assert response2.json()["name"] == response1.json()["name"]
    assert response2.json()["name"] == "hehe"
    assert response2.json()["id"] == workspace_id


async def test_get_one_workspace_no_token(client, make_user):
    user = await make_user("satvik@example.com")
    response1 = await client.post("/workspaces", json={"name": "hehe"}, headers=user["headers"])
    assert response1.status_code == 201
    workspace_id = response1.json()["id"]
    response2 = await client.get(f"/workspaces/{workspace_id}")
    assert response2.status_code == 401


async def test_get_one_workspace_non_uuid(client, make_user):
    user = await make_user("satvik@example.com")
    response1 = await client.post("/workspaces", json={"name": "hehe"}, headers=user["headers"])
    assert response1.status_code == 201
    response2 = await client.get("/workspaces/1", headers=user["headers"])
    assert response2.status_code == 422


async def test_get_one_workspace_non_member(client, make_user):
    user = await make_user("satvik@example.com")
    owner = await make_user("maria@example.com")
    res = await client.post("/workspaces", headers=owner["headers"], json={"name": "hehehe"})
    assert res.status_code == 201
    workspace_id = res.json()["id"]
    response = await client.get(f"/workspaces/{workspace_id}", headers=user["headers"])
    assert response.status_code == 404


async def test_owner_add_viewer(client, make_user):
    owner = await make_user("satvik@example.com")
    res1 = await client.post("/workspaces", headers=owner["headers"], json={"name": "hahaha"})
    wsid = res1.json()["id"]
    viewer = await make_user("maria@example.com")
    res2 = await client.post(
        f"/workspaces/{wsid}/members",
        json={"email": viewer["email"], "role": "viewer"},
        headers=owner["headers"],
    )
    assert res2.status_code == 201

    # adding same user again
    res3 = await client.post(
        f"/workspaces/{wsid}/members",
        json={"email": viewer["email"], "role": "viewer"},
        headers=owner["headers"],
    )
    assert res3.status_code == 409
    # unknown email
    res4 = await client.post(
        f"/workspaces/{wsid}/members",
        json={"email": "sc@example.com", "role": "viewer"},
        headers=owner["headers"],
    )
    assert res4.status_code == 404
    # admin role:doesn't exist
    admin = await make_user("gavin@example.com")
    res5 = await client.post(
        f"/workspaces/{wsid}/members",
        json={"email": admin["email"], "role": "admin"},
        headers=owner["headers"],
    )
    assert res5.status_code == 422


def test_ranking():
    assert ranking["owner"] > ranking["viewer"]
    assert ranking["owner"] > ranking["editor"]
    assert ranking["editor"] > ranking["viewer"]


@pytest.mark.parametrize(
    "role,expected_status_code",
    [("viewer", 403), ("owner", 201), ("editor", 403), ("stranger", 404), ("anonymous", 401)],
)
async def test_matrix(client, make_user, role, expected_status_code):
    owner = await make_user("satvik@example.com")
    response1 = await client.post(
        "/workspaces", headers=owner["headers"], json={"name": "matrix test"}
    )
    assert response1.status_code == 201

    wsid = response1.json()["id"]
    if role == "owner":
        test_headers = owner["headers"]
    elif role == "anonymous":
        test_headers = {}
    elif role == "viewer" or role == "editor":
        member = await make_user("maria@example.com")
        response2 = await client.post(
            f"/workspaces/{wsid}/members",
            headers=owner["headers"],
            json={"email": member["email"], "role": role},
        )
        assert response2.status_code == 201
        test_headers = member["headers"]
    else:
        stranger = await make_user("stranger@example.com")
        test_headers = stranger["headers"]
    target_user = await make_user("invitee@example.com")
    response3 = await client.post(
        f"/workspaces/{wsid}/members",
        headers=test_headers,
        json={"email": target_user["email"], "role": "viewer"},
    )
    assert response3.status_code == expected_status_code
