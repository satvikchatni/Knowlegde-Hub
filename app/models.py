import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, text,ForeignKey,UniqueConstraint,Enum
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from enum import StrEnum
class Role(StrEnum):
    OWNER="owner"
    EDITOR="editor"
    VIEWER="viewer"

ranking={
    Role.OWNER:3,
    Role.EDITOR:2,
    Role.VIEWER:1
}

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(unique=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    password_hash: Mapped[str] = mapped_column(nullable=False)

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    token_hash: Mapped[str] = mapped_column(unique=True)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )

class WorkSpace(Base):
    __tablename__="workspace"
    id: Mapped[uuid.UUID]= mapped_column(primary_key=True,default=uuid.uuid4)
    name: Mapped[str]= mapped_column()
    created_at: Mapped[datetime]= mapped_column(TIMESTAMP(timezone=True),server_default=text('now()'))#saves dates and times with their timezones included to prevent confusion


class Membership(Base):
    __tablename__="membership"
    id: Mapped[uuid.UUID]= mapped_column(primary_key=True,default=uuid.uuid4)
    user_id:Mapped[uuid.UUID]= mapped_column(ForeignKey("users.id",ondelete="CASCADE"))
    workspace_id:Mapped[uuid.UUID]=mapped_column(ForeignKey("workspace.id",ondelete="CASCADE"),index=True)#for fast lookups 
    role:Mapped[Role]=mapped_column(Enum(Role,native_enum=False,length=10),nullable=False)
    created_at:Mapped[datetime]= mapped_column(TIMESTAMP(timezone=True),server_default=text('now()'))
    __table_args__=(UniqueConstraint("user_id","workspace_id",name="users_workspace_uc"),)