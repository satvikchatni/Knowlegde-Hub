import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select

from app.db import DbSession
from app.models import Membership, Role, User, ranking
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: DbSession) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        user_id = decode_access_token(token)
    except jwt.InvalidTokenError, ValueError:
        raise credentials_error from None
    user = await db.get(User, user_id)
    if user is None:
        raise credentials_error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(minimum_role: Role):
    async def access_of_current_user(user: CurrentUser, workspace_id: uuid.UUID, db: DbSession):
        stmt = select(Membership).where(
            Membership.workspace_id == workspace_id, Membership.user_id == user.id
        )  # stmt stands for statement,the query here.
        membership = (await db.execute(stmt)).scalar_one_or_none()

        if membership is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
        if ranking[membership.role] < ranking[minimum_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to do this.",
            )

        return membership

    return access_of_current_user


AnyRole = Annotated[Membership, Depends(require_role(Role.VIEWER))]
EditorandAbove = Annotated[Membership, Depends(require_role(Role.EDITOR))]
Owner = Annotated[Membership, Depends(require_role(Role.OWNER))]
