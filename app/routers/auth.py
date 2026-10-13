import asyncio
from typing import Annotated
from fastapi import APIRouter, HTTPException, status,Depends
from sqlalchemy.exc import IntegrityError
from fastapi.security import OAuth2PasswordRequestForm
from app.db import DbSession
from app.models import User
from app.schemas import RegisterRequest, UserResponse, TokenResponse
from app.security import hash_password, create_access_token, verify_password
from sqlalchemy import select
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


@router.post("/login", response_model=TokenResponse)
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession):
    query = select(User).where(User.email == form_data.username.lower())
    result = await db.execute(query)
    user = result.scalar()
    if not user or not await asyncio.to_thread(verify_password, form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(user.id)
    return TokenResponse(access_token=access_token)