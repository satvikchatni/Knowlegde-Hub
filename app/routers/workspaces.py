from fastapi import APIRouter,status,HTTPException
from app.schemas import WorkSpaceCreate,WorkSpaceResponse,MemberAdd,MemberResponse
from app.deps import DbSession,CurrentUser,Owner,AnyRole
from app.models import WorkSpace,Membership,User,Role
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
import uuid
from typing import List
router=APIRouter(prefix="/workspaces",tags=["workspaces"])


@router.post("",response_model=WorkSpaceResponse,status_code=status.HTTP_201_CREATED)
async def create_workspace(db:DbSession,body:WorkSpaceCreate,user:CurrentUser):
    workspace_name=body.name
    workspace=WorkSpace(name=workspace_name)
    db.add(workspace)
    await db.flush()#Flushes to generate workspace id
    membership=Membership(workspace_id=workspace.id,user_id=user.id,role=Role.OWNER)
    db.add(membership)#db.add(...) is synchronous
    await db.commit()
    #no need of db.refresh(workspace) because created_at,name,id come from the insert(flush/commit phase).
    #try,except block unnecessary as when a request fails get_db closes the session immediately and uncommitted work is rolled back automatically.
    return {"id":workspace.id,"name":workspace.name,"role":Role.OWNER,"created_at":workspace.created_at}
    

@router.get("",status_code=status.HTTP_200_OK,response_model=List[WorkSpaceResponse])
async def get_workspaces(db:DbSession,user:CurrentUser):
    query=select(WorkSpace,Membership.role).join(Membership,Membership.workspace_id==WorkSpace.id).where(Membership.user_id==user.id).order_by(WorkSpace.created_at.asc())
    #Join's tables and filters by user
    result=await db.execute(query)
    output=[]
    for workspace,role in result:
        output.append({
            "id":workspace.id,
            "name":workspace.name,
            "role":role,
            "created_at":workspace.created_at

        })
    return output
    


@router.get("/{workspace_id}",status_code=status.HTTP_200_OK,response_model=WorkSpaceResponse)
async def get_workspace(workspace_id:uuid.UUID,db:DbSession,user:CurrentUser,membership=AnyRole):
    query=select(WorkSpace,Membership.role).join(Membership,WorkSpace.id==Membership.workspace_id).where(Membership.user_id==user.id,Membership.workspace_id==workspace_id)
    result=await db.execute(query)
    row=result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"Workspace with id:{workspace_id}  not found.")
    workspace,role=row
    return {"role":role,"name":workspace.name,"id":workspace.id,"created_at":workspace.created_at}

@router.post("/{workspace_id}/members",status_code=status.HTTP_201_CREATED,response_model=MemberResponse)
async def add_user_to_workspace(body:MemberAdd,db:DbSession,membership:Owner):
    query=select(User).where(User.email==body.email.lower())
    target_user=(await db.execute(query)).scalar_one_or_none()
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="User not found")
    new_membership=Membership(user_id=target_user.id,role=body.role,workspace_id=membership.workspace_id)
    try:
        db.add(new_membership)
        await db.commit()
        await db.refresh(new_membership)
        return {
            "user_id":new_membership.user_id,
            "email":target_user.email,
            "role":body.role
        }
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,detail="user already in workspace")




    


