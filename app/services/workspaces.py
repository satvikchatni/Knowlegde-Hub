import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import DbSession
from app.exceptions import Conflict, NotFound
from app.models import Membership, Role, User, WorkSpace
from app.schemas import (
    MemberAdd,
    MemberResponse,
    WorkSpaceCreate,
    WorkSpaceResponse,
)


async def make_workspace(db: DbSession, body: WorkSpaceCreate, user) -> WorkSpaceResponse:
    workspace_name = body.name
    workspace = WorkSpace(name=workspace_name)
    db.add(workspace)
    await db.flush()  # Flushes to generate workspace id
    membership = Membership(workspace_id=workspace.id, user_id=user.id, role=Role.OWNER)
    db.add(membership)  # db.add(...) is synchronous
    await db.commit()
    # no need of db.refresh(workspace) because created_at,name,id come from the insert(flush/commit phase).
    # try,except block unnecessary as when a request fails get_db closes the session immediately and uncommitted work is rolled back automatically.
    return {
        "id": workspace.id,
        "name": workspace.name,
        "role": Role.OWNER,
        "created_at": workspace.created_at,
    }


async def retrieve_workspaces(db: DbSession, user) -> list[WorkSpaceResponse]:
    query = (
        select(WorkSpace, Membership.role)
        .join(Membership, Membership.workspace_id == WorkSpace.id)
        .where(Membership.user_id == user.id)
        .order_by(WorkSpace.created_at.asc())
    )
    # Join's tables and filters by user
    result = await db.execute(query)
    output = []
    for workspace, role in result:
        output.append(
            {
                "id": workspace.id,
                "name": workspace.name,
                "role": role,
                "created_at": workspace.created_at,
            }
        )
    return output


async def retrieve_single_workspace(db: DbSession, user, workspace_id: uuid.UUID):
    query = (
        select(WorkSpace, Membership.role)
        .join(Membership, WorkSpace.id == Membership.workspace_id)
        .where(Membership.user_id == user.id, Membership.workspace_id == workspace_id)
    )
    result = await db.execute(query)
    row = result.one_or_none()
    if row is None:
        raise NotFound(message=f"Workspace with id:{workspace_id}  not found.")
        # raise HTTPException(
        #     status_code=status.HTTP_404_NOT_FOUND,
        #     detail=f"Workspace with id:{workspace_id}  not found.",
        # )
    workspace, role = row
    return {
        "role": role,
        "name": workspace.name,
        "id": workspace.id,
        "created_at": workspace.created_at,
    }


async def add_to_workspace(db: DbSession, body: MemberAdd, membership) -> MemberResponse:
    query = select(User).where(User.email == body.email.lower())
    target_user = (await db.execute(query)).scalar_one_or_none()
    if target_user is None:
        raise NotFound(message="User not found")
        # raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    new_membership = Membership(
        user_id=target_user.id, role=body.role, workspace_id=membership.workspace_id
    )
    try:
        db.add(new_membership)
        await db.commit()
        await db.refresh(new_membership)
        return {"user_id": new_membership.user_id, "email": target_user.email, "role": body.role}
    except IntegrityError:
        await db.rollback()
        raise Conflict(message="user already in workspace") from None
        # raise HTTPException(
        #     status_code=status.HTTP_409_CONFLICT, detail="user already in workspace"
        # ) from None
