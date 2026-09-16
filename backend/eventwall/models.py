from datetime import datetime

import hashlib
import secrets

from sqlalchemy import Boolean, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aidevops.database import Base
from aidevops.types import UTCDateTime
from rbac.models.authorization import utc_now


class EventRecord(Base):

    __tablename__ = "event_records"
    __table_args__ = (
        Index("ix_event_module_occurred", "module", "occurred_at"),
        Index("ix_event_resource_occurred", "resource_type", "resource_id", "occurred_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, index=True)
    module: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    result: Mapped[str] = mapped_column(String(16), default="success", index=True)
    severity: Mapped[str] = mapped_column(String(16), default="info")
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(String(255), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    actor_type: Mapped[str] = mapped_column(String(16), default="user")
    actor_username: Mapped[str] = mapped_column(String(64), default="", index=True)
    actor_display: Mapped[str] = mapped_column(String(128), default="")
    source_type: Mapped[str] = mapped_column(String(16), default="http")
    request_method: Mapped[str] = mapped_column(String(12), default="")
    source_path: Mapped[str] = mapped_column(String(255), default="")
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    correlation_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    parent_event_id: Mapped[int | None] = mapped_column(ForeignKey("event_records.id", ondelete="SET NULL"), nullable=True)
    resource_module: Mapped[str] = mapped_column(String(32), default="")
    resource_type: Mapped[str] = mapped_column(String(64), default="", index=True)
    resource_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    resource_name: Mapped[str] = mapped_column(String(255), default="", index=True)
    business_line: Mapped[str] = mapped_column(String(64), default="")
    environment: Mapped[str] = mapped_column(String(32), default="")
    tags: Mapped[list[object]] = mapped_column(JSON, default=list)
    related_resources: Mapped[list[object]] = mapped_column(JSON, default=list)
    changes: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    event_metadata: Mapped[dict[str, object]] = mapped_column("metadata", JSON, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    application: Mapped[str] = mapped_column(String(128), default="", index=True)
    parent_event: Mapped["EventRecord | None"] = relationship(remote_side="EventRecord.id", back_populates="children", lazy="raise")
    children: Mapped[list["EventRecord"]] = relationship(back_populates="parent_event", lazy="raise")


class EventSource(Base):

    __tablename__ = "event_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    source_kind: Mapped[str] = mapped_column(String(16))
    source_type: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(String(255), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="not_configured")
    endpoint_url: Mapped[str] = mapped_column(String(512), default="")
    auth_type: Mapped[str] = mapped_column(String(16), default="webhook")
    token_hash: Mapped[str] = mapped_column(String(64), default="")
    token_preview: Mapped[str] = mapped_column(String(24), default="")
    config: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    field_mapping: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    last_sync_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    last_error: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)

    def issue_token(self) -> str:
        token = secrets.token_urlsafe(32)
        self.token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        self.token_preview = f"{token[:8]}...{token[-4:]}"
        return token

    def verify_token(self, token: str) -> bool:
        if not self.token_hash or not token:
            return False
        candidate = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return secrets.compare_digest(self.token_hash, candidate)


class EventEnvironment(Base):

    __tablename__ = "event_environments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(String(255), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)

    def normalized_aliases(self) -> list[str]:
        values: list[str] = []
        seen = {self.code.strip().lower(), (self.name or self.code).strip().lower()}
        for item in self.aliases or []:
            value = str(item or "").strip()
            key = value.lower()
            if value and key not in seen:
                seen.add(key)
                values.append(value)
        return values


__all__ = ["EventEnvironment", "EventRecord", "EventSource"]
