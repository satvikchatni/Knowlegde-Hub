import uuid
from typing import Annotated

from arq.connections import ArqRedis  # redis pool type
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, status
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy import select

from app.deps import (
    AnyRole,
    DbSession,
    EditorandAbove,
    get_queue,
)
from app.exceptions import Conflict, NotFound
from app.models import Document
from app.schemas import (
    DocumentResponse,
    ListRequest,
    ListResponse,
)
from app.services.documents import delete_a_document, file_upload, get_a_document, list_of_documents

router = APIRouter(prefix="/workspaces/{workspace_id}/documents", tags=["documents"])

# replaced with task-queue
# @router.post(
#     "",
#     status_code=status.HTTP_202_ACCEPTED,
#     response_model=DocumentResponse,
# )
# async def upload_file(
#     workspace_id: uuid.UUID,
#     file: UploadFile,
#     db: DbSession,
#     membership: EditorandAbove,
#     background_tasks: BackgroundTasks,
#     factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
#     embedder: Annotated[BaseEmbedder, Depends(get_embedder)],
# ):
#     doc = await file_upload(workspace_id=workspace_id, file=file, db=db)
#     background_tasks.add_task(
#         process_document, document_id=doc.id, session_factory=factory, embedder=embedder
#     )
#     return doc

Queue = Annotated[ArqRedis, Depends(get_queue)]


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DocumentResponse,
    summary="To upload a document",
)
async def upload_file(
    workspace_id: uuid.UUID,
    file: UploadFile,
    db: DbSession,
    membership: EditorandAbove,
    queue: Queue,
    request: Request,
):
    doc = await file_upload(workspace_id=workspace_id, file=file, db=db)
    try:
        job=await queue.enqueue_job(
            "process_doc_job", str(doc.id), request.state.request_id, _job_id=f"ingest:{doc.id}"
        )
        print("enqueued job:",job)
    except (RedisTimeoutError, RedisConnectionError) as e:
        document = (
            await db.execute(
                select(Document).where(Document.id == doc.id, Document.workspace_id == workspace_id)
            )
        ).scalar_one_or_none()
        if document is not None:
            document.status = "error"
            document.error_message = "Redis is unavailable.Please retry later."
            await db.commit()
        raise HTTPException(status_code=503, detail="Redis is down,try again later") from e
    return doc


@router.get(
    "", response_model=ListResponse, status_code=status.HTTP_200_OK, summary="List of documents"
)
async def get_list_of_document(
    filter_query: Annotated[ListRequest, Query()],
    db: DbSession,
    membership: AnyRole,
    workspace_id: uuid.UUID,
):
    list_of_docs = await list_of_documents(
        db=db, workspace_id=workspace_id, filter_query=filter_query
    )
    return list_of_docs


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="To get a particular document",
)
async def get_document(
    workspace_id: uuid.UUID, document_id: uuid.UUID, db: DbSession, membership: AnyRole
):
    document = await get_a_document(workspace_id=workspace_id, document_id=document_id, db=db)
    return document


@router.delete(
    "/{document_id}", status_code=status.HTTP_204_NO_CONTENT, summary="To delete a document"
)
async def delete_document(
    db: DbSession, workspace_id: uuid.UUID, document_id: uuid.UUID, membership: EditorandAbove
):
    await delete_a_document(db=db, workspace_id=workspace_id, document_id=document_id)


# @router.post("/{document_id}/retry", status_code=status.HTTP_202_ACCEPTED)
# async def retry(
#     db: DbSession,
#     workspace_id: uuid.UUID,
#     document_id: uuid.UUID,
#     membership: EditorandAbove,
#     background_tasks: BackgroundTasks,
#     factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
#     embedder: Annotated[BaseEmbedder, Depends(get_embedder)],
# ):
#     stmt = select(Document).where(Document.workspace_id == workspace_id, Document.id == document_id)
#     document = (await db.execute(stmt)).scalar_one_or_none()
#     if document is None:
#         raise NotFound(
#             f"Document with id {document_id} doesnt exist in workspace with id:{workspace_id}"
#         )
#     if document.status == "error":
#         document.status = "queued"
#         document.error_message = None
#         await db.commit()
#         background_tasks.add_task(
#             process_document, document_id=document_id, session_factory=factory, embedder=embedder
#         )
#         return document
#     else:
#         raise Conflict("Document can only be retried if it's status is error")


@router.post(
    "/{document_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry document processing",
)
async def retry(
    db: DbSession,
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    membership: EditorandAbove,
    queue: Queue,
    request: Request,
):
    stmt = select(Document).where(Document.workspace_id == workspace_id, Document.id == document_id)
    document = (await db.execute(stmt)).scalar_one_or_none()
    if document is None:
        raise NotFound(
            f"Document with id {document_id} doesnt exist in workspace with id:{workspace_id}"
        )
    if document.status == "error":
        document.status = "queued"
        document.error_message = None
        await db.commit()
        try:
            await queue.enqueue_job(
                "process_doc_job",
                str(document.id),
                request.state.request_id,
                _job_id=f"ingest:{document.id}",
            )  # job
        except (RedisTimeoutError, RedisConnectionError) as e:
            document = (
                await db.execute(
                    select(Document).where(
                        Document.id == document.id, Document.workspace_id == workspace_id
                    )
                )
            ).scalar_one_or_none()
            if document is not None:
                document.status = "error"
                document.error_message = "Redis is unavailable.Please retry later."
                await db.commit()
            raise HTTPException(status_code=503, detail="Redis is down,try again later") from e
        return document
    else:
        raise Conflict("Document can only be retried if it's status is error")
