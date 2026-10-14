import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import RefreshToken
from app.security import generate_refresh_token, hash_token


def issue_refresh_token(
    db: AsyncSession, user_id: uuid.UUID, family_id: uuid.UUID | None = None
) -> str:
    """Add a new token row to the session (the caller commits) and return the plain token."""
    token = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user_id,
            family_id=family_id or uuid.uuid4(),
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    return token


async def revoke_family(db: AsyncSession, family_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )