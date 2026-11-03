import uuid

from reportlab.pdfgen import canvas  # allows you to create pdfs
from sqlalchemy import select

from app.models import Chunk, Document
from app.services.processing import process_document


def create_pdf_file(tmp_path):
    file_path = tmp_path / "test.pdf"
    c = canvas.Canvas(str(file_path))  # creates a pdf
    c.drawString(100, 500, "this is page 1")  # writes text at (x,y) pos
    c.showPage()  # ends current page and starts next one
    c.drawString(100, 500, "this is page 2")
    c.showPage()
    c.save()  # writes pdf to disk
    return file_path


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
    chunks = r.scalars().all()
    assert len(chunks) > 0
    for chunk in chunks:
        assert chunk.workspace_id == uuid.UUID(workspace["id"])
        assert chunk.document_id == document.id
        print(chunk.text)
    positions = [chunk.position for chunk in chunks]
    assert positions == list(range(len(chunks)))


async def test_pdf_file_processing(db_session, make_user, make_workspace, tmp_path, upload_file):
    owner = await make_user("pdfowner@example.com")
    workspace = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    file_path = create_pdf_file(tmp_path)
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
    assert document.status == "done"
    r = await db_session.execute(
        select(Chunk).where(Chunk.document_id == document.id, Chunk.workspace_id == workspace["id"])
    )
    chunks = r.scalars().all()
    assert len(chunks) > 0
    for chunk in chunks:
        assert chunk.workspace_id == uuid.UUID(workspace["id"])
        assert chunk.document_id == document.id

        print(chunk.text)
    positions = [chunk.position for chunk in chunks]  # list comprehension
    assert positions == list(range(len(chunks)))
    pages = {chunk.page_number for chunk in chunks}  # set comprehension,no need to call set()
    assert pages == {1, 2}


def create_empty_pdf_file(tmp_path):
    file_path = tmp_path / "test.pdf"
    c = canvas.Canvas(str(file_path))  # creates a pdf
    c.save()  # writes pdf to disk
    return file_path


async def test_empty_pdf_file_processing(
    db_session, make_user, make_workspace, tmp_path, upload_file
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
    r = await db_session.execute(
        select(Chunk).where(Chunk.document_id == document.id, Chunk.workspace_id == workspace["id"])
    )
    chunks = r.scalars().all()
    assert len(chunks) == 0
    assert document.error_message


async def test_run_job_twice(
    db_session, make_user, make_workspace, tmp_path, upload_file, session_factory
):
    owner = await make_user("pdfowner@example.com")
    workspace = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    file_path = create_pdf_file(tmp_path)
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
    assert document.status == "done"
    r1 = await db_session.execute(
        select(Chunk).where(Chunk.document_id == document.id, Chunk.workspace_id == workspace["id"])
    )
    chunks1 = r1.scalars().all()
    await process_document(
        document_id=doc_response.json()["id"], session_factory=session_factory
    )
    r2 = await db_session.execute(
        select(Chunk).where(Chunk.document_id == document.id, Chunk.workspace_id == workspace["id"])
    )
    chunks2 = r2.scalars().all()
    assert len(chunks1) == len(chunks2)
    positions = [chunk.position for chunk in chunks2]
    assert positions == list(range(len(chunks1)))
    assert [c1.text for c1 in chunks1] == [c2.text for c2 in chunks2]
