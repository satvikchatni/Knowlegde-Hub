import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import Conflict, UnAuthenticatedClient
from app.models import RefreshToken, User
from app.schemas import RefreshRequest, RegisterRequest, TokenResponse, UserResponse
from app.security import create_access_token, hash_password, hash_token, verify_password
from app.services.refresh_tokens import issue_refresh_token, revoke_family


# main benefit of moving logic code into services is that you can test these functions directly instead of sending requests through a client(can test independently of HTTP)
# also reusability, cleaner routers are big advantages
#a service should take a plain AsyncSession
async def register_user(db: AsyncSession, body: RegisterRequest) -> UserResponse:
    password_hash = await asyncio.to_thread(hash_password, body.password)
    user = User(email=body.email.lower(), password_hash=password_hash)
    try:
        db.add(user)
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise Conflict(message="Email already registered") from None
        # raise HTTPException(
        #     status_code=status.HTTP_409_CONFLICT,
        #     detail="Email already registered",
        # ) from None
    return user


DUMMY_HASH = hash_password("dummy_password")


# if user is None ,the hashing never runs. A login for an unknown email comes back much faster than one for a real email with a wrong password, and anyone can time that difference to find out which emails have accounts.
# hence we hash using dummy password
async def login_user(db: AsyncSession, form_data) -> TokenResponse:
    query = select(User).where(User.email == form_data.username.lower())
    result = await db.execute(query)
    user = result.scalar()
    hashed_password = user.password_hash if user else DUMMY_HASH
    if not user or not await asyncio.to_thread(
        verify_password, form_data.password, hashed_password
    ):
        raise UnAuthenticatedClient(
            message="Invalid email or password", headers={"WWW-Authenticate": "Bearer"}
        )
        # raise HTTPException(
        #     status_code=status.HTTP_401_UNAUTHORIZED,
        #     detail="Invalid email or password",
        #     headers={"WWW-Authenticate": "Bearer"},
        # )
    access_token = create_access_token(user.id)
    refresh_token = issue_refresh_token(db, user.id)
    await db.commit()  # Commit the new refresh token to the database
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


async def refresh_route(db: AsyncSession, body: RefreshRequest) -> TokenResponse:
    # invalid = HTTPException(
    #     status_code=status.HTTP_401_UNAUTHORIZED,
    #     detail="Invalid refresh token",
    #     headers={"WWW-Authenticate": "Bearer"},
    # )
    invalid = UnAuthenticatedClient(
        message="Invalid refresh token", headers={"WWW-Authenticate": "Bearer"}
    )
    stored = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(body.refresh_token))
    )
    if stored is None:
        raise invalid
    if stored.revoked_at is not None:
        # already used: possibly stolen, so end every session from this login
        await revoke_family(db, stored.family_id)
        await db.commit()  # must happen before the raise, or the revoke is lost
        raise invalid
    if stored.expires_at <= datetime.now(UTC):
        raise invalid

    # rotation: the old token dies, a new one in the same family replaces it
    stored.revoked_at = datetime.now(UTC)
    new_refresh_token = issue_refresh_token(db, stored.user_id, stored.family_id)
    await db.commit()
    return TokenResponse(
        access_token=create_access_token(stored.user_id), refresh_token=new_refresh_token
    )


async def logout_user(db: AsyncSession, body: RefreshRequest) -> None:
    stored = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(body.refresh_token))
    )
    if stored is not None:  # unknown token: do nothing and say nothing
        await revoke_family(db, stored.family_id)
        await db.commit()
