import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from sqlalchemy import delete, func, select

from app.config import settings
from app.deps import AnyRole, DbSession, EditorandAbove
from app.models import Document, DocumentStatus
from app.schemas import (
    DocumentResponse,
    ListRequest,
    ListResponse,
)
from app.services.storage import StorageService
from app.exceptions import NotFound,TooLarge,UnsupportedType

router=APIRouter(prefix="/workspaces/{workspace_id}/documents",tags=["documents"])

@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DocumentResponse,
)
async def upload_file(
    workspace_id: uuid.UUID, file: UploadFile, db: DbSession, membership: EditorandAbove
):
    if file.size == 0:
        
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="file is empty"
        )
    if file.size > (settings.max_upload_mb * 1024 * 1024):  # convert megabytes in settings to bytes
        raise TooLarge(message="file too large")
        # raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="file too large")
    storage = StorageService(upload_dir=settings.upload_dir)

    try:
        file_type = storage.verify_file_type(file.file)
    except ValueError: #use raise X from None in except block to hide low-level internal errors and to remove extra traceback
        raise UnsupportedType(
            message="wrong type of file, or content doesn't match extension."
        )
        # raise HTTPException(
        #     status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        #     detail="wrong type of file, or content doesn't match extension.",
        # ) from None
    if file_type == "text/plain" and file.filename.lower().endswith(
        ".pdf"
    ):  # important verification
        raise UnsupportedType(
                    message="wrong type of file, or content doesn't match extension."
                )
    if file_type == "application/pdf" and file.filename.lower().endswith(".txt"):
        raise UnsupportedType(
                    message="wrong type of file, or content doesn't match extension."
                )
    if (
        file.filename.lower().endswith(".txt") is False
        and file.filename.lower().endswith(".pdf") is False
    ):
        raise UnsupportedType(
                    message="wrong type of file, or content doesn't match extension."
                )
    clean_name = storage.clean_display_name(file.filename)
    document_id = uuid.uuid4()
    relative_path = await storage.save_file(
        file=file, workspace_id=workspace_id, document_id=document_id
    )
    try:
        document = Document(
            id=document_id,
            workspace_id=workspace_id,
            filename=clean_name,
            content_type=file_type,
            size_bytes=file.size,
            status=DocumentStatus.uploaded,
            storage_path=relative_path,
        )
        db.add(document)
        await db.commit()
        await db.refresh(document)
        return document
    except Exception as e:
        await db.rollback()
        await storage.delete_file(relative_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save record document to the database",
        ) from e


@router.get(
    "", response_model=ListResponse, status_code=status.HTTP_200_OK
)
async def get_list_of_document(
    filter_query: Annotated[ListRequest, Query()],
    db: DbSession,
    membership: AnyRole,
    workspace_id: uuid.UUID,
):
    # query=select(Document).where(Document.workspace_id==workspace_id).order_by(Document.created_at.desc()).limit(filter_query.limit).offset(filter_query.offset)#offset=20:skips the first 20 rows
    # result=await db.execute(query)
    # document_list=result.scalars().all()
    # count= await db.scalar(select(func.count(Document.id)).where(Document.workspace_id==workspace_id))
    # return {
    #     "items":document_list,
    #     "total":count,
    #     "limit":filter_query.limit,
    #     "offset":filter_query.offset
    # }
    base_filter = [Document.workspace_id == workspace_id]
    if (
        hasattr(filter_query, "status") and filter_query.status
    ):  # check if filter_query has the attribute status first then check if it has a value(other than None obv)
        base_filter.append(Document.status == filter_query.status)
    count = await db.scalar(select(func.count(Document.id)).where(*base_filter))
    query = (
        select(Document)
        .where(*base_filter)
        .order_by(Document.created_at.desc())
        .limit(filter_query.limit)
        .offset(filter_query.offset)
    )
    result = await db.execute(query)
    document_list = result.scalars().all()
    return {
        "items": document_list,
        "total": count,
        "limit": filter_query.limit,
        "offset": filter_query.offset,
    }


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
)
async def get_document(
    workspace_id: uuid.UUID, document_id: uuid.UUID, db: DbSession, membership: AnyRole
):
    stmt = select(Document).where(Document.id == document_id, Document.workspace_id == workspace_id)
    result = await db.execute(stmt)
    document = result.scalar_one_or_none()
    if document is None:
        raise NotFound(
            message=f"document with id:{document_id} doesn't exist in this workspace"
        )
        # raise HTTPException(
        #     status_code=status.HTTP_404_NOT_FOUND,
        #     detail=f"document with id:{document_id} doesn't exist in this workspace",
        # )
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    db: DbSession, workspace_id: uuid.UUID, document_id: uuid.UUID, membership: EditorandAbove
):
    stmt = select(Document).where(Document.id == document_id, Document.workspace_id == workspace_id)
    document = await db.scalar(stmt)

    if not document:
        raise NotFound(
                    message=f"document with id:{document_id} doesn't exist in this workspace"
                )
        # raise HTTPException(
        #     status_code=status.HTTP_404_NOT_FOUND,
        #     detail=f"document with id:{document_id} not found",
        # )
    relative_path = document.storage_path
    query = delete(Document).where(
        Document.id == document_id, Document.workspace_id == workspace_id
    )  # we use delete(...) instead of select(...) for deletion operations.
    await db.execute(query)
    await db.commit()

    storage = StorageService(upload_dir=settings.upload_dir)
    await storage.delete_file(relative_path)  # delete_file is a asynchronous
