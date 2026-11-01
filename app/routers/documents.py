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
from app.services.documents import file_upload,list_of_documents,get_a_document,delete_a_document

router=APIRouter(prefix="/workspaces/{workspace_id}/documents",tags=["documents"])

@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DocumentResponse,
)
async def upload_file(
    workspace_id: uuid.UUID, file: UploadFile, db: DbSession, membership: EditorandAbove
):
    doc=await file_upload(workspace_id=workspace_id,file=file,db=db)
    return doc
    


@router.get(
    "", response_model=ListResponse, status_code=status.HTTP_200_OK
)
async def get_list_of_document(
    filter_query: Annotated[ListRequest, Query()],
    db: DbSession,
    membership: AnyRole,
    workspace_id: uuid.UUID,
):
    list_of_docs=await list_of_documents(db=db,workspace_id=workspace_id,filter_query=filter_query)
    return list_of_docs
    


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
)
async def get_document(
    workspace_id: uuid.UUID, document_id: uuid.UUID, db: DbSession, membership: AnyRole
):
    document=await get_a_document(workspace_id=workspace_id,document_id=document_id,db=db)
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    db: DbSession, workspace_id: uuid.UUID, document_id: uuid.UUID, membership: EditorandAbove
):
    await delete_a_document(db=db,workspace_id=workspace_id,document_id=document_id)