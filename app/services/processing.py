import uuid
from sqlalchemy.ext.asyncio import AsyncSession,async_sessionmaker
from app.models import Document,Chunk
from sqlalchemy import select,delete
from app.services.extraction import file_extraction
from app.services.chunking import chunk_text
from app.config import settings
from app.exceptions import Conflict,UnsupportedType
import asyncio
import logging
logger=logging.getLogger(__name__) # __name__ identifies the module, makes logs easier to trace

async def process_document(document_id:uuid.UUID,session_factory:async_sessionmaker[AsyncSession]):#[] indicates what type of object the factory creates
   async with session_factory() as s:
        stmt=select(Document).where(Document.id==document_id)
        document=(await s.execute(stmt)).scalar_one_or_none()
        if document is None:
            return 
        document.status="reading"
        await s.commit()
        file_path=document.storage_path
        try:
            #for to_thread() we can pass the function call,just the function itself and the arguments of fn as params of to_thread.
            #so, no to_thread(fexample(arg1,arg2)), it sud be to_thread(fexample,arg1,arg2)
            file=await asyncio.to_thread(file_extraction,file_path=file_path)#as fn is synchronous, it's blocking code, it'll take time we assign it to a bg thread and await it
            position=0
            new_chunks=[]

            for page in file:
                page_number=page["page_number"]
                text=page["text"]
                chunks=await asyncio.to_thread(chunk_text,text=text,size=settings.chunk_size,overlap=settings.chunk_overlap)#the main thread can continue and won't be stuck doing a big task
                for c in chunks:
                    chunk=Chunk(document_id=document_id,workspace_id=document.workspace_id,text=c,position=position,page_number=page_number)
                    new_chunks.append(chunk)
                    position+=1
            #delete old chunks
            await s.execute(delete(Chunk).where(Chunk.document_id==document_id))
            s.add_all(new_chunks) #add entire list we use add_all
            document.status="done"
            document.error_message=None
            await s.commit()
        except (Conflict,UnsupportedType,ValueError) as e:
            await s.rollback()#after rollback, ORM objects are expired, so we have to retrieve them again
            stmt=select(Document).where(Document.id==document_id)
            document=(await s.execute(stmt)).scalar_one_or_none()
            if document is None:
                    return 
            document.status="error"
            document.error_message=str(e)
            await s.commit()
        except Exception:
            logger.exception("Ran into unexpected error")
            await s.rollback()#again, rollback expires the ORM objects retrieval is necessary
            stmt=select(Document).where(Document.id==document_id)
            document=(await s.execute(stmt)).scalar_one_or_none()
            if document is None:
                return 
            document.status="error"
            document.error_message="looking into it,fix will be on the way"
            await s.commit()
            
            


            

            

        

