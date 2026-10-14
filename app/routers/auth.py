import asyncio
import datetime
from typing import Annotated
from fastapi import APIRouter, HTTPException, status,Depends
from sqlalchemy.exc import IntegrityError
from fastapi.security import OAuth2PasswordRequestForm
from app.db import DbSession
from app.deps import CurrentUser
from app.models import RefreshToken, User
from app.schemas import RefreshRequest, RegisterRequest, UserResponse, TokenResponse
from app.security import hash_password, create_access_token, verify_password
from sqlalchemy import select
from app.services.refresh_tokens import issue_refresh_token
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

DUMMY_HASH=hash_password("dummy_password")
#if user is None ,the hashing never runs. A login for an unknown email comes back much faster than one for a real email with a wrong password, and anyone can time that difference to find out which emails have accounts.
#hence we hash using dummy password
@router.post("/login", response_model=TokenResponse)
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession):
    query = select(User).where(User.email == form_data.username.lower())
    result = await db.execute(query)
    user = result.scalar()
    hashed_password = user.password_hash if user else DUMMY_HASH
    if not user or not await asyncio.to_thread(verify_password, form_data.password, hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(user.id)
    refresh_token=issue_refresh_token(db, user.id)
    await db.commit()  # Commit the new refresh token to the database
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)

@router.get("/me", response_model=UserResponse)
async def get_current_user(current_user: CurrentUser):
    return current_user

@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: DbSession):
    token_hash = hash_password(body.refresh_token)
    query = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    result = await db.execute(query)
    stored = result.scalar()
    if not stored or stored.revoked_at is not None or stored.expires_at <= datetime.now():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    stored.revoked_at = datetime.now()
    new_refresh_token = issue_refresh_token(db, stored.user_id, stored.family_id)
    return TokenResponse(
        access_token=create_access_token(stored.user_id),
        refresh_token=new_refresh_token
    )
    


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, db: DbSession) -> None:
    token_hash = hash_password(body.refresh_token)
    query = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    result = await db.execute(query)
    stored = result.scalar()
    if not stored or stored.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    stored.revoked_at = datetime.now()
    await db.commit()