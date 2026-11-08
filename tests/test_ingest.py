import pytest
from sqlalchemy import select

from app.config import settings
from app.deps import get_embedder
from app.main import app
from app.models import Chunk, Document
from tests.fakes import FailingEmbedder, WrongDimEmbedder


def create_file(tmp_path):
    file_path = tmp_path / "test.txt"
    file_path.write_text("Text to process,this is our testing phase", encoding="utf-8")
    return file_path


async def test_processed_docs_chunks_have_rightdim_vectors(
    db_session, client, tmp_path, make_user, make_workspace, upload_file
):
    owner = await make_user("owner@example.com")
    ws = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    file_path = create_file(tmp_path)
    doc_response = await upload_file(
        filename="test.txt",
        content=file_path.read_bytes(),
        workspace_id=ws["id"],
        headers=owner["headers"],
    )
    assert doc_response.status_code == 202
    r = await db_session.execute(select(Document).where(Document.id == doc_response.json()["id"]))
    document = r.scalar_one()
    assert document.status == "done"
    document_id = doc_response.json()["id"]
    result = await db_session.execute(
        select(Chunk).where(Chunk.document_id == document_id, Chunk.workspace_id == workspace_id)
    )
    chunks = result.scalars().all()
    assert chunks
    assert all(len(chunk.embedding) == settings.expected_dimension_size for chunk in chunks)


def create_larger_file(tmp_path):
    file_path = tmp_path / "test.txt"
    file_path.write_text("a" * 70, encoding="utf-8")
    return file_path


async def test_batching(
    monkeypatch, db_session, tmp_path, make_user, make_workspace, upload_file, fake_embedder
):
    monkeypatch.setattr(settings, "embedding_batch_size", 2)
    monkeypatch.setattr(settings, "chunk_size", 20)
    monkeypatch.setattr(settings, "chunk_overlap", 5)
    owner = await make_user("owner@example.com")
    ws = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    file_path = create_larger_file(tmp_path)
    doc_response = await upload_file(
        filename="test.txt",
        content=file_path.read_bytes(),
        workspace_id=ws["id"],
        headers=owner["headers"],
    )
    assert doc_response.status_code == 202
    r = await db_session.execute(select(Document).where(Document.id == doc_response.json()["id"]))
    document = r.scalar_one()
    assert document.status == "done"
    document_id = doc_response.json()["id"]
    result = await db_session.execute(
        select(Chunk).where(Chunk.document_id == document_id, Chunk.workspace_id == workspace_id)
    )
    chunks = result.scalars().all()
    # Debugging:both were set to 1000 and 150 respectively
    # print("chunk size",settings.chunk_size)
    # print("chunk overlap",settings.chunk_overlap)
    assert len(chunks) == 5
    assert fake_embedder.batch_sizes == [2, 2, 1]


async def test_embedder_failure(
    db_session, client, tmp_path, make_user, make_workspace, upload_file
):
    app.dependency_overrides[get_embedder] = lambda: FailingEmbedder()
    owner = await make_user("owner@example.com")
    ws = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    file_path = create_file(tmp_path)
    doc_response = await upload_file(
        filename="test.txt",
        content=file_path.read_bytes(),
        workspace_id=ws["id"],
        headers=owner["headers"],
    )
    assert doc_response.status_code == 202
    r = await db_session.execute(select(Document).where(Document.id == doc_response.json()["id"]))
    document = r.scalar_one()
    assert document.status == "error"
    document_id = doc_response.json()["id"]
    result = await db_session.execute(
        select(Chunk).where(Chunk.document_id == document_id, Chunk.workspace_id == workspace_id)
    )
    chunks = result.scalars().all()
    assert not chunks


async def test_embedder_returning_wrongdim_vectors(
    db_session, client, tmp_path, make_user, make_workspace, upload_file
):
    app.dependency_overrides[get_embedder] = lambda: WrongDimEmbedder()
    owner = await make_user("owner@example.com")
    ws = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    file_path = create_file(tmp_path)
    doc_response = await upload_file(
        filename="test.txt",
        content=file_path.read_bytes(),
        workspace_id=ws["id"],
        headers=owner["headers"],
    )
    assert doc_response.status_code == 202
    r = await db_session.execute(select(Document).where(Document.id == doc_response.json()["id"]))
    document = r.scalar_one()
    assert document.status == "error"
    document_id = doc_response.json()["id"]
    result = await db_session.execute(
        select(Chunk).where(Chunk.document_id == document_id, Chunk.workspace_id == workspace_id)
    )
    chunks = result.scalars().all()
    assert not chunks


def create_search_file(tmp_path):
    file_path = tmp_path / "test.txt"
    file_path.write_text("apple orange beetroot", encoding="utf-8")  # i don't like beetroot
    return file_path


async def test_search_best_chunks_come_first(
    db_session, client, tmp_path, make_user, make_workspace, upload_file, monkeypatch
):
    monkeypatch.setattr(settings, "chunk_size", 7)
    monkeypatch.setattr(settings, "chunk_overlap", 1)
    owner = await make_user("owner@example.com")
    ws = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    file_path = create_search_file(tmp_path)
    doc_response = await upload_file(
        filename="test.txt",
        content=file_path.read_bytes(),
        workspace_id=ws["id"],
        headers=owner["headers"],
    )
    assert doc_response.status_code == 202
    r = await db_session.execute(select(Document).where(Document.id == doc_response.json()["id"]))
    document = r.scalar_one()
    assert document.status == "done"
    stmt = select(Chunk).where(
        Chunk.workspace_id == workspace_id, Chunk.document_id == doc_response.json()["id"]
    )
    chunks = (await db_session.execute(stmt)).scalars().all()
    assert chunks
    assert len(chunks) == 4
    # print([chunk.text for chunk in chunks])
    res = await client.get(
        f"/workspaces/{workspace_id}/search",
        headers=owner["headers"],
        params={"q": "orange", "limit": 3},
    )
    assert res.status_code == 200
    assert res.json()[0]["score"] == 1.0  # orange equals orange
    # print(res.json())


async def test_search_empty_q(
    db_session, client, tmp_path, make_user, make_workspace, upload_file, monkeypatch
):
    owner = await make_user("owner@example.com")
    ws = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    file_path = create_search_file(tmp_path)
    doc_response = await upload_file(
        filename="test.txt",
        content=file_path.read_bytes(),
        workspace_id=ws["id"],
        headers=owner["headers"],
    )
    assert doc_response.status_code == 202
    r = await db_session.execute(select(Document).where(Document.id == doc_response.json()["id"]))
    document = r.scalar_one()
    assert document.status == "done"
    stmt = select(Chunk).where(
        Chunk.workspace_id == workspace_id, Chunk.document_id == doc_response.json()["id"]
    )
    chunks = (await db_session.execute(stmt)).scalars().all()
    assert chunks
    res = await client.get(
        f"/workspaces/{workspace_id}/search", headers=owner["headers"], params={"q": "", "limit": 3}
    )
    assert res.status_code == 422


async def test_search_long_q(
    db_session, client, tmp_path, make_user, make_workspace, upload_file, monkeypatch
):
    owner = await make_user("owner@example.com")
    ws = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    file_path = create_search_file(tmp_path)
    doc_response = await upload_file(
        filename="test.txt",
        content=file_path.read_bytes(),
        workspace_id=ws["id"],
        headers=owner["headers"],
    )
    assert doc_response.status_code == 202
    r = await db_session.execute(select(Document).where(Document.id == doc_response.json()["id"]))
    document = r.scalar_one()
    assert document.status == "done"
    stmt = select(Chunk).where(
        Chunk.workspace_id == workspace_id, Chunk.document_id == doc_response.json()["id"]
    )
    chunks = (await db_session.execute(stmt)).scalars().all()
    assert chunks
    res = await client.get(
        f"/workspaces/{workspace_id}/search",
        headers=owner["headers"],
        params={"q": "q" * 600, "limit": 3},
    )
    assert res.status_code == 422


# no docs have been uploaded
async def test_search_no_embedded_chunks(make_user, make_workspace, client):
    owner = await make_user("owner@example.com")
    ws = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    res = await client.get(
        f"/workspaces/{workspace_id}/search",
        headers=owner["headers"],
        params={"q": "mar", "limit": 3},
    )
    assert res.status_code == 200
    assert res.json() == []


# Even is one ws has closer chunk,doesnt appear for other workspace
async def test_search_isolation(
    db_session, client, tmp_path, make_user, make_workspace, upload_file, monkeypatch
):
    # workspace A
    owner1 = await make_user("owner1@example.com")
    ws1 = await make_workspace(workspace_name="testws", user_headers=owner1["headers"])
    workspace_id1 = ws1["id"]
    file_path1 = create_search_file(tmp_path)
    doc_response1 = await upload_file(
        filename="test.txt",
        content=file_path1.read_bytes(),
        workspace_id=ws1["id"],
        headers=owner1["headers"],
    )
    assert doc_response1.status_code == 202
    r1 = await db_session.execute(select(Document).where(Document.id == doc_response1.json()["id"]))
    document1 = r1.scalar_one()
    assert document1.status == "done"
    stmt = select(Chunk).where(
        Chunk.workspace_id == workspace_id1, Chunk.document_id == doc_response1.json()["id"]
    )
    chunks1 = (await db_session.execute(stmt)).scalars().all()
    assert chunks1

    # workspace B
    owner2 = await make_user("owner2@example.com")
    ws2 = await make_workspace(workspace_name="testws", user_headers=owner2["headers"])
    workspace_id2 = ws2["id"]
    file_path2 = create_file(tmp_path)
    doc_response2 = await upload_file(
        filename="test.txt",
        content=file_path2.read_bytes(),
        workspace_id=ws2["id"],
        headers=owner2["headers"],
    )
    assert doc_response2.status_code == 202
    r2 = await db_session.execute(select(Document).where(Document.id == doc_response2.json()["id"]))
    document2 = r2.scalar_one()
    assert document2.status == "done"
    stmt = select(Chunk).where(
        Chunk.workspace_id == workspace_id2, Chunk.document_id == doc_response2.json()["id"]
    )
    chunks2 = (await db_session.execute(stmt)).scalars().all()
    assert chunks2

    res = await client.get(
        f"/workspaces/{workspace_id2}/search",
        headers=owner2["headers"],
        params={"q": "orange", "limit": 3},
    )
    assert res.status_code == 200
    returned_ids = [item["document_id"] for item in res.json()]
    assert str(doc_response1.json()["id"]) not in returned_ids
    returned_text = [item["text"] for item in res.json()]
    assert "apple orange beetroot" not in returned_text
    print(res.json())


@pytest.mark.parametrize(
    "role,expected_status_code",
    [("viewer", 200), ("owner", 200), ("editor", 200), ("anonymous", 401), ("stranger", 404)],
)
async def test_matrix_search(
    make_user,
    client,
    make_workspace,
    role,
    expected_status_code,
    tmp_path,
    db_session,
    upload_file,
    make_membership,
):
    owner = await make_user("owner@example.com")
    ws = await make_workspace(workspace_name="testws", user_headers=owner["headers"])
    workspace_id = ws["id"]
    file_path = create_search_file(tmp_path)
    doc_response = await upload_file(
        filename="test.txt",
        content=file_path.read_bytes(),
        workspace_id=ws["id"],
        headers=owner["headers"],
    )
    assert doc_response.status_code == 202
    r = await db_session.execute(select(Document).where(Document.id == doc_response.json()["id"]))
    document = r.scalar_one()
    assert document.status == "done"
    stmt = select(Chunk).where(
        Chunk.workspace_id == workspace_id, Chunk.document_id == doc_response.json()["id"]
    )
    chunks = (await db_session.execute(stmt)).scalars().all()
    assert chunks
    test_user = await make_user("user@example.com")
    headers = {}
    if role == "owner":
        headers = owner["headers"]
    elif role == "viewer" or role == "editor":
        await make_membership(
            workspace_id=workspace_id,
            role=role,
            email=test_user["email"],
            owner_headers=owner["headers"],
        )
        headers = test_user["headers"]
    elif role == "stranger":
        headers = test_user["headers"]
    res = await client.get(
        f"/workspaces/{workspace_id}/search", headers=headers, params={"q": "orange", "limit": 3}
    )
    assert res.status_code == expected_status_code
