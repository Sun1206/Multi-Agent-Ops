import json
import math
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, create_model, field_validator


# JSON仅作为业务数据，限制深度、体积和数值，不执行远端内容或解析外部引用。
def check_json(value, depth=0):
    if depth > 20:
        raise ValueError('JSON嵌套过深。')
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('JSON数值不合法。')
    if isinstance(value, dict):
        for child in value.values():
            check_json(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            check_json(child, depth + 1)


# 创建与完整编辑只接收业务字段；状态、计数、认领、抑制及审计不能由客户端伪造。
class AlertCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=256)
    source: str = Field(min_length=1, max_length=128)
    message: str = Field(max_length=32768)
    level: Literal['critical', 'warning', 'info'] = 'info'
    source_type: Literal['prometheus', 'zabbix', 'nightingale', 'aliyun', 'generic'] = 'generic'
    external_id: str = Field(default='', max_length=128)
    host: int | None = Field(default=None, gt=0)
    integration: int | None = Field(default=None, gt=0)
    service: str = Field(default='', max_length=128)
    environment: str = Field(default='', max_length=64)
    cluster: str = Field(default='', max_length=128)
    namespace: str = Field(default='', max_length=128)
    region: str = Field(default='', max_length=128)
    business_line: str = Field(default='', max_length=128)
    resource_type: str = Field(default='', max_length=64)
    resource: str = Field(default='', max_length=256)
    metric_name: str = Field(default='', max_length=128)
    runbook_url: str = Field(default='', max_length=500)
    labels: dict = Field(default_factory=dict)
    annotations: dict = Field(default_factory=dict)
    raw_payload: dict = Field(default_factory=dict)
    starts_at: datetime | None = None

    # PATCH继承同样校验；未提交默认None不执行校验，显式null仅允许关联及开始时间。
    @field_validator('*')
    @classmethod
    def validate_values(cls, value, info):
        if value is None and info.field_name not in ('host', 'integration', 'starts_at'):
            raise ValueError('字段不能为null。')
        if info.field_name in ('labels', 'annotations', 'raw_payload') and value is not None:
            check_json(value)
            if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode()) > 65536:
                raise ValueError('JSON超过允许大小。')
        if info.field_name in ('title', 'source') and isinstance(value, str) and not value.strip():
            raise ValueError('字段不能仅包含空白。')
        return value


# 动态复用创建字段的类型和长度，PATCH只写显式提交字段，不重置其余业务数据。
AlertPatch = create_model('AlertPatch', __base__=AlertCreate, **{
    name: (Annotated[field.annotation | None, *field.metadata] if field.metadata else field.annotation | None, Field(default=None, **{key: value for key, value in field.asdict()['attributes'].items() if key not in ('default', 'default_factory')}))
    for name, field in AlertCreate.model_fields.items()
})


# 人工动作只接收备注；账号从认证上下文取值，不接收客户端actor。
class AlertActionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    note: str = Field(default='', max_length=255)


# 屏蔽时长使用严格整数，默认一小时、最多七天，避免布尔/浮点及时间溢出。
class AlertMuteRequest(AlertActionRequest):
    minutes: StrictInt = Field(default=60, ge=1, le=10080)
