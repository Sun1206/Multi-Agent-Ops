from datetime import datetime, timedelta, timezone
from typing import Literal, NamedTuple

from pydantic import BaseModel, Field, model_validator


class ResolvedAuditRange(NamedTuple):
    start: datetime | None
    end: datetime | None


class AuditRange(BaseModel):
    days: int | None = Field(default=None, ge=1, le=365)
    start: datetime | None = None
    end: datetime | None = None
    range: Literal['all'] | None = None

    @model_validator(mode='after')
    def validate_range(self):
        if self.range and any(value is not None for value in (self.days, self.start, self.end)):
            raise ValueError('全部时间不能与其他时间参数同时使用。')
        if (self.start is None) != (self.end is None):
            raise ValueError('开始时间和结束时间必须同时提供。')
        if self.days is not None and self.start is not None:
            raise ValueError('最近天数不能与自定义时间同时使用。')
        if self.start is not None:
            if self.start.tzinfo is None or self.end.tzinfo is None:
                raise ValueError('时间必须包含时区。')
            if self.start >= self.end or self.end - self.start > timedelta(days=365):
                raise ValueError('时间范围无效或超过365天。')
        return self

    def resolve(self, now: datetime | None = None) -> ResolvedAuditRange:
        if self.range == 'all':
            return ResolvedAuditRange(None, None)
        end = self.end.astimezone(timezone.utc) if self.end else (now or datetime.now(timezone.utc))
        start = self.start.astimezone(timezone.utc) if self.start else end - timedelta(days=self.days or 7)
        return ResolvedAuditRange(start, end)
