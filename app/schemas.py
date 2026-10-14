import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr,Field,ConfigDict

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

    