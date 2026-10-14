from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.db import DbSession
from app.models import User
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: DbSession) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    decoded_token = decode_access_token(token)
    if not decoded_token:
        raise credentials_error
    user_id = decoded_token.get("sub")
    user = await db.get(User, user_id)
    if not user:
        raise credentials_error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]