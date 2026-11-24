from datetime import date

from fastapi import APIRouter

from app.db import DbSession
from app.deps import CurrentUser
from app.schemas import Usage
from app.services.usage import get_usage

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("", response_model=list[Usage], status_code=200)
async def usage(db: DbSession, user: CurrentUser, since: date):
    return await get_usage(user_id=user.id, since=since, db=db)
