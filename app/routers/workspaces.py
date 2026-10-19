from fastapi import APIRouter,status,HTTPException
from app.schemas import WorkSpaceCreate,WorkSpaceResponse,MemberAdd
from app.deps import DbSession,CurrentUser,Owner
from app.models import WorkSpace,Membership,User
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
import uuid
router=APIRouter(prefix="/workspaces",tags=["workspaces"])


@router.post("/",response_model=WorkSpaceResponse,status_code=status.HTTP_201_CREATED)
async def create_workspace(db:DbSession,body:WorkSpaceCreate,user:CurrentUser):
    try:
        workspace_name=body.name
        workspace=WorkSpace(name=workspace_name)
        db.add(workspace)
        await db.flush()#Flushes to generate workspace id
        membership=Membership(workspace_id=workspace.id,user_id=user.id,role="owner")
        db.add(membership)#db.add(...) is synchronous
        await db.commit()
        await db.refresh(workspace)#because that's what you return
        return {"id":workspace.id,"name":workspace.name,"role":"owner","created_at":workspace.created_at}
    except Exception as e:#catches every error that might happen during database operation
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,detail="failed to create workspace")


@router.get("/",status_code=status.HTTP_200_OK)
async def get_workspaces(db:DbSession,user:CurrentUser):
    query=select(WorkSpace,Membership.role).join(Membership,Membership.workspace_id==WorkSpace.id).where(Membership.user_id==user.id).order_by(WorkSpace.id.asc())
    #Join's tables and filters by user
    result=await db.execute(query)
    rows=result.tuples().all()
    output=[]
    for workspace,role in rows:
        output.append({
            "id":workspace.id,
            "name":workspace.name,
            "role":role

        })
    return output
    


@router.get("/{workspace_id}",status_code=status.HTTP_200_OK)
async def get_workspace(workspace_id:uuid.UUID,db:DbSession,user:CurrentUser,):
    query=select(WorkSpace,Membership.role).join(Membership,WorkSpace.id==Membership.workspace_id).where(Membership.user_id==user.id,Membership.workspace_id==workspace_id)
    result=await db.execute(query)
    row=result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"Workspace with id:{workspace_id}  not found.")
    workspace,role=row
    return {"role":role,"name":workspace.name,"id":workspace.id}

@router.post("/{workspace_id}/members",status_code=status.HTTP_201_CREATED)
async def add_user_to_workspace(body:MemberAdd,db:DbSession,user:CurrentUser,membership:Owner):
    query=select(User).where(User.email==body.email.lower())
    target_user=(await db.execute(query)).scalar_one_or_none()
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="User not found")
    new_membership=Membership(user_id=target_user.id,role=body.role,workspace_id=membership.workspace_id)
    try:
        db.add(new_membership)
        await db.commit()
        await db.refresh(new_membership)
        return new_membership
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,detail="user already in workspace")




    


