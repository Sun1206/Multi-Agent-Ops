# 校验告警配置管理请求，并兼容旧页面回传的只读展示字段。

import json
import math
from datetime import datetime
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, create_model, field_validator, model_validator

from app.services.events import is_sensitive_key


Name = Annotated[str, Field(min_length=1, max_length=128)]
ShortText = Annotated[str, Field(max_length=255)]
PositiveId = Annotated[StrictInt, Field(gt=0)]
Minutes = Annotated[StrictInt, Field(ge=1, le=10080)]
Scalar = str | int | float | bool


# 限制可持久化JSON的深度、总体大小和浮点取值，避免异常对象进入配置列。
def validate_json(value: Any, *, depth: int = 0) -> Any:
    if depth > 20:
        raise ValueError('JSON嵌套过深。')
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 128:
                raise ValueError('JSON对象键不合法。')
            validate_json(item, depth=depth + 1)
    elif isinstance(value, list):
        if len(value) > 500:
            raise ValueError('JSON数组项过多。')
        for item in value:
            validate_json(item, depth=depth + 1)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError('JSON不能包含非有限数字。')
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError('JSON值类型不合法。')
    if depth == 0 and len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()) > 65536:
        raise ValueError('JSON配置不能超过64KiB。')
    return value


# 统一忽略旧页面会回传的展示字段，其余未知字段继续由Pydantic拒绝。
class AlertConfigInput(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    roundtrip_fields: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode='before')
    @classmethod
    def strip_readonly(cls, value):
        readonly = {'id', 'created_at', 'updated_at'} | set(cls.roundtrip_fields)
        return {key: item for key, item in value.items() if key not in readonly} if isinstance(value, dict) else value

    @field_validator('name', check_fields=False, mode='before')
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


# 单条匹配条件只接受公开标签键、固定操作符和有界标量值。
class Matcher(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    key: Annotated[str, Field(min_length=1, max_length=128)]
    op: Literal['==', '!=', '=~', '!~', 'in', 'not in', 'contains'] = '=='
    value: Scalar | list[Scalar]

    @field_validator('key')
    @classmethod
    def safe_key(cls, value):
        value = value.strip()
        if not value or is_sensitive_key(value):
            raise ValueError('匹配键不合法。')
        return value

    @field_validator('value')
    @classmethod
    def safe_value(cls, value):
        values = value if isinstance(value, list) else [value]
        if len(values) > 100 or any(isinstance(item, str) and len(item) > 1200 for item in values):
            raise ValueError('匹配值不合法。')
        if any(isinstance(item, float) and not math.isfinite(item) for item in values):
            raise ValueError('匹配值不能包含非有限数字。')
        return value


# 告警来源配置由服务端生成接收令牌，客户端只维护业务属性。
class IntegrationCreate(AlertConfigInput):
    roundtrip_fields = frozenset({'provider_display', 'last_received_at', 'webhook_url', 'default_label_rows'})
    name: Name
    provider: Literal['prometheus', 'zabbix', 'nightingale', 'aliyun', 'generic']
    is_enabled: StrictBool = True
    default_labels: dict[str, Scalar] = Field(default_factory=dict, max_length=64)
    description: ShortText = ''

    @field_validator('default_labels')
    @classmethod
    def safe_labels(cls, value):
        if any(is_sensitive_key(key) or len(key) > 128 or isinstance(item, str) and len(item) > 255 for key, item in value.items()):
            raise ValueError('默认标签不合法。')
        return validate_json(value)


# 收件人允许关联平台账号，也允许单独保存外部联系方式。
class RecipientCreate(AlertConfigInput):
    roundtrip_fields = frozenset({'user_detail'})
    name: Annotated[str, Field(min_length=1, max_length=64)]
    user: PositiveId | None = None
    phone: Annotated[str, Field(max_length=32)] = ''
    email: Annotated[str, Field(max_length=255)] = ''
    dingtalk_user_id: Annotated[str, Field(max_length=128)] = ''
    feishu_user_id: Annotated[str, Field(max_length=128)] = ''
    wecom_user_id: Annotated[str, Field(max_length=128)] = ''
    is_enabled: StrictBool = True
    description: ShortText = ''

    @field_validator('email')
    @classmethod
    def valid_email(cls, value):
        if value and (value.count('@') != 1 or value.startswith('@') or value.endswith('@')):
            raise ValueError('邮箱格式不合法。')
        return value


# 收件人组用ID数组替换关联，显式空数组表示清空。
class RecipientGroupCreate(AlertConfigInput):
    roundtrip_fields = frozenset({'recipients', 'users'})
    name: Name
    description: ShortText = ''
    is_enabled: StrictBool = True
    recipient_ids: list[PositiveId] = Field(default_factory=list, max_length=500)
    user_ids: list[PositiveId] = Field(default_factory=list, max_length=500)


# 通知渠道保存模板与加密配置，不在配置管理阶段发送测试消息。
class ChannelCreate(AlertConfigInput):
    roundtrip_fields = frozenset({'channel_type_display', 'webhook_url', 'access_token', 'to'})
    name: Name
    channel_type: Literal['sms', 'voice', 'email', 'dingtalk', 'feishu', 'wecom']
    is_enabled: StrictBool = True
    send_resolved: StrictBool = True
    timeout_seconds: Annotated[StrictInt, Field(ge=1, le=60)] = 8
    config: dict[str, Any] = Field(default_factory=dict)
    template_title: ShortText = ''
    template_body: Annotated[str, Field(max_length=100000)] = ''

    @field_validator('config')
    @classmethod
    def safe_config(cls, value):
        return validate_json(value)


# 聚合规则控制分组维度、等待窗口和重复提醒间隔。
class AggregationCreate(AlertConfigInput):
    name: Name
    is_enabled: StrictBool = True
    matchers: list[Matcher] = Field(default_factory=list, max_length=32)
    group_by: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(default_factory=list, max_length=12)
    window_minutes: Minutes = 5
    repeat_interval_minutes: Minutes = 30
    description: ShortText = ''

    @field_validator('group_by', mode='before')
    @classmethod
    def safe_dimensions(cls, value):
        if not isinstance(value, list):
            raise ValueError('分组维度必须是数组。')
        value = [item.strip() if isinstance(item, str) else item for item in value]
        if any(not item or is_sensitive_key(item) for item in value):
            raise ValueError('分组维度不合法。')
        return list(dict.fromkeys(value))


# 抑制规则分别定义源匹配、目标匹配和必须相等的公开标签。
class InhibitionCreate(AlertConfigInput):
    name: Name
    is_enabled: StrictBool = True
    source_matchers: list[Matcher] = Field(default_factory=list, max_length=32)
    target_matchers: list[Matcher] = Field(default_factory=list, max_length=32)
    equal_labels: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(default_factory=list, max_length=12)
    duration_minutes: Minutes = 60
    description: ShortText = ''

    @field_validator('equal_labels', mode='before')
    @classmethod
    def safe_equal_labels(cls, value):
        if not isinstance(value, list):
            raise ValueError('相等标签必须是数组。')
        value = [item.strip() if isinstance(item, str) else item for item in value]
        if any(not item or is_sensitive_key(item) for item in value):
            raise ValueError('相等标签不合法。')
        return list(dict.fromkeys(value))


# 静默规则的时间边界在合并PATCH状态后由服务层统一校验。
class MuteCreate(AlertConfigInput):
    roundtrip_fields = frozenset({'range', 'created_by', 'description'})
    name: Name
    is_enabled: StrictBool = True
    matchers: list[Matcher] = Field(default_factory=list, max_length=32)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    reason: ShortText = ''

    @model_validator(mode='after')
    def valid_time_range(self):
        if (self.starts_at is None) != (self.ends_at is None):
            raise ValueError('开始和结束时间必须同时填写。')
        if self.starts_at is not None:
            starts_aware = self.starts_at.utcoffset() is not None
            ends_aware = self.ends_at.utcoffset() is not None
            if starts_aware != ends_aware or self.ends_at <= self.starts_at:
                raise ValueError('结束时间必须晚于开始时间且时区格式一致。')
        return self


# 升级层级定义相对等待分钟数和需要使用的通知渠道。
class EscalationLevel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: Annotated[str, Field(min_length=1, max_length=128)]
    after_minutes: Annotated[StrictInt, Field(ge=0, le=10080)]
    channel_ids: list[PositiveId] = Field(default_factory=list, max_length=500)

    @field_validator('name', mode='before')
    @classmethod
    def trim_level_name(cls, value):
        value = value.strip() if isinstance(value, str) else value
        if not value:
            raise ValueError('升级层级名称不能为空。')
        return value


# 升级策略至少包含一个层级，渠道存在性由服务层校验。
class EscalationCreate(AlertConfigInput):
    name: Name
    is_enabled: StrictBool = True
    matchers: list[Matcher] = Field(default_factory=list, max_length=32)
    levels: list[EscalationLevel] = Field(min_length=1, max_length=20)
    repeat_interval_minutes: Minutes = 30
    description: ShortText = ''


# 通知规则组合匹配器、策略引用和三类通知对象关联。
class NotificationRuleCreate(AlertConfigInput):
    roundtrip_fields = frozenset({'channels', 'recipients', 'recipient_groups', 'aggregation_rule_name', 'escalation_policy_name'})
    name: Name
    is_enabled: StrictBool = True
    matchers: list[Matcher] = Field(default_factory=list, max_length=32)
    min_level: Literal['', 'critical', 'warning', 'info'] = ''
    aggregation_rule: PositiveId | None = None
    escalation_policy: PositiveId | None = None
    channel_ids: list[PositiveId] = Field(default_factory=list, max_length=500)
    recipient_ids: list[PositiveId] = Field(default_factory=list, max_length=500)
    recipient_group_ids: list[PositiveId] = Field(default_factory=list, max_length=500)
    notify_on_fire: StrictBool = True
    notify_on_resolved: StrictBool = True
    notify_on_escalation: StrictBool = True
    description: ShortText = ''


# 从创建模型生成局部更新模型；最终状态仍用完整创建模型复验。
def partial_model(name: str, base: type[BaseModel]):
    fields = {}
    for field_name, info in base.model_fields.items():
        annotation = info.annotation
        if info.metadata:
            annotation = Annotated[annotation, *info.metadata]
        fields[field_name] = (annotation | None, None)
    partial_base = type(name + 'Input', (AlertConfigInput,), {'roundtrip_fields': base.roundtrip_fields})
    return create_model(name, __base__=partial_base, **fields)


IntegrationPatch = partial_model('IntegrationPatch', IntegrationCreate)
RecipientPatch = partial_model('RecipientPatch', RecipientCreate)
RecipientGroupPatch = partial_model('RecipientGroupPatch', RecipientGroupCreate)
ChannelPatch = partial_model('ChannelPatch', ChannelCreate)
AggregationPatch = partial_model('AggregationPatch', AggregationCreate)
InhibitionPatch = partial_model('InhibitionPatch', InhibitionCreate)
MutePatch = partial_model('MutePatch', MuteCreate)
EscalationPatch = partial_model('EscalationPatch', EscalationCreate)
NotificationRulePatch = partial_model('NotificationRulePatch', NotificationRuleCreate)


SCHEMAS = {
    'alert-integrations': (IntegrationCreate, IntegrationPatch),
    'alert-recipients': (RecipientCreate, RecipientPatch),
    'alert-recipient-groups': (RecipientGroupCreate, RecipientGroupPatch),
    'alert-notification-channels': (ChannelCreate, ChannelPatch),
    'alert-notification-rules': (NotificationRuleCreate, NotificationRulePatch),
    'alert-aggregation-rules': (AggregationCreate, AggregationPatch),
    'alert-inhibition-rules': (InhibitionCreate, InhibitionPatch),
    'alert-mute-rules': (MuteCreate, MutePatch),
    'alert-escalation-policies': (EscalationCreate, EscalationPatch),
}
