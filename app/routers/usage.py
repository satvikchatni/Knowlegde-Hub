from fastapi import APIRouter
from app.deps import CurrentUser
from datetime import date
from app.services.usage  import get_usage
from app.db import DbSession
from app.schemas import Usage

router=APIRouter(prefix="/usage",tags=["usage"])


@router.get("",response_model=list[Usage],status_code=200)
async def usage(db:DbSession,user:CurrentUser,since:date):
    return await get_usage(user_id=user.id,since=since,db=db)