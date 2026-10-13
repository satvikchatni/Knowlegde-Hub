from fastapi import Depends, FastAPI
from sqlalchemy import  text
from app.db import get_db,engine
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()

app = FastAPI(lifespan=lifespan)


@app.get("/")
def read_root():
    return {"message": "Hello, World!"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/health/db")
async def health_check_db(db:Annotated[AsyncSession, Depends(get_db)]):
    await db.execute(text("SELECT 1"))
    return {"database":"ok"}

