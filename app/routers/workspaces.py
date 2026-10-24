from fastapi import APIRouter,status,HTTPException,UploadFile,Query
from app.schemas import WorkSpaceCreate,WorkSpaceResponse,MemberAdd,MemberResponse,DocumentResponse,ListResponse,ListRequest
from app.deps import DbSession,CurrentUser,Owner,AnyRole,EditorandAbove
from app.models import WorkSpace,Membership,User,Role,Document
from sqlalchemy import select,func,delete
from sqlalchemy.exc import IntegrityError
import uuid
from typing import List
from app.config import settings
from app.services.storage import StorageService
from typing import Annotated
from pathlib import Path

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

@router.post("/{workspace_id}/documents",status_code=status.HTTP_202_ACCEPTED,response_model=DocumentResponse)
async def upload_file(workspace_id:uuid.UUID,file:UploadFile,db:DbSession,membership:EditorandAbove):
    if file.size==0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,detail="file is empty")
    if file.size>(settings.max_upload_mb*1024*1024):#convert megabytes in settings to bytes
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE,detail="file too large")
    storage=StorageService(upload_dir=settings.upload_dir)
    
    try:
        file_type=storage.verify_file_type(file.file)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,detail="wrong type of file, or content doesn't match extension.")
    if file_type=="text/plain" and file.filename.endswith(".pdf"):#important verification
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,detail="wrong type of file, or content doesn't match extension.")
    if file_type=="application/pdf" and file.filename.endswith(".txt"):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,detail="wrong type of file, or content doesn't match extension.")
    if file.filename.endswith(".txt") is False and file.filename.endswith(".pdf") is False:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,detail="wrong type of file, or content doesn't match extension.")
    clean_name=storage.clean_display_name(file.filename)
    document_id=uuid.uuid4()
    relative_path=await storage.save_file(file=file,workspace_id=workspace_id,document_id=document_id)
    try:
        document=Document(id=document_id,workspace_id=workspace_id,filename=clean_name,content_type=file_type,size_bytes=file.size,status="uploaded",storage_path=relative_path)
        db.add(document)
        await db.commit()
        await db.refresh(document)
        return document
    except Exception as e:
        await db.rollback()
        await storage.delete_file(relative_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail="Failed to save record document to the database")


@router.get("/{workspace_id}/documents",response_model=ListResponse,status_code=status.HTTP_200_OK)
async def get_list_of_document(filter_query:Annotated[ListRequest,Query()],db:DbSession,membership:AnyRole,workspace_id:uuid.UUID):
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
    base_filter=[Document.workspace_id==workspace_id]
    if hasattr(filter_query,"status") and filter_query.status: #check if filter_query has the attribute status first then check if it has a value(other than None obv)
        base_filter.append(Document.status==filter_query.status)
    count=await db.scalar(select(func.count(Document.id)).where(*base_filter))
    query=select(Document).where(*base_filter).order_by(Document.created_at.desc()).limit(filter_query.limit).offset(filter_query.offset)
    result= await db.execute(query)
    document_list=result.scalars().all()
    return {
            "items":document_list,
            "total":count,
            "limit":filter_query.limit,
            "offset":filter_query.offset
        }

@router.get("/{workspace_id}/documents/{document_id}",response_model=DocumentResponse,status_code=status.HTTP_200_OK)
async def get_document(workspace_id:uuid.UUID,document_id:uuid.UUID,db:DbSession,membership:AnyRole):
    stmt=select(Document).where(Document.id==document_id,Document.workspace_id==workspace_id)
    result=await db.execute(stmt)
    document=result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"document with id:{document_id} doesn't exist in this workspace")
    return document

@router.delete("/{workspace_id}/documents/{document_id}",status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(db:DbSession,workspace_id:uuid.UUID,document_id:uuid.UUID,membership:EditorandAbove):
    stmt=select(Document).where(Document.id==document_id,Document.workspace_id==workspace_id)
    document=await db.scalar(stmt)

    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"document with id:{document_id} not found")
    relative_path=document.storage_path
    query=delete(Document).where(Document.id==document_id,Document.workspace_id==workspace_id)#we use delete(...) instead of select(...) for deletion operations.
    await db.execute(query)
    await db.commit()
    try:
        storage=StorageService(upload_dir=settings.upload_dir)
        await storage.delete_file(relative_path) #delete_file is a asynchronous
    except Exception:
        pass #treating missing file as 'fine'