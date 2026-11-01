from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.db import DbSession
from app.deps import CurrentUser
from app.schemas import RefreshRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.auth import login_user, logout_user, refresh_route, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: DbSession):
    user = await register_user(db=db, body=body)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession):
    token_response = await login_user(form_data=form_data, db=db)
    return token_response


@router.get("/me", response_model=UserResponse)
async def get_current_user(current_user: CurrentUser):
    return current_user


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: DbSession):
    refresh_response = await refresh_route(body=body, db=db)
    return refresh_response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, db: DbSession) -> None:
    await logout_user(db=db, body=body)
