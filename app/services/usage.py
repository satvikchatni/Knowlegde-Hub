from app.db import DbSession
import uuid
from datetime import date
from app.models import Message,Conversation
from sqlalchemy import func,select,Date,cast #cast() converts a val/expression into a SQLAlchemy data type
from app.schemas import Usage

async def get_usage(db:DbSession,user_id:uuid.UUID, since:date):
    day=cast(func.timezone("UTC",Message.created_at),Date).label("day") 
    #counts llms token usage
    results=await db.execute(select(day,
    func.count().label("messages"),
    func.coalesce(func.sum(Message.input_tokens),0).label("input_tokens"),
    func.coalesce(func.sum(Message.output_tokens),0).label("output_tokens")
    ).join(Conversation,Message.conversation_id==Conversation.id).where(Message.created_at>=since,Conversation.user_id==user_id,Message.role=="assistant").group_by(day).order_by(day))

    return [Usage(**row._mapping) for row in results]

