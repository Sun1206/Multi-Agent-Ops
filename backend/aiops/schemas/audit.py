from datetime import datetime, timedelta, timezone
from typing import Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


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


# 明细默认查询全部历史；分页、文本长度及自定义时间沿用页面传参约定。
class AuditListFilters(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    q: str = Field(default='', max_length=256)
    username: str = Field(default='', max_length=64)
    status: str = Field(default='', max_length=32)
    risk_level: str = Field(default='', max_length=32)
    purpose: str = Field(default='', max_length=32)
    start: datetime | None = None
    end: datetime | None = None

    # 校验成对时间和最大跨度，统一以带时区的时间进行比较。
    @model_validator(mode='after')
    def validate_time(self):
        AuditRange(start=self.start, end=self.end)
        return self


# 批量清理每次只接受一种明确的目标列表，禁止空列表或无限批量请求。
class AuditDeleteInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    session_ids: list[StrictInt] | None = Field(default=None, min_length=1, max_length=100)
    invocation_ids: list[StrictInt] | None = Field(default=None, min_length=1, max_length=100)
    action_ids: list[StrictInt] | None = Field(default=None, min_length=1, max_length=100)
    trace_ids: list[str] | None = Field(default=None, min_length=1, max_length=100)

    # 数字主键必须为正数；具体列表名称和路径类型由服务层进一步匹配。
    @model_validator(mode='after')
    def validate_identifiers(self):
        fields = [value for value in (self.session_ids, self.invocation_ids, self.action_ids, self.trace_ids) if value is not None]
        if len(fields) != 1:
            raise ValueError('必须且只能提供一种目标列表。')
        if any(value <= 0 for values in (self.session_ids, self.invocation_ids, self.action_ids) if values for value in values):
            raise ValueError('记录编号必须为正整数。')
        if self.trace_ids and any(len(value) > 100 for value in self.trace_ids):
            raise ValueError('命中记录编号过长。')
        return self
