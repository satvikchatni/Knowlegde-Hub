import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import DocumentStatus, Role


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


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
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)


class WorkSpaceResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, from_attributes=True)
    id: uuid.UUID
    name: str = Field(min_length=1, max_length=100)
    created_at: datetime
    role: Role


class MemberAdd(BaseModel):
    email: EmailStr
    role: Role


class MemberResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )  # will sending a response,you fetch data from your db(returns a database object or ORM model) and to extract data from that object we need to set from_attributes=True.
    user_id: uuid.UUID
    email: EmailStr
    role: Role


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workspace_id: uuid.UUID
    content_type: str
    size_bytes: int
    filename: str
    status: DocumentStatus
    error_message: str | None
    created_at: datetime


class ListRequest(BaseModel):
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)
    status: DocumentStatus | None = None


class ListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    items: list[DocumentResponse]
    total: int
    limit: int
    offset: int
    status: str | None = None


class SearchParams(BaseModel):
    q: str = Field(min_length=1, max_length=500)
    limit: int = Field(5, ge=1, le=20)


class SearchOut(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page_number: int
    position: int
    text: str
    score: float


# what gemini returns to app
class LLMResponse(BaseModel):
    generated_text: str
    input_token_usage: int
    output_token_usage: int


# the structured answer Gemini generates
class LLMAnswer(BaseModel):
    answer: str = Field(min_length=1)
    cited_ids: list[str]


class Ask(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=500)


class CitationSchema(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    page_number: int
    filename: str
    snippet: str


class AskOut(BaseModel):
    answer: str
    citations: list[CitationSchema]


#when a user is creating a conversation
class ConversationIn(BaseModel):
    title : str

class ConversationOut(BaseModel):
    id: uuid.UUID
    workspace_id : uuid.UUID
    user_id :uuid.UUID
    title: str
    created_at : datetime
    updated_at: datetime
    model_config=ConfigDict(from_attributes=True) #normally, pydantic expects a dict but from_attributes=True tells it to read values of object since SQLAlchemy gives ORM obj

class MessageOut(BaseModel):
    id:uuid.UUID
    conversation_id:uuid.UUID
    content:str
    status:str
    role:str
    citations:list[dict]|None=None
    input_tokens:int|None=None
    output_tokens:int|None=None
    created_at:datetime
    model_config=ConfigDict(from_attributes=True)

class QuestionIn(BaseModel):
    question:str=Field(min_length=1,max_length=500)
    model_config=ConfigDict(str_strip_whitespace=True)


#generated text
#TokenEvent sends each piece of text when it is generated
class TokenEvent(BaseModel):
    text:str

#CitationEvent sends the source details supporting its answer
class CitationEvent(BaseModel):
    chunk_id:uuid.UUID
    document_id:uuid.UUID
    page_number:int
    position:int
    snippet:str

#DoneEvent tells the frontend when the task is completed(task=generation of text) and provides token usage
#when llm is finished generating text, send done event
class DoneEvent(BaseModel):
    input_tokens:int
    output_tokens:int

#if something goes wrong during streaming we send an error event
class ErrorEvent(BaseModel):
    error:str

class LLMStreamResult(BaseModel):
    status:str
    input_tokens:int
    output_tokens:int

