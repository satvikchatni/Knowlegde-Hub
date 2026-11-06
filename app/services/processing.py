import asyncio
import logging
import uuid
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.exceptions import Conflict, UnsupportedType,PasswordProtected,InvalidFile
from app.models import Chunk, Document
from app.services.chunking import chunk_text
from app.services.extraction import file_extraction
from app.services.base_embedder import BaseEmbedder

logger = logging.getLogger(__name__)  # __name__ identifies the module, makes logs easier to trace


async def process_document(
    document_id: uuid.UUID, session_factory: async_sessionmaker[AsyncSession],embedder:BaseEmbedder
):  # [] indicates what type of object the factory creates
    async with session_factory() as s:
        stmt = select(Document).where(Document.id == document_id)
        document = (await s.execute(stmt)).scalar_one_or_none()
        if document is None:
            return
        document.status = "reading"
        await s.commit()
        file_path = document.storage_path  # relative path
        try:
            # for to_thread() we can pass the function call,just the function itself and the arguments of fn as params of to_thread.
            # so, no to_thread(fexample(arg1,arg2)), it sud be to_thread(fexample,arg1,arg2)
            file = await asyncio.to_thread(
                file_extraction, file_path=Path(settings.upload_dir) / file_path
            )  # as fn is synchronous, it's blocking code, it'll take time we assign it to a bg thread and await it
            position = 0
            new_chunks = []

            for page in file:
                page_number = page["page_number"]
                text = page["text"]
                chunks = await asyncio.to_thread(
                    chunk_text, text=text, size=settings.chunk_size, overlap=settings.chunk_overlap
                )  # the main thread can continue and won't be stuck doing a big task
                for c in chunks:
                    chunk = Chunk(
                        document_id=document_id,
                        workspace_id=document.workspace_id,
                        text=c,
                        position=position,
                        page_number=page_number,
                    )
                    new_chunks.append(chunk)
                    position += 1
            list_of_chunk_texts=[chunk.text for chunk in new_chunks]#extracts text from each chunk object
            batch_size=settings.embedding_batch_size#gets the configured batch size
            vectors=[]
            for start in range(0,len(list_of_chunk_texts),batch_size):#gets the starting index
                batch=list_of_chunk_texts[start:start+batch_size]#slicing extracts each batch
                vectors_of_batch=await embedder.embed_documents(texts=batch,is_query=False)
                if len(vectors_of_batch)!=len(batch):
                    raise ValueError("Batch size doesn't equal the vectors returned for that batch")
                #.append() list of batches, .extend() list of flat vectors
                vectors.extend(vectors_of_batch) #.extend(vectors_of_batch) appends each vector indivifually to the main list,.append(vectors_of_batch) would add an entire batch as an nested list
            if len(vectors)!=len(list_of_chunk_texts):
                raise ValueError("number of vectors returned doesn;t equal the number of chunks sent.")
            #zip() pairs two lists at the same position
            for chunk,vector in zip(new_chunks,vectors):#new_chunks ORM object,vectors it's corresponding embedding
                chunk.embedding=vector
            # delete old chunks
            await s.execute(delete(Chunk).where(Chunk.document_id == document_id))
            s.add_all(new_chunks)  # add entire list we use add_all
            document.status = "done"
            document.error_message = None
            await s.commit()
        except (InvalidFile,PasswordProtected, UnsupportedType) as e:#user-defined errors only,cause ValueError,etc would display techincal text too.
            await (
                s.rollback()
            )  # after rollback, ORM objects are expired, so we have to retrieve them again
            stmt = select(Document).where(Document.id == document_id)
            document = (await s.execute(stmt)).scalar_one_or_none()
            if document is None:
                return
            document.status = "error"
            document.error_message = str(e)
            await s.commit()
        except Exception:
            logger.exception(f"Ran into unexpected error with document:{document_id}")
            await s.rollback()  # again, rollback expires the ORM objects retrieval is necessary
            stmt = select(Document).where(Document.id == document_id)
            document = (await s.execute(stmt)).scalar_one_or_none()
            if document is None:
                return 
            document.status = "error"
            document.error_message = "looking into it,fix will be on the way"
            await s.commit()
