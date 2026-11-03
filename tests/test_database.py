from sqlalchemy import delete, select

from app.models import Chunk, Document


def create_file(tmp_path):
    file_path = tmp_path / "test.txt"
    file_path.write_text("Text to process,this is our testing phase", encoding="utf-8")
    return file_path


async def test_txt_file_processing(db_session, make_user, make_workspace, tmp_path, upload_file):
    owner = await make_user("owner@example.com")
    workspace = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
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
    r = await db_session.execute(
        select(Chunk).where(Chunk.document_id == document.id, Chunk.workspace_id == workspace["id"])
    )
    assert r.scalar_one_or_none is not None
    # deletion of document
    await db_session.execute(
        delete(Document).where(Document.id == document.id, Document.workspace_id == workspace["id"])
    )
    res = await db_session.execute(
        select(Chunk).where(Chunk.document_id == document.id, Chunk.workspace_id == workspace["id"])
    )
    chunks = res.scalar_one_or_none()
    assert chunks is None
