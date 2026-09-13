# 定义操作审计筛选、白名单响应和清理参数。

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from app.core.types import ensure_utc


def require_iso_datetime(value: object) -> object:
    if value is None or isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError('时间必须为带时区的 ISO 8601 字符串。')
    try:
        datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError('时间必须为带时区的 ISO 8601 字符串。') from error
    return value


def validated_utc(value: datetime) -> datetime:
    try:
        return ensure_utc(value)
    except (OverflowError, ValueError) as error:
        raise ValueError('时间超出有效 UTC 日期范围。') from error


class AuditFilters(BaseModel):

    model_config = ConfigDict(extra='forbid', json_schema_extra={'description': '校验分页与筛选条件，拒绝含糊的无时区时间。'})
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1)
    search: str = ''
    module: str = ''
    actor: str = ''
    result: Literal['', 'success', 'failed', 'partial', 'pending', 'rejected'] = ''
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None

    @field_validator('search', 'module', 'actor', 'result', mode='before')
    @classmethod
    def trim_filter(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator('page_size')
    @classmethod
    def cap_page_size(cls, value: int) -> int:
        return min(value, 200)

    @field_validator('start_at', 'end_at')
    @classmethod
    def utc_filter_time(cls, value: datetime | None) -> datetime | None:
        return validated_utc(value) if value is not None else None

    @field_validator('start_at', 'end_at', mode='before')
    @classmethod
    def iso_filter_time(cls, value: object) -> object:
        return require_iso_datetime(value)

    @model_validator(mode='after')
    def ordered_window(self):
        if self.start_at is not None and self.end_at is not None and self.start_at > self.end_at:
            raise ValueError('开始时间不能晚于结束时间。')
        return self


class AuditResponse(BaseModel):

    model_config = ConfigDict(from_attributes=True, json_schema_extra={'description': '只返回操作审计页面所需字段，不暴露历史敏感载荷。'})
    id: int
    occurred_at: datetime
    title: str
    module: str
    action: str
    actor_username: str
    actor_display: str
    resource_type: str
    resource_id: str
    resource_name: str
    result: str
    source_type: str
    request_method: str
    source_path: str
    ip_address: str

    @field_validator('occurred_at')
    @classmethod
    def utc_response_time(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @computed_field(description='提供结果的中文显示名，未知历史值保留原文。')
    @property
    def result_display(self) -> str:
        return {'success': '成功', 'failed': '失败', 'partial': '部分成功', 'pending': '待处理', 'rejected': '已拒绝'}.get(self.result, self.result)

    @computed_field(description='提供事件来源显示名，兼容历史来源值。')
    @property
    def source_type_display(self) -> str:
        return {'http': 'HTTP', 'async': '异步任务', 'scheduler': '调度器', 'system': '系统', 'seed': '演示数据', 'websocket': 'WebSocket', 'external': 'External'}.get(self.source_type, self.source_type)


class AuditPage(BaseModel):
    model_config = {'json_schema_extra': {'description': "保持前端分页契约与筛选后的总记录数。"}}

    count: int
    next: str | None
    previous: str | None
    results: list[AuditResponse]


class PruneRequest(BaseModel):

    model_config = ConfigDict(extra='forbid', json_schema_extra={'description': '仅接收明确带时区的严格删除截止时间。'})
    before_at: AwareDatetime

    @field_validator('before_at', mode='before')
    @classmethod
    def iso_cutoff(cls, value: object) -> object:
        return require_iso_datetime(value)

    @field_validator('before_at')
    @classmethod
    def utc_cutoff(cls, value: datetime) -> datetime:
        return validated_utc(value)


class PruneResponse(BaseModel):
    model_config = {'json_schema_extra': {'description': "报告直接删除的审计记录条数与 UTC 截止时间。"}}

    deleted: int
    before_at: datetime
