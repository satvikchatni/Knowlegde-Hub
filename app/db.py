from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]

async def get_session_factory():
    return SessionLocal

#async_sessionmaker is a factory that creates async database sessions
#[AsyncSession] tells python what type of sessions the factory creates
#async_sessionmaker[AsyncSession]: a factory that creates objects of type AsyncSession
SessionFactory=Annotated[async_sessionmaker[AsyncSession],Depends(get_session_factory)]

