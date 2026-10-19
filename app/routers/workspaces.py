from fastapi import APIRouter,status,HTTPException
from app.schemas import WorkSpaceCreate,WorkSpaceResponse
from app.deps import DbSession,CurrentUser
from app.models import WorkSpace,Membership
from sqlalchemy import select
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
        return workspace
    except Exception as e:#catches every error that might happen during database operation
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,detail="failed to create workspace")


@router.get("/",status_code=status.HTTP_200_OK)
async def get_workspace(db:DbSession,user:CurrentUser):
    query=select(WorkSpace,Membership.role).join(Membership,Membership.workspace_id==WorkSpace.id).where(Membership.user_id==user.id).order_by(WorkSpace.id.asc())
    #Join's tables and filters by user
    result=await db.execute(query)
    rows=result.tuples().all()
    output=[]
    for workspace,role in rows:
        output.append({
            "id":workspace.id,
            "workspace-name":workspace.name,
            "role":role

        })
    return output
    


