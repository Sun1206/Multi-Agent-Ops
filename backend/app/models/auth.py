from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.types import UTCDateTime
from app.models.rbac import group_users, user_roles, utc_now


class User(Base):
    """保存平台本地账号以及管理员状态。"""

    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(254), default="")
    first_name: Mapped[str] = mapped_column(String(150), default="")
    last_name: Mapped[str] = mapped_column(String(150), default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    date_joined: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    last_login: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    roles: Mapped[list["Role"]] = relationship(secondary=user_roles, back_populates="users", lazy="raise")
    groups: Mapped[list["UserGroup"]] = relationship(secondary=group_users, back_populates="users", lazy="raise")
    tokens: Mapped[list["AuthToken"]] = relationship(back_populates="user", cascade="all, delete-orphan", lazy="raise")

    @property
    def display_name(self) -> str:
        """优先返回姓名，姓名为空时回退到用户名。"""
        return f"{self.first_name} {self.last_name}".strip() or self.username


class AuthToken(Base):
    """仅保存登录令牌摘要，原始令牌只返回给客户端一次。"""

    __tablename__ = "auth_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    user: Mapped[User] = relationship(back_populates="tokens", lazy="joined")
