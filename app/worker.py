import asyncio
import uuid

from arq import Retry
from arq.connections import RedisSettings
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import Document
from app.services.local_embedder import LocalEmbedder
from app.services.processing import process_document


async def startup(ctx):
    ctx["session_factory"] = SessionLocal
    # ctx['embedder']=LocalEmbedder(), have to initialize the instance here, not the class
    ctx["embedder"] = await asyncio.to_thread(
        LocalEmbedder
    )  # if CPU-heavy work  assign it to a thread


# permanent errors are handled in process_document function
async def process_doc_job(ctx, document_id: str):
    session_factory = ctx["session_factory"]
    embedder = ctx["embedder"]
    try:
        await process_document(
            document_id=uuid.UUID(document_id), session_factory=session_factory, embedder=embedder
        )
    except Exception as e:  # temporary error can be re-tried
        if ctx["job_try"] >= WorkerSettings.max_tries:
            async with session_factory() as db:
                document = (
                    await db.execute(select(Document).where(Document.id == uuid.UUID(document_id)))
                ).scalar_one_or_none()
                if document is not None:
                    document.status = "error"
                    document.error_message = "Reached max number of re-tries"
                    await db.commit()
        else:
            raise Retry(defer=ctx["job_try"] * 5) from e


class WorkerSettings:
    functions = [process_doc_job]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    on_startup = startup
    max_tries = 4
    keep_result = 0  # so, completed job IDs can be reused immediately, if same document needs to be retried later, ARQ can accept it
    job_timeout = 600  # maximum time a job that take to complete
