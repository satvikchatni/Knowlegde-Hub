import asyncio
from app.models import User,RefreshToken
from app.exceptions import Conflict,UnAuthenticatedClient
from sqlalchemy.exc import IntegrityError
from app.security import hash_password
from app.schemas import RefreshRequest, RegisterRequest, TokenResponse, UserResponse
from app.db import DbSession
from sqlalchemy import select
from app.security import create_access_token, hash_password, hash_token, verify_password
from app.services.refresh_tokens import issue_refresh_token, revoke_family
from datetime import datetime,UTC

async def register_user(db:DbSession,body:RegisterRequest)->UserResponse:
        password_hash = await asyncio.to_thread(hash_password, body.password)
        user = User(email=body.email.lower(), password_hash=password_hash)
        try:
            db.add(user)
            await db.commit()
            await db.refresh(user)
        except IntegrityError:
            await db.rollback()
            raise Conflict(
                message="Email already registered"
            )
            # raise HTTPException(
            #     status_code=status.HTTP_409_CONFLICT,
            #     detail="Email already registered",
            # ) from None
        return user

DUMMY_HASH = hash_password("dummy_password")

# if user is None ,the hashing never runs. A login for an unknown email comes back much faster than one for a real email with a wrong password, and anyone can time that difference to find out which emails have accounts.
# hence we hash using dummy password
async def login_user(db:DbSession,form_data)->TokenResponse:
        query = select(User).where(User.email == form_data.username.lower())
        result = await db.execute(query)
        user = result.scalar()
        hashed_password = user.password_hash if user else DUMMY_HASH
        if not user or not await asyncio.to_thread(
            verify_password, form_data.password, hashed_password
        ):  raise UnAuthenticatedClient(message="Invalid email or password",headers={"WWW-Authenticate": "Bearer"})
            # raise HTTPException(
            #     status_code=status.HTTP_401_UNAUTHORIZED,
            #     detail="Invalid email or password",
            #     headers={"WWW-Authenticate": "Bearer"},
            # )
        access_token = create_access_token(user.id)
        refresh_token = issue_refresh_token(db, user.id)
        await db.commit()  # Commit the new refresh token to the database
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)


async def refresh_route(db:DbSession,body:RefreshRequest)->TokenResponse:
    # invalid = HTTPException(
    #     status_code=status.HTTP_401_UNAUTHORIZED,
    #     detail="Invalid refresh token",
    #     headers={"WWW-Authenticate": "Bearer"},
    # )
    invalid = UnAuthenticatedClient(message="Invalid refresh token",headers={"WWW-Authenticate": "Bearer"})
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

async def logout_user(db:DbSession,body:RefreshRequest)->None:
    stored = await db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(body.refresh_token))
        )
    if stored is not None:  # unknown token: do nothing and say nothing
        await revoke_family(db, stored.family_id)
        await db.commit()