from collections.abc import AsyncIterator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine,async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings
engine=create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal=async_sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session