import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query, status
from fastapi.sse import EventSourceResponse
from sqlalchemy import delete, select

from app.db import SessionFactory
from app.deps import AnyRole, CurrentUser, DbSession, Owner, get_embedder, get_llm, prepare_turn
from app.exceptions import NotFound
from app.models import Conversation
from app.schemas import (
    Ask,
    AskOut,
    ConversationIn,
    ConversationOut,
    MemberAdd,
    MemberResponse,
    SearchOut,
    SearchParams,
    WorkSpaceCreate,
    WorkSpaceResponse,
)
from app.services.base_embedder import BaseEmbedder
from app.services.base_llm import LLMClient
from app.services.conversations import stream_turn
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


@router.post(
    "/{workspace_id}/conversations",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    db: DbSession, workspace_id: uuid.UUID, body: ConversationIn, membership: AnyRole
):
    user_id = membership.user_id
    c = Conversation(title=body.title, workspace_id=workspace_id, user_id=user_id)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c
    # return ConversationOut(id=c.id,workspace_id=workspace_id,user_id=user_id,title=body.title,created_at=c.created_at,updated_at=c.updated_at)


@router.get(
    "/{workspace_id}/conversations",
    response_model=list[ConversationOut],
    status_code=status.HTTP_200_OK,
)
async def list_conversations(db: DbSession, workspace_id: uuid.UUID, membership: AnyRole):
    stmt = select(Conversation).where(
        Conversation.workspace_id == workspace_id, Conversation.user_id == membership.user_id
    )
    list_of_convos = (await db.execute(stmt)).scalars().all()
    return list_of_convos


@router.get(
    "/{workspace_id}/conversations/{conversation_id}",
    response_model=ConversationOut,
    status_code=status.HTTP_200_OK,
)
async def get_a_conversation(
    db: DbSession, workspace_id: uuid.UUID, conversation_id: uuid.UUID, membership: AnyRole
):
    user_id = membership.user_id
    stmt = select(Conversation).where(
        Conversation.user_id == user_id,
        Conversation.workspace_id == workspace_id,
        Conversation.id == conversation_id,
    )
    conversation = (await db.execute(stmt)).scalar_one_or_none()
    if conversation is None:
        raise NotFound(f"conversation with id:{conversation_id} doesn't exist")
        # raise HTTPException(
        #     status_code=status.HTTP_404_NOT_FOUND,
        #     detail=f"conversation with id:{conversation_id} doesn't exist"

        # )
    return conversation


@router.delete(
    "/{workspace_id}/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_conversation(
    db: DbSession, workspace_id: uuid.UUID, conversation_id: uuid.UUID, membership: AnyRole
):
    user_id = membership.user_id
    # RETURNING asks pg to return the id of the deleted row(convo)
    query = (
        delete(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
            Conversation.workspace_id == workspace_id,
        )
        .returning(Conversation.id)
    )
    result = (await db.execute(query)).scalar_one_or_none()
    if result is None:
        await db.rollback()
        raise NotFound(f"conversation with id:{conversation_id} doesn't exist")

    await db.commit()


# also since stream_turn is an async generator contains yield, we don't await it
# since prepare_turn already receives body:QuestionIn and reads the request body, declaring it again in the route is redundant
@router.post(
    "/{workspace_id}/conversations/{conversation_id}/stream", response_class=EventSourceResponse
)
async def stream(
    workspace_id: uuid.UUID,
    conversation_id: uuid.UUID,
    llm: Annotated[LLMClient, Depends(get_llm)],
    session_factory: SessionFactory,
    prepared: Annotated[dict, Depends(prepare_turn)],
):  # prepared receives dict returned by prepare_turn
    return EventSourceResponse(
        stream_turn(
            message_id=prepared["message_id"],
            conversation=prepared["conversation"],
            system_prompt=prepared["system_prompt"],
            final_user_prompt=prepared["final_user_prompt"],
            best_chunks=prepared["best_chunks"],
            llm=llm,
            session_factory=session_factory,
        )
    )
