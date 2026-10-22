import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr,Field,ConfigDict
from app.models import Role,DocumentStatus
from typing import List
class RegisterRequest(BaseModel):
    email: EmailStr
    password:str=Field(min_length=8, max_length=128)

class UserResponse(BaseModel):
    
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str 

class RefreshRequest(BaseModel):
    refresh_token: str


class WorkSpaceCreate(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True)
    name:str=Field(min_length=1,max_length=100)

class WorkSpaceResponse(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True,from_attributes=True)
    id:uuid.UUID
    name:str=Field(min_length=1,max_length=100)
    created_at:datetime
    role:Role

class MemberAdd(BaseModel):
    email:EmailStr
    role:Role


class MemberResponse(BaseModel):
    model_config=ConfigDict(from_attributes=True)#will sending a response,you fetch data from your db(returns a database object or ORM model) and to extract data from that object we need to set from_attributes=True.
    user_id:uuid.UUID
    email:EmailStr
    role:Role


class DocumentResponse(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id: uuid.UUID
    workspace_id: uuid.UUID
    content_type: str
    size_bytes: int
    filename: str
    status: DocumentStatus
    error_message: str|None
    created_at: datetime

class ListRequest(BaseModel):
    limit:int=Field(20,ge=0,le=100)
    offset:int=Field(ge=0)

class ListResponse(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    items: List[DocumentResponse]
    total: int
    limit: int
    offset: int