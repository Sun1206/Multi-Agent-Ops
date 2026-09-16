# 校验配置写入，兼容页面回传的只读显示字段，拒绝未知字段。

from decimal import Decimal
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


Name = Annotated[str, Field(min_length=1, max_length=128)]
TextItem = Annotated[str, Field(min_length=1, max_length=255)]
Price = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=6, allow_inf_nan=False)]
PositiveId = Annotated[int, Field(gt=0)]


class ConfigInput(BaseModel):

    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, json_schema_extra={'description': '统一移除允许回传的显示字段，实际修改仅取显式可写字段。'})

    @model_validator(mode='before')
    @classmethod
    def strip_readonly(cls, value):
        readonly = {'id', 'created_at', 'updated_at', 'is_builtin', 'has_api_key', 'runtime_ready', 'setup_hint', 'last_test_status', 'last_test_message'}
        return {key: item for key, item in value.items() if key not in readonly} if isinstance(value, dict) else value

    @field_validator('name', 'slug', check_fields=False, mode='before')
    @classmethod
    def trimmed_identity(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('applicable_actions', 'examples', 'builtin_tools', 'recommended_tools', 'allowed_role_codes', 'tool_whitelist', 'suggested_questions', check_fields=False)
    @classmethod
    def distinct_text_items(cls, value):
        items = [item.strip() for item in value]
        if any(not item for item in items):
            raise ValueError('数组项不能只有空白。')
        return list(dict.fromkeys(items))


class ProviderPatch(ConfigInput):
    model_config = {'json_schema_extra': {'description': "接收提供商可写参数，不允许直接提交密文。"}}

    name: Name = ''
    provider_type: Literal['openai_compatible'] = 'openai_compatible'
    base_url: str = Field(default='', max_length=255)
    provider_preset: str = Field(default='', max_length=64)
    api_key: SecretStr = SecretStr('')
    default_model: str = Field(default='', max_length=128)
    backup_model: str = Field(default='', max_length=128)
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=10000, ge=100, le=16000)
    timeout_seconds: int = Field(default=30, ge=5, le=120)
    price_currency: Literal['USD', 'CNY'] = 'CNY'
    input_token_price_per_1m: Price = Decimal(0)
    output_token_price_per_1m: Price = Decimal(0)
    is_enabled: bool = True

    @field_validator('base_url')
    @classmethod
    def safe_url(cls, value: str) -> str:
        if not value:
            return value
        parts = urlsplit(value)
        if parts.scheme not in {'http', 'https'} or not parts.hostname or parts.username is not None or parts.password is not None:
            raise ValueError('地址必须是无内嵌凭据的 HTTP/HTTPS URL。')
        return value

    @field_validator('api_key')
    @classmethod
    def nonblank_secret(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if (raw and not raw.strip()) or len(raw) > 8192:
            raise ValueError('API Key 无效。')
        return value


class ProviderCreate(ProviderPatch):
    model_config = {'json_schema_extra': {'description': "创建时必须提供非空提供商名称。"}}
    name: Name


class McpPatch(ConfigInput):
    model_config = {'json_schema_extra': {'description': "保存 MCP 声明，不触发连接或 STDIO 执行。"}}
    name: Name = ''
    server_type: Literal['http', 'stdio', 'platform_builtin'] = 'http'
    endpoint_or_command: str = Field(default='', max_length=255)
    description: str = Field(default='', max_length=255)
    auth_config: dict = Field(default_factory=dict)
    tool_whitelist: list[TextItem] = Field(default_factory=list, max_length=500)
    is_enabled: bool = True


class McpCreate(McpPatch):
    model_config = {'json_schema_extra': {'description': "创建时提供名称，内置类型由服务端目录专用初始化。"}}
    name: Name


class SkillPatch(ConfigInput):
    model_config = {'json_schema_extra': {'description': "接收 Skill 方法与工具声明，不读取或执行 local 路径。"}}
    name: Name = ''
    slug: Name = ''
    description: str = Field(default='', max_length=255)
    category: str = Field(default='', max_length=64)
    source_type: Literal['inline', 'local'] = 'inline'
    content: str = Field(default='', max_length=100000)
    applicable_actions: list[TextItem] = Field(default_factory=list, max_length=500)
    examples: list[TextItem] = Field(default_factory=list, max_length=500)
    builtin_tools: list[TextItem] = Field(default_factory=list, max_length=500)
    recommended_tools: list[TextItem] = Field(default_factory=list, max_length=500)
    allowed_role_codes: list[TextItem] = Field(default_factory=list, max_length=500)
    max_iterations: int = Field(default=0, ge=0, le=20)
    risk_level: Literal['read_only', 'draft', 'write', 'execute'] = 'read_only'
    output_contract: dict = Field(default_factory=dict)
    is_enabled: bool = True


class SkillCreate(SkillPatch):
    model_config = {'json_schema_extra': {'description': "创建自定义 Skill 时必须给出名称与稳定标识。"}}
    name: Name
    slug: Name


class StrategyPatch(ConfigInput):
    model_config = {'json_schema_extra': {'description': "保持旧 PUT 的局部更新语义，显式空数组清空选中能力。"}}
    default_provider_id: PositiveId | None = None
    system_prompt: str = Field(default='', max_length=100000)
    welcome_message: str = Field(default="你好，我可以帮你结合平台上下文查询资源、根因分析、生成待执行任务等。", max_length=255)
    suggested_questions: list[TextItem] = Field(default_factory=list, max_length=100)
    is_enabled: bool = True
    allow_action_execution: bool = True
    require_confirmation: bool = True
    show_evidence: bool = True
    allow_analysis: bool = True
    enabled_mcp_server_ids: list[PositiveId] = Field(default_factory=list, max_length=500)
    enabled_skill_ids: list[PositiveId] = Field(default_factory=list, max_length=500)
    max_history_messages: int = Field(default=12, ge=1, le=100)


class CloneRequest(ConfigInput):
    model_config = {'json_schema_extra': {'description': "克隆 Skill 时可显式提供新名称或标识，否则生成唯一后缀。"}}
    name: Name = ''
    slug: Name = ''
