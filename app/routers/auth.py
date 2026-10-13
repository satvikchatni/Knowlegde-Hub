import asyncio

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.db import DbSession
from app.models import User
from app.schemas import RegisterRequest, UserResponse
from app.security import hash_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: DbSession):
    password_hash = await asyncio.to_thread(hash_password, body.password)
    user=User(email=body.email.lower(), password_hash=password_hash)
    try:
        db.add(user)
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    return user
    