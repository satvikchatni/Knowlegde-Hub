import pytest


async def upload_file(upload_client, filename, content, workspace_id, headers):
    files = {"file": (filename, content, "text/plain")}
    result = await upload_client.post(
        f"/workspaces/{workspace_id}/documents", files=files, headers=headers
    )
    return result


async def test_txt_file_upload(upload_client, make_user, make_workspace, tmp_path):
    owner = await make_user("owner@example.com")
    workspace = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = workspace["id"]
    response = await upload_file(
        upload_client,
        filename="test.txt",
        content=b"content",
        workspace_id=workspace_id,
        headers=owner["headers"],
    )
    assert response.status_code == 202
    assert response.json()["status"] == "uploaded"
    assert "storage_path" not in response.json()
    path = (
        tmp_path / response.json()["workspace_id"] / f"{response.json()['id']}.txt"
    )  # json doesn't have standard uuid type,id and workspace_id when returned as json are strings, can chain temp_path to other strings or path objects
    assert path.exists() == True
    assert path.read_bytes() == b"content"


async def test_pdf_file_upload(upload_client, make_user, make_workspace, tmp_path):
    owner = await make_user("owner@example.com")
    workspace = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = workspace["id"]
    files = {"file": ("test.pdf", b"%PDF- valid pdf header", "application/pdf")}
    response = await upload_client.post(
        f"/workspaces/{workspace_id}/documents", headers=owner["headers"], files=files
    )
    assert response.status_code == 202
    assert response.json()["status"] == "uploaded"
    path = tmp_path / response.json()["workspace_id"] / f"{response.json()['id']}.pdf"
    assert path.exists() is True
    assert path.read_bytes() == b"%PDF- valid pdf header"
    assert path.read_bytes() != b"not valid pdf header"


async def test_file_upload_with_text_in_pdf(upload_client, make_user, make_workspace):
    owner = await make_user("owner@example.com")
    workspace = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = workspace["id"]
    files = {"file": ("test.pdf", b"not a valid pdf header", "application/pdf")}
    response = await upload_client.post(
        f"/workspaces/{workspace_id}/documents", headers=owner["headers"], files=files
    )
    assert response.status_code == 415


async def test_file_with_invalid_utf(upload_client, make_user, make_workspace):
    owner = await make_user("owner@example.com")
    workspace = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = workspace["id"]
    files = {
        "file": ("test.txt", b"Hello \xff world", "text/plain")
    }  # maybe a jpeg \xff is a invalid utf character
    response = await upload_client.post(
        f"/workspaces/{workspace_id}/documents", headers=owner["headers"], files=files
    )
    assert response.status_code == 415


async def test_empty_file(upload_client, make_user, make_workspace):
    owner = await make_user("owner@example.com")
    workspace = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = workspace["id"]
    files = {"file": ("test.txt", b"", "text/plain")}
    response = await upload_client.post(
        f"/workspaces/{workspace_id}/documents", headers=owner["headers"], files=files
    )
    assert response.status_code == 422


async def test_no_file(upload_client, make_user, make_workspace):
    owner = await make_user("owner@example.com")
    workspace = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = workspace["id"]
    response = await upload_client.post(
        f"/workspaces/{workspace_id}/documents", headers=owner["headers"]
    )
    assert response.status_code == 422


async def test_wrong_extension(upload_client, make_user, make_workspace):
    owner = await make_user("owner@example.com")
    workspace = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = workspace["id"]
    files = {"file": ("test.text", b"content", "text/plain")}
    response = await upload_client.post(
        f"/workspaces/{workspace_id}/documents", headers=owner["headers"], files=files
    )
    assert response.status_code == 415


async def test_big_file(upload_client, make_user, make_workspace):
    owner = await make_user("owner@example.com")
    workspace = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = workspace["id"]
    files = {"file": ("test.txt", b"a" * 2000000, "text/plain")}
    response = await upload_client.post(
        f"/workspaces/{workspace_id}/documents", headers=owner["headers"], files=files
    )
    assert response.status_code == 413


async def test_path_safety(upload_client, make_user, make_workspace):
    owner = await make_user("owner@example.com")
    workspace = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = workspace["id"]
    files = {"file": ("../../test.txt", b"content", "text/plain")}
    response = await upload_client.post(
        f"/workspaces/{workspace_id}/documents", headers=owner["headers"], files=files
    )
    assert response.status_code == 202
    assert response.json()["filename"] == "test.txt"


@pytest.mark.parametrize(
    "role,expected_status_code",
    [("viewer", 403), ("editor", 202), ("owner", 202), ("stranger", 404), ("anonymous", 401)],
)
async def test_matrix_file_upload(
    upload_client, make_user, make_workspace, role, expected_status_code, make_membership
):
    owner = await make_user("owner@example.com")
    workspace = await make_workspace("testws", user_headers=owner["headers"])
    workspace_id = workspace["id"]
    if role == "owner":
        test_headers = owner["headers"]
    elif role == "editor" or role == "viewer":
        member = await make_user("ve@example.com")  # can be either vieweror editor
        membership = await make_membership(
            workspace_id=workspace_id,
            role=role,
            email=member["email"],
            owner_headers=owner["headers"],
        )
        test_headers = member["headers"]
    elif role == "stranger":
        stranger = await make_user("stranger@example.com")
        test_headers = stranger["headers"]
    else:
        # if anonymous, no headers
        test_headers = {}
    files = {"file": ("test.txt", b"content", "text/plain")}
    response = await upload_client.post(
        f"/workspaces/{workspace_id}/documents", headers=test_headers, files=files
    )
    assert response.status_code == expected_status_code


@pytest.mark.parametrize(
    "role,expected_status_code",
    [("viewer", 403), ("editor", 204), ("owner", 204), ("stranger", 404), ("anonymous", 401)],
)
async def test_matrix_file_delete(
    upload_client, make_user, make_workspace, role, expected_status_code, make_membership
):
    owner = await make_user("owner@example.com")
    workspace = await make_workspace("testws", user_headers=owner["headers"])
    workspace_id = workspace["id"]
    files = {"file": ("test.txt", b"content", "text/plain")}
    document = await upload_client.post(
        f"/workspaces/{workspace_id}/documents", headers=owner["headers"], files=files
    )
    if role == "owner":
        test_headers = owner["headers"]
    elif role == "editor" or role == "viewer":
        member = await make_user("ve@example.com")  # can be either vieweror editor
        membership = await make_membership(
            workspace_id=workspace_id,
            role=role,
            email=member["email"],
            owner_headers=owner["headers"],
        )
        test_headers = member["headers"]
    elif role == "stranger":
        stranger = await make_user("stranger@example.com")
        test_headers = stranger["headers"]
    else:
        # if anonymous, no headers
        test_headers = {}
    files = {"file": ("test.txt", b"content", "text/plain")}
    document_id = document.json()["id"]
    response = await upload_client.delete(
        f"/workspaces/{workspace_id}/documents/{document_id}", headers=test_headers
    )
    assert response.status_code == expected_status_code


@pytest.mark.parametrize(
    "role,expected_status_code", [("viewer", 200), ("editor", 200), ("stranger", 404)]
)
async def test_get_one_document(
    upload_client, make_user, make_workspace, make_membership, role, expected_status_code
):
    owner = await make_user("owner@example.com")
    workspace = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = workspace["id"]
    document = await upload_file(
        upload_client,
        filename="test.txt",
        content=b"content",
        workspace_id=workspace_id,
        headers=owner["headers"],
    )
    if role == "editor" or role == "viewer":
        member = await make_user("ve@example.com")  # can be either vieweror editor
        membership = await make_membership(
            workspace_id=workspace_id,
            role=role,
            email=member["email"],
            owner_headers=owner["headers"],
        )
        test_headers = member["headers"]
    elif role == "stranger":
        stranger = await make_user("stranger@example.com")
        test_headers = stranger["headers"]
    document_id = document.json()["id"]
    response = await upload_client.get(
        f"/workspaces/{workspace_id}/documents/{document_id}", headers=test_headers
    )
    assert response.status_code == expected_status_code


async def test_delete_a_document(
    upload_client, make_user, make_workspace, make_membership, tmp_path
):
    owner = await make_user("owner@example.com")
    workspace = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = workspace["id"]
    response = await upload_file(
        upload_client,
        filename="test.txt",
        content=b"content",
        workspace_id=workspace_id,
        headers=owner["headers"],
    )
    assert response.status_code == 202
    path = tmp_path / response.json()["workspace_id"] / f"{response.json()['id']}.txt"
    assert path.read_bytes() == b"content"
    document_id = response.json()["id"]
    deletion1 = await upload_client.delete(
        f"/workspaces/{workspace_id}/documents/{document_id}", headers=owner["headers"]
    )
    assert deletion1.status_code == 204
    assert path.exists() is False
    # check if deleted doc is still there
    res = await upload_client.get(
        f"/workspaces/{workspace_id}/documents/{document_id}", headers=owner["headers"]
    )
    assert res.status_code == 404
    # second delete
    deletion2 = await upload_client.delete(
        f"/workspaces/{workspace_id}/documents/{document_id}", headers=owner["headers"]
    )
    assert deletion2.status_code == 404


async def test_get_list_of_docs(upload_client, make_user, make_workspace, make_membership):
    # first workspace and its documents
    owner1 = await make_user("owner1@example.com")
    workspace1 = await make_workspace(workspace_name="testws", user_headers=owner1["headers"])
    workspace1_id = workspace1["id"]
    w1d1 = await upload_file(
        upload_client,
        filename="test1.txt",
        content=b"content1",
        workspace_id=workspace1_id,
        headers=owner1["headers"],
    )
    w1d2 = await upload_file(
        upload_client,
        filename="test2.txt",
        content=b"content2",
        workspace_id=workspace1_id,
        headers=owner1["headers"],
    )
    # second workspace and its documents
    owner2 = await make_user("owner2@example.com")
    workspace2 = await make_workspace(workspace_name="testws", user_headers=owner2["headers"])
    workspace2_id = workspace2["id"]
    w2d1 = await upload_file(
        upload_client,
        filename="test3.txt",
        content=b"content3",
        workspace_id=workspace2_id,
        headers=owner2["headers"],
    )
    w2d2 = await upload_file(
        upload_client,
        filename="test4.txt",
        content=b"content4",
        workspace_id=workspace2_id,
        headers=owner2["headers"],
    )
    response1 = await upload_client.get(
        f"/workspaces/{workspace1_id}/documents",
        headers=owner1["headers"],
        params={"limit": 25, "offset": 0},
    )
    assert response1.status_code == 200
    assert response1.json()["limit"] == 25
    print(response1.json())
    assert len(response1.json()["items"]) == 2
    items1 = response1.json()["items"]
    assert all(doc["workspace_id"] == workspace1_id for doc in items1)

    assert w2d1.json()["id"] not in [doc["id"] for doc in items1]
    assert w2d2.json()["id"] not in [doc["id"] for doc in items1]

    response2 = await upload_client.get(
        f"/workspaces/{workspace2_id}/documents",
        headers=owner2["headers"],
        params={"limit": 20, "offset": 1},
    )
    assert response2.status_code == 200
    print(response2.json())
    assert len(response2.json()["items"]) == 1
    items2 = response2.json()["items"]
    assert w1d1.json()["id"] not in [doc["id"] for doc in items2]
    assert w1d2.json()["id"] not in [doc["id"] for doc in items2]
    assert response2.json()["offset"] == 1
    assert all(doc["workspace_id"] == workspace2_id for doc in items2)
