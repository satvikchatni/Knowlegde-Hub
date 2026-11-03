import pytest
from reportlab.pdfgen import canvas
from sqlalchemy import select

from app.models import Document


def create_file(tmp_path):
    file_path = tmp_path / "test.txt"
    file_path.write_text("Text to process,this is our testing phase", encoding="utf-8")
    return file_path


async def test_retry_endpoint(
    make_user, make_workspace, upload_file, tmp_path, db_session, upload_client
):
    owner = await make_user("owner@example.com")
    workspace = await make_workspace("testws", user_headers=owner["headers"])
    file_path = create_file(tmp_path)
    doc_response = await upload_file(
        filename="test.txt",
        content=file_path.read_bytes(),
        workspace_id=workspace["id"],
        headers=owner["headers"],
    )
    assert doc_response.status_code == 202
    assert doc_response.json()["workspace_id"] == workspace["id"]
    assert (
        doc_response.json()["status"] != "done"
    )  # the result json is created before the bg task runs
    result = await db_session.execute(
        select(Document).where(Document.id == doc_response.json()["id"])
    )
    document = result.scalar_one()
    assert document.status == "done"
    workspace_id = workspace["id"]
    document_id = document.id
    retry = await upload_client.post(
        f"/workspaces/{workspace_id}/documents/{document_id}/retry", headers=owner["headers"]
    )
    assert retry.status_code == 409


def create_empty_pdf_file(tmp_path):
    file_path = tmp_path / "test.pdf"
    c = canvas.Canvas(str(file_path))  # creates a pdf
    c.save()  # writes pdf to disk
    return file_path


@pytest.mark.parametrize(
    "role,expected_status_code",
    [("viewer", 403), ("editor", 202), ("owner", 202), ("stranger", 404), ("anonymous", 401)],
)
async def test_retry_for_diff_users(
    db_session,
    make_user,
    role,
    expected_status_code,
    make_membership,
    make_workspace,
    tmp_path,
    upload_file,
    upload_client,
):
    owner = await make_user("pdfowner@example.com")
    workspace = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    file_path = create_empty_pdf_file(tmp_path)
    doc_response = await upload_file(
        filename="test.pdf",
        content=file_path.read_bytes(),
        workspace_id=workspace["id"],
        headers=owner["headers"],
    )
    assert doc_response.status_code == 202
    assert (
        doc_response.json()["status"] != "done"
    )  # the result json is created before the bg task runs
    result = await db_session.execute(
        select(Document).where(Document.id == doc_response.json()["id"])
    )
    document = result.scalar_one()
    assert document.status == "error"
    assert document.error_message is not None
    workspace_id = workspace["id"]
    document_id = document.id
    headers = {}
    if role == "owner":
        headers = owner["headers"]
    elif role == "viewer" or role == "editor":
        test_user = await make_user("sm@example.com")
        await make_membership(
            workspace_id=workspace_id,
            role=role,
            email=test_user["email"],
            owner_headers=owner["headers"],
        )
        headers = test_user["headers"]
    elif role == "stranger":
        test_user = await make_user("sm@example.com")
        headers = test_user["headers"]

    retry = await upload_client.post(
        f"/workspaces/{workspace_id}/documents/{document_id}/retry", headers=headers
    )
    assert retry.status_code == expected_status_code
