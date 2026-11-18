import pytest
from arq import Retry
from sqlalchemy import select

from app.exceptions import InvalidFile
from app.models import Chunk, Document
from app.services.processing import process_document
from app.worker import process_doc_job


async def test_upload_enqueues_job(client, make_user, make_workspace, fake_queue):
    owner = await make_user("owner@example.com")
    workspace = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = workspace["id"]
    res = await client.post(
        f"/workspaces/{workspace_id}/documents",
        headers=owner["headers"],
        files={"file": ("test.txt", b"tests suck", "text/plain")},
    )

    assert res.status_code == 202
    assert res.json()["status"] == "queued"
    assert len(fake_queue.calls)
    assert fake_queue.calls[0]["function_name"] == "process_doc_job"


async def test_retry_doc(client, make_user, make_workspace, fake_queue, db_session):
    owner = await make_user("owner@example.com")
    workspace = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = workspace["id"]
    res = await client.post(
        f"/workspaces/{workspace_id}/documents",
        headers=owner["headers"],
        files={"file": ("test.txt", b"tests suck", "text/plain")},
    )
    document_id = res.json()["id"]

    document = (
        await db_session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one()
    document.status = "error"
    document.error_message = "error for test retry endpt"
    await db_session.commit()

    res = await client.post(
        f"/workspaces/{workspace_id}/documents/{document_id}/retry", headers=owner["headers"]
    )

    assert res.status_code == 202
    assert res.json()["status"] == "queued"
    assert len(fake_queue.calls)
    assert fake_queue.calls[0]["function_name"] == "process_doc_job"
    assert fake_queue.calls[0]["_job_id"] == f"ingest:{document_id}"


async def test_happy_path_task(
    client, make_user, make_workspace, fake_queue, db_session, session_factory, fake_embedder
):
    owner = await make_user("owner@example.com")
    workspace = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = workspace["id"]
    res = await client.post(
        f"/workspaces/{workspace_id}/documents",
        headers=owner["headers"],
        files={"file": ("test.txt", b"tests suck", "text/plain")},
    )
    document_id = res.json()["id"]
    # since task-queues we have two seperate processes now
    await process_document(
        document_id=document_id, session_factory=session_factory, embedder=fake_embedder
    )

    document = (
        await db_session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one()

    chunks_after_first_run = (
        (await db_session.execute(select(Chunk).where(Chunk.document_id == document_id)))
        .scalars()
        .all()
    )

    assert document.status == "done"
    assert len(chunks_after_first_run) > 0
    # second run, idempotency
    await process_document(
        document_id=document_id, session_factory=session_factory, embedder=fake_embedder
    )

    document = (
        await db_session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one()

    chunks_after_second_run = (
        (await db_session.execute(select(Chunk).where(Chunk.document_id == document_id)))
        .scalars()
        .all()
    )

    assert len(chunks_after_second_run) == len(chunks_after_first_run)


def fake_file_extraction(
    **kwargs,
):  # **kwargs mean accept any keyword argument passed to the function, here we want it to act as file_extraction fn, can also pass file_path instead to be more specific
    raise InvalidFile("for tests ahahaehheh")


async def test_permanent_error(
    client,
    make_user,
    make_workspace,
    fake_queue,
    db_session,
    session_factory,
    fake_embedder,
    monkeypatch,
):
    owner = await make_user("owner@example.com")
    workspace = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = workspace["id"]
    res = await client.post(
        f"/workspaces/{workspace_id}/documents",
        headers=owner["headers"],
        files={"file": ("test.txt", b"tests suck", "text/plain")},
    )
    document_id = res.json()["id"]

    monkeypatch.setattr("app.services.processing.file_extraction", fake_file_extraction)
    await process_document(
        document_id=document_id, session_factory=session_factory, embedder=fake_embedder
    )
    document = (
        await db_session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one()
    assert document.status == "error"
    assert document.error_message == "for tests ahahaehheh"


class failingembedder:
    async def embed_documents(self, **kwargs):
        raise ConnectionError("embedder took too long")


async def test_temp_error(
    db_session, client, make_user, make_workspace, fake_embedder, session_factory, monkeypatch
):
    ctx = {"session_factory": session_factory, "embedder": failingembedder(), "job_try": 1}
    owner = await make_user("owner@example.com")
    workspace = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = workspace["id"]
    res = await client.post(
        f"/workspaces/{workspace_id}/documents",
        headers=owner["headers"],
        files={"file": ("test.txt", b"tests suck", "text/plain")},
    )
    document_id = res.json()["id"]

    with pytest.raises(Retry):
        await process_doc_job(ctx, document_id)

    ctx["job_try"] = 4

    await process_doc_job(ctx, document_id)
    document = (
        await db_session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one()
    assert document.status == "error"

    assert document.error_message == "Reached max number of re-tries"
