import uuid

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import AnyRole, CurrentUser, DbSession, Owner
from app.models import  Membership, Role, User, WorkSpace
from app.schemas import (
    MemberAdd,
    MemberResponse,
    WorkSpaceCreate,
    WorkSpaceResponse,
)
from app.exceptions import NotFound,Conflict
from app.services.workspaces import make_workspace,retrieve_workspaces,retrieve_single_workspace,add_to_workspace
router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkSpaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(db: DbSession, body: WorkSpaceCreate, user: CurrentUser):
    workspace=await make_workspace(db=db,body=body,user=user)
    return workspace


@router.get("", status_code=status.HTTP_200_OK, response_model=list[WorkSpaceResponse])
async def get_workspaces(db: DbSession, user: CurrentUser):
    workspaces=await retrieve_workspaces(db=db,user=user)
    return workspaces
    

@router.get("/{workspace_id}", status_code=status.HTTP_200_OK, response_model=WorkSpaceResponse)
async def get_workspace(
    workspace_id: uuid.UUID, db: DbSession, user: CurrentUser, membership=AnyRole
):
    ws=await retrieve_single_workspace(db=db,user=user,workspace_id=workspace_id)
    return ws
    


@router.post(
    "/{workspace_id}/members", status_code=status.HTTP_201_CREATED, response_model=MemberResponse
)
async def add_user_to_workspace(body: MemberAdd, db: DbSession, membership: Owner):
    user=await add_to_workspace(body=body,db=db,membership=membership)
    return user


