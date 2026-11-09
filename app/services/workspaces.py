import uuid
from app.services.prompt import build_user_message,llm_response_parse,filter_citations
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated
from fastapi import Depends
import logging
from app.deps import get_embedder
from app.services.base_embedder import  BaseEmbedder
from app.exceptions import Conflict, NotFound, EmbeddingServiceUnavailable
from app.models import Membership, Role, User, WorkSpace, Chunk, Document
from app.schemas import (
    MemberAdd,
    MemberResponse,
    WorkSpaceCreate,
    WorkSpaceResponse,
    SearchParams,
    Ask,
    SearchOut
)
from app.services.base_llm import LLMClient
from app.services.prompt import system_prompt,llm_response_parse,filter_citations
from app.config import settings

logger=logging.getLogger("app")

async def make_workspace(db: AsyncSession, body: WorkSpaceCreate, user) -> WorkSpaceResponse:
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


async def retrieve_workspaces(db: AsyncSession, user) -> list[WorkSpaceResponse]:
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


async def retrieve_single_workspace(db: AsyncSession, user, workspace_id: uuid.UUID):
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


async def add_to_workspace(db: AsyncSession, body: MemberAdd, membership) -> MemberResponse:
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



#retrieval function,retrieves the most relevant chunks...
async def retrieve(db,filter_params,workspace_id:uuid.UUID,embedder):
    try:
        vectors = await embedder.embed_documents(texts=[filter_params.q], is_query=True)
        if len(vectors) != 1:
            raise EmbeddingServiceUnavailable(
                "Invalid embedding response"
            )  # check that only 1 vector was returned
        q = vectors[0]  # since we have embedded only one query
        dist = Chunk.embedding.cosine_distance(q).label(
            "distance"
        )  # maps the mathematical distance between the stored document and the query asked.
    except EmbeddingServiceUnavailable:
        raise  # if EmbeddingServiceUnavailable is raise this block catches it and re-raises it unchanged,w/o this the except Exception block would get triggered and would display a mssg not suitable to the error
    except Exception as e:  # any unexpected errors this runs
        raise EmbeddingServiceUnavailable(
            "Embedding service is currently down"
        ) from e  # from e: preserves the explicit exception as the cause of the error
        # from None :suppresses the original exception's display in the traceback
    stmt = (
        select(
            Chunk.text,
            dist,
            Document.filename,
            Chunk.document_id,
            Chunk.page_number,
            Chunk.id,
            Chunk.position,
        )
        .join(Document)
        .where(Chunk.workspace_id == workspace_id, Chunk.embedding.is_not(None))
        .order_by(dist)
        .limit(filter_params.limit)
    )  # join(Document) uses the foreign key relationship between the two tables, SQL understands that document.id sud equal chunk.document_id,so no need of adding that to the .where() clause.
    result = await db.execute(stmt)
    rows = result.all()  # .scalars() would drop the dist column,so don't use that in situations where you  require both(text,dist)
    if not rows:
        return []
    result = []
    for row in rows:
        item = SearchOut(
            chunk_id=row.id,
            document_id=row.document_id,
            filename=row.filename,
            page_number=row.page_number,
            position=row.position,
            text=row.text,
            score= 1.0
            - float(row.distance),  # score equals similarity more the similarity,the better
        )
            
    
        result.append(item)
    return result


async def ask(db,workspace_id:uuid.UUID,embedder,ask_params:Ask,llm:LLMClient):
    relevant_chunks=await retrieve(db=db,filter_params=SearchParams(q=ask_params.question,limit=settings.ask_top_chunks),workspace_id=workspace_id,embedder=embedder)
    if not relevant_chunks: #if no relevant chunks
        return {
            "answer":"I don't know the answer based on the provided documents",
            "citations":[]
        }
        
    message=build_user_message(question=ask_params.question,chunks=relevant_chunks)
    llm_ans=await llm.generate(system=system_prompt,message=message)
    validated_llm_ans=llm_response_parse(response=llm_ans.generated_text)
    valid_cited_ids=filter_citations(cited_ids=validated_llm_ans.cited_ids,chunks=relevant_chunks)
    if len(valid_cited_ids)==0: #if gemini provides no valid chunk ids
         return {
            "answer":"I don't know the answer based on the provided documents",
            "citations":[]
        }       
    citation_details=[]
    for chunk in relevant_chunks:
        if str(chunk.chunk_id) in valid_cited_ids:
            c={
                "chunk_id":chunk.chunk_id,
                "document_id":chunk.document_id,
                "filename":chunk.filename,
                "page_number":chunk.page_number,
                "snippet": chunk.text[:20]  #snippet of the chunk text till 20th character
            }
            citation_details.append(c)
    
    logger.info(f"LLM token usage,Input token usage= {llm_ans.input_token_usage}, Output token usage={llm_ans.output_token_usage}")
    return {
        "answer":validated_llm_ans.answer,
        "citations":citation_details
    }

