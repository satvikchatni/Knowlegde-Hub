import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query, status

from app.deps import AnyRole, CurrentUser, DbSession, Owner, get_embedder, get_llm
from app.schemas import (
    Ask,
    AskOut,
    MemberAdd,
    MemberResponse,
    SearchOut,
    SearchParams,
    WorkSpaceCreate,
    WorkSpaceResponse,
)
from app.services.base_embedder import BaseEmbedder
from app.services.base_llm import LLMClient
from app.services.workspaces import (
    add_to_workspace,
    ask,
    make_workspace,
    retrieve,
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
    return await retrieve(
        db=db, workspace_id=workspace_id, filter_params=filter_params, embedder=embedder
    )


@router.post("/{workspace_id}/ask", status_code=status.HTTP_200_OK, response_model=AskOut)
async def ask_question(
    db: DbSession,
    workspace_id: uuid.UUID,
    membership: AnyRole,
    embedder: Annotated[BaseEmbedder, Depends(get_embedder)],
    llm: Annotated[LLMClient, Depends(get_llm)],
    ask_params: Annotated[
        Ask, Body()
    ],  # /ask sud receive a JSON request body like {"question":"....."}
):
    answer = await ask(
        db=db, workspace_id=workspace_id, embedder=embedder, llm=llm, ask_params=ask_params
    )
    return answer
