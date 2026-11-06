import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select

from app.deps import AnyRole, CurrentUser, DbSession, Owner, get_embedder
from app.exceptions import EmbeddingServiceUnavailable
from app.models import Chunk, Document
from app.schemas import (
    MemberAdd,
    MemberResponse,
    SearchOut,
    SearchParams,
    WorkSpaceCreate,
    WorkSpaceResponse,
)
from app.services.base_embedder import BaseEmbedder
from app.services.workspaces import (
    add_to_workspace,
    make_workspace,
    retrieve_single_workspace,
    retrieve_workspaces,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkSpaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(db: DbSession, body: WorkSpaceCreate, user: CurrentUser):
    workspace = await make_workspace(db=db, body=body, user=user)
    return workspace


@router.get("", status_code=status.HTTP_200_OK, response_model=list[WorkSpaceResponse])
async def get_workspaces(db: DbSession, user: CurrentUser):
    workspaces = await retrieve_workspaces(db=db, user=user)
    return workspaces


@router.get("/{workspace_id}", status_code=status.HTTP_200_OK, response_model=WorkSpaceResponse)
async def get_workspace(
    workspace_id: uuid.UUID, db: DbSession, user: CurrentUser, membership=AnyRole
):
    ws = await retrieve_single_workspace(db=db, user=user, workspace_id=workspace_id)
    return ws


@router.post(
    "/{workspace_id}/members", status_code=status.HTTP_201_CREATED, response_model=MemberResponse
)
async def add_user_to_workspace(body: MemberAdd, db: DbSession, membership: Owner):
    user = await add_to_workspace(body=body, db=db, membership=membership)
    return user


@router.get(
    "/{workspace_id}/search", status_code=status.HTTP_200_OK, response_model=list[SearchOut]
)
async def search(
    db: DbSession,
    workspace_id: uuid.UUID,
    filter_params: Annotated[SearchParams, Query()],
    membership: AnyRole,
    embedder: Annotated[BaseEmbedder, Depends(get_embedder)],
):
    try:
        vectors = await embedder.embed_documents(texts=[filter_params.q], is_query=True)
        if len(vectors) != 1:
            raise EmbeddingServiceUnavailable(
                "Invalid embedding response"
            )  # check that only 1 vector was returned
        q = vectors[0]  # since we have embedded only one query
        dist = Chunk.embedding.cosine_distance(q).label(
            "distance"
        )  # maps the mathematical distance between the stored document and the query asked.
    except EmbeddingServiceUnavailable:
        raise  # if EmbeddingServiceUnavailable is raise this block catches it and re-raises it unchanged,w/o this the except Exception block would get triggered and would display a mssg not suitable to the error
    except Exception as e:  # any unexpected errors this runs
        raise EmbeddingServiceUnavailable(
            "Embedding service is currently down"
        ) from e  # from e: preserves the explicit exception as the cause of the error
        # from None :suppresses the original exception's display in the traceback
    stmt = (
        select(
            Chunk.text,
            dist,
            Document.filename,
            Chunk.document_id,
            Chunk.page_number,
            Chunk.id,
            Chunk.position,
        )
        .join(Document)
        .where(Chunk.workspace_id == workspace_id, Chunk.embedding.is_not(None))
        .order_by(dist)
        .limit(filter_params.limit)
    )  # join(Document) uses the foreign key relationship between the two tables, SQL understands that document.id sud equal chunk.document_id,so no need of adding that to the .where() clause.
    result = await db.execute(stmt)
    rows = result.all()  # .scalars() would drop the dist column,so don't use that in situations where you  require both(text,dist)
    if not rows:
        return []
    result = []
    for row in rows:
        item = {
            "chunk_id": row.id,
            "document_id": row.document_id,
            "filename": row.filename,
            "page_number": row.page_number,
            "position": row.position,
            "text": row.text,
            "score": 1.0
            - float(row.distance),  # score equals similarity more the similarity,the better
        }
        result.append(item)
    return result
