# SQLAlchemy domain models; maintain directly and evolve schema with new Alembic revisions.
from datetime import date, datetime, time, timezone
from decimal import Decimal
import uuid

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, LargeBinary, Numeric, String, Table, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from aidevops.database import Base
from aidevops.types import UTCDateTime


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid_string() -> str:
    return str(uuid.uuid4())


class AIOpsModelProvider(Base):

    __tablename__ = 'aiops_modelprovider'
    PROVIDER_OPENAI_COMPATIBLE = 'openai_compatible'
    CURRENCY_USD = 'USD'
    CURRENCY_CNY = 'CNY'
    STATUS_UNKNOWN = 'unknown'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=True, index=False, primary_key=False)
    provider_type: Mapped[str] = mapped_column('provider_type', String(32), nullable=False, unique=False, index=False, primary_key=False, default='openai_compatible')
    base_url: Mapped[str] = mapped_column('base_url', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    provider_preset: Mapped[str] = mapped_column('provider_preset', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    api_key_encrypted: Mapped[str] = mapped_column('api_key_encrypted', Text, nullable=False, unique=False, index=False, primary_key=False, default='')
    default_model: Mapped[str] = mapped_column('default_model', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    backup_model: Mapped[str] = mapped_column('backup_model', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    temperature: Mapped[float] = mapped_column('temperature', Float, nullable=False, unique=False, index=False, primary_key=False, default=0.2)
    max_tokens: Mapped[int] = mapped_column('max_tokens', Integer, nullable=False, unique=False, index=False, primary_key=False, default=10000)
    timeout_seconds: Mapped[int] = mapped_column('timeout_seconds', Integer, nullable=False, unique=False, index=False, primary_key=False, default=30)
    price_currency: Mapped[str] = mapped_column('price_currency', String(3), nullable=False, unique=False, index=False, primary_key=False, default='USD')
    input_token_price_per_1m: Mapped[Decimal] = mapped_column('input_token_price_per_1m', Numeric(10, 6), nullable=False, unique=False, index=False, primary_key=False, default=0)
    output_token_price_per_1m: Mapped[Decimal] = mapped_column('output_token_price_per_1m', Numeric(10, 6), nullable=False, unique=False, index=False, primary_key=False, default=0)
    is_enabled: Mapped[bool] = mapped_column('is_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    last_test_status: Mapped[str] = mapped_column('last_test_status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='unknown')
    last_test_message: Mapped[str] = mapped_column('last_test_message', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class AIOpsAgentConfig(Base):

    __tablename__ = 'aiops_agentconfig'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(64), nullable=False, unique=True, index=False, primary_key=False, default='default')
    default_provider_id: Mapped[int | None] = mapped_column('default_provider_id', Integer, ForeignKey('aiops_modelprovider.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    system_prompt: Mapped[str] = mapped_column('system_prompt', Text, nullable=False, unique=False, index=False, primary_key=False, default='')
    welcome_message: Mapped[str] = mapped_column('welcome_message', String(255), nullable=False, unique=False, index=False, primary_key=False, default='你好，我可以帮你结合平台上下文查询资源、根因分析、生成待执行任务等。')
    suggested_questions: Mapped[dict[str, object] | list[object]] = mapped_column('suggested_questions', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    is_enabled: Mapped[bool] = mapped_column('is_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    allow_action_execution: Mapped[bool] = mapped_column('allow_action_execution', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    require_confirmation: Mapped[bool] = mapped_column('require_confirmation', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    show_evidence: Mapped[bool] = mapped_column('show_evidence', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    allow_analysis: Mapped[bool] = mapped_column('allow_analysis', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    enabled_mcp_server_ids: Mapped[dict[str, object] | list[object]] = mapped_column('enabled_mcp_server_ids', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    enabled_skill_ids: Mapped[dict[str, object] | list[object]] = mapped_column('enabled_skill_ids', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    max_history_messages: Mapped[int] = mapped_column('max_history_messages', Integer, nullable=False, unique=False, index=False, primary_key=False, default=12)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class AIOpsMCPServer(Base):

    __tablename__ = 'aiops_mcpserver'
    SERVER_HTTP = 'http'
    SERVER_STDIO = 'stdio'
    SERVER_PLATFORM_BUILTIN = 'platform_builtin'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=True, index=False, primary_key=False)
    server_type: Mapped[str] = mapped_column('server_type', String(16), nullable=False, unique=False, index=False, primary_key=False, default='http')
    endpoint_or_command: Mapped[str] = mapped_column('endpoint_or_command', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    description: Mapped[str] = mapped_column('description', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    auth_config: Mapped[dict[str, object] | list[object]] = mapped_column('auth_config', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    tool_whitelist: Mapped[dict[str, object] | list[object]] = mapped_column('tool_whitelist', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    is_builtin: Mapped[bool] = mapped_column('is_builtin', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=False)
    is_enabled: Mapped[bool] = mapped_column('is_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class AIOpsSkill(Base):

    __tablename__ = 'aiops_skill'
    SOURCE_INLINE = 'inline'
    SOURCE_LOCAL = 'local'
    RISK_READ_ONLY = 'read_only'
    RISK_DRAFT = 'draft'
    RISK_WRITE = 'write'
    RISK_EXECUTE = 'execute'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=True, index=False, primary_key=False)
    slug: Mapped[str] = mapped_column('slug', String(128), nullable=False, unique=True, index=False, primary_key=False)
    description: Mapped[str] = mapped_column('description', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    category: Mapped[str] = mapped_column('category', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    applicable_actions: Mapped[dict[str, object] | list[object]] = mapped_column('applicable_actions', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    examples: Mapped[dict[str, object] | list[object]] = mapped_column('examples', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    builtin_tools: Mapped[dict[str, object] | list[object]] = mapped_column('builtin_tools', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    recommended_tools: Mapped[dict[str, object] | list[object]] = mapped_column('recommended_tools', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    max_iterations: Mapped[int] = mapped_column('max_iterations', Integer, nullable=False, unique=False, index=False, primary_key=False, default=0)
    risk_level: Mapped[str] = mapped_column('risk_level', String(16), nullable=False, unique=False, index=False, primary_key=False, default='read_only')
    output_contract: Mapped[dict[str, object] | list[object]] = mapped_column('output_contract', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    source_type: Mapped[str] = mapped_column('source_type', String(16), nullable=False, unique=False, index=False, primary_key=False, default='inline')
    content: Mapped[str] = mapped_column('content', Text, nullable=False, unique=False, index=False, primary_key=False, default='')
    allowed_role_codes: Mapped[dict[str, object] | list[object]] = mapped_column('allowed_role_codes', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    is_builtin: Mapped[bool] = mapped_column('is_builtin', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=False)
    is_enabled: Mapped[bool] = mapped_column('is_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class AIOpsKnowledgeEnvironment(Base):

    __tablename__ = 'aiops_knowledgeenvironment'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=True, index=False, primary_key=False)
    aliases: Mapped[dict[str, object] | list[object]] = mapped_column('aliases', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    description: Mapped[str] = mapped_column('description', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    event_environments: Mapped[dict[str, object] | list[object]] = mapped_column('event_environments', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    grafana_folder_keys: Mapped[dict[str, object] | list[object]] = mapped_column('grafana_folder_keys', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    metric_datasource_ids: Mapped[dict[str, object] | list[object]] = mapped_column('metric_datasource_ids', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    log_datasource_ids: Mapped[dict[str, object] | list[object]] = mapped_column('log_datasource_ids', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    tracing_datasource_ids: Mapped[dict[str, object] | list[object]] = mapped_column('tracing_datasource_ids', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    observability_link_ids: Mapped[dict[str, object] | list[object]] = mapped_column('observability_link_ids', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    alert_environments: Mapped[dict[str, object] | list[object]] = mapped_column('alert_environments', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    k8s_cluster_ids: Mapped[dict[str, object] | list[object]] = mapped_column('k8s_cluster_ids', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    k8s_namespaces: Mapped[dict[str, object] | list[object]] = mapped_column('k8s_namespaces', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    docker_host_ids: Mapped[dict[str, object] | list[object]] = mapped_column('docker_host_ids', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    task_resource_environment_ids: Mapped[dict[str, object] | list[object]] = mapped_column('task_resource_environment_ids', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    association_snapshot: Mapped[dict[str, object] | list[object]] = mapped_column('association_snapshot', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    child_node_snapshot: Mapped[dict[str, object] | list[object]] = mapped_column('child_node_snapshot', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    snapshot_generated_at: Mapped[datetime | None] = mapped_column('snapshot_generated_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    is_default: Mapped[bool] = mapped_column('is_default', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=False)
    is_enabled: Mapped[bool] = mapped_column('is_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    created_by: Mapped[str] = mapped_column('created_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    updated_by: Mapped[str] = mapped_column('updated_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class AIOpsChatSession(Base):

    __tablename__ = 'aiops_chatsession'
    STATUS_ACTIVE = 'active'
    STATUS_ARCHIVED = 'archived'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    context: Mapped[dict[str, object] | list[object]] = mapped_column('context', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    user_id: Mapped[int] = mapped_column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=False, index=False, primary_key=False)
    mirror_source_id: Mapped[int | None] = mapped_column('mirror_source_id', Integer, ForeignKey('aiops_chatsession.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    title: Mapped[str] = mapped_column('title', String(128), nullable=False, unique=False, index=False, primary_key=False, default='新会话')
    status: Mapped[str] = mapped_column('status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='active')
    last_message_at: Mapped[datetime] = mapped_column('last_message_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class AIOpsChatMessage(Base):

    __tablename__ = 'aiops_chatmessage'
    ROLE_SYSTEM = 'system'
    ROLE_USER = 'user'
    ROLE_ASSISTANT = 'assistant'
    TYPE_TEXT = 'text'
    TYPE_ANALYSIS = 'analysis'
    TYPE_ACTION = 'action'
    TYPE_ERROR = 'error'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    session_id: Mapped[int] = mapped_column('session_id', Integer, ForeignKey('aiops_chatsession.id', ondelete='CASCADE'), nullable=False, unique=False, index=False, primary_key=False)
    mirror_source_id: Mapped[int | None] = mapped_column('mirror_source_id', Integer, ForeignKey('aiops_chatmessage.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    role: Mapped[str] = mapped_column('role', String(16), nullable=False, unique=False, index=False, primary_key=False)
    message_type: Mapped[str] = mapped_column('message_type', String(16), nullable=False, unique=False, index=False, primary_key=False, default='text')
    content: Mapped[str] = mapped_column('content', Text, nullable=False, unique=False, index=False, primary_key=False)
    citations: Mapped[dict[str, object] | list[object]] = mapped_column('citations', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    tool_calls: Mapped[dict[str, object] | list[object]] = mapped_column('tool_calls', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    metadata_data: Mapped[dict[str, object] | list[object]] = mapped_column('metadata', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)


class AIOpsPendingAction(Base):

    __tablename__ = 'aiops_pendingaction'
    ACTION_EXECUTE_HOST_TASK = 'execute_host_task'
    RISK_LOW = 'low'
    RISK_MEDIUM = 'medium'
    RISK_HIGH = 'high'
    RISK_CRITICAL = 'critical'
    STATUS_PENDING = 'pending'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CANCELED = 'canceled'
    STATUS_EXECUTED = 'executed'
    STATUS_FAILED = 'failed'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    session_id: Mapped[int] = mapped_column('session_id', Integer, ForeignKey('aiops_chatsession.id', ondelete='CASCADE'), nullable=False, unique=False, index=False, primary_key=False)
    mirror_source_id: Mapped[int | None] = mapped_column('mirror_source_id', Integer, ForeignKey('aiops_pendingaction.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    message_id: Mapped[int | None] = mapped_column('message_id', Integer, ForeignKey('aiops_chatmessage.id', ondelete='CASCADE'), nullable=True, unique=False, index=False, primary_key=False)
    action_type: Mapped[str] = mapped_column('action_type', String(32), nullable=False, unique=False, index=False, primary_key=False)
    title: Mapped[str] = mapped_column('title', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    risk_level: Mapped[str] = mapped_column('risk_level', String(16), nullable=False, unique=False, index=False, primary_key=False, default='low')
    status: Mapped[str] = mapped_column('status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='pending')
    action_payload: Mapped[dict[str, object] | list[object]] = mapped_column('action_payload', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    result_payload: Mapped[dict[str, object] | list[object]] = mapped_column('result_payload', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    confirmed_by: Mapped[str] = mapped_column('confirmed_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    confirmed_at: Mapped[datetime | None] = mapped_column('confirmed_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class AIOpsToolInvocation(Base):

    __tablename__ = 'aiops_toolinvocation'
    STATUS_PENDING = 'pending'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    session_id: Mapped[int] = mapped_column('session_id', Integer, ForeignKey('aiops_chatsession.id', ondelete='CASCADE'), nullable=False, unique=False, index=False, primary_key=False)
    message_id: Mapped[int | None] = mapped_column('message_id', Integer, ForeignKey('aiops_chatmessage.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    tool_name: Mapped[str] = mapped_column('tool_name', String(64), nullable=False, unique=False, index=False, primary_key=False)
    status: Mapped[str] = mapped_column('status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='pending')
    latency_ms: Mapped[int] = mapped_column('latency_ms', Integer, nullable=False, unique=False, index=False, primary_key=False, default=0)
    request_payload: Mapped[dict[str, object] | list[object]] = mapped_column('request_payload', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    response_summary: Mapped[dict[str, object] | list[object]] = mapped_column('response_summary', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)


class AIOpsModelInvocation(Base):

    __tablename__ = 'aiops_modelinvocation'
    PURPOSE_CHAT_PLANNING = 'chat_planning'
    PURPOSE_ANSWER_FORMATTING = 'answer_formatting'
    PURPOSE_PARAMETER_EXTRACTION = 'parameter_extraction'
    PURPOSE_MODEL_PROBE = 'model_probe'
    PURPOSE_CONNECTION_TEST = 'connection_test'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    provider_id: Mapped[int | None] = mapped_column('provider_id', Integer, ForeignKey('aiops_modelprovider.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    session_id: Mapped[int | None] = mapped_column('session_id', Integer, ForeignKey('aiops_chatsession.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    message_id: Mapped[int | None] = mapped_column('message_id', Integer, ForeignKey('aiops_chatmessage.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    username: Mapped[str] = mapped_column('username', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    purpose: Mapped[str] = mapped_column('purpose', String(32), nullable=False, unique=False, index=False, primary_key=False, default='chat_planning')
    requested_model: Mapped[str] = mapped_column('requested_model', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    resolved_model: Mapped[str] = mapped_column('resolved_model', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    status: Mapped[str] = mapped_column('status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='success')
    latency_ms: Mapped[int] = mapped_column('latency_ms', Integer, nullable=False, unique=False, index=False, primary_key=False, default=0)
    prompt_tokens: Mapped[int] = mapped_column('prompt_tokens', Integer, nullable=False, unique=False, index=False, primary_key=False, default=0)
    completion_tokens: Mapped[int] = mapped_column('completion_tokens', Integer, nullable=False, unique=False, index=False, primary_key=False, default=0)
    total_tokens: Mapped[int] = mapped_column('total_tokens', Integer, nullable=False, unique=False, index=False, primary_key=False, default=0)
    estimated_cost_usd: Mapped[Decimal] = mapped_column('estimated_cost_usd', Numeric(12, 6), nullable=False, unique=False, index=False, primary_key=False, default=0)
    estimated_cost_currency: Mapped[str] = mapped_column('estimated_cost_currency', String(3), nullable=False, unique=False, index=False, primary_key=False, default='USD')
    request_summary: Mapped[dict[str, object] | list[object]] = mapped_column('request_summary', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    response_summary: Mapped[dict[str, object] | list[object]] = mapped_column('response_summary', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)


class AIOpsExternalTask(Base):

    __tablename__ = 'aiops_externaltask'
    STATUS_QUEUED = 'queued'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_CANCELED = 'canceled'
    STATUS_FAILED = 'failed'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    public_id: Mapped[str] = mapped_column('public_id', String(45), nullable=False, unique=True, index=False, primary_key=False, default=_uuid_string)
    source_agent: Mapped[str] = mapped_column('source_agent', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    title: Mapped[str] = mapped_column('title', String(128), nullable=False, unique=False, index=False, primary_key=False, default='AIOps 外部任务')
    action_code: Mapped[str] = mapped_column('action_code', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    agent_mode: Mapped[str] = mapped_column('agent_mode', String(32), nullable=False, unique=False, index=False, primary_key=False, default='')
    status: Mapped[str] = mapped_column('status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='queued')
    input_payload: Mapped[dict[str, object] | list[object]] = mapped_column('input_payload', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    plan_steps: Mapped[dict[str, object] | list[object]] = mapped_column('plan_steps', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    orchestration_state: Mapped[dict[str, object] | list[object]] = mapped_column('orchestration_state', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    agent_results: Mapped[dict[str, object] | list[object]] = mapped_column('agent_results', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    react_trace: Mapped[dict[str, object] | list[object]] = mapped_column('react_trace', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    result_payload: Mapped[dict[str, object] | list[object]] = mapped_column('result_payload', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    error_message: Mapped[str] = mapped_column('error_message', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_by_id: Mapped[int | None] = mapped_column('created_by_id', Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)
    completed_at: Mapped[datetime | None] = mapped_column('completed_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    canceled_at: Mapped[datetime | None] = mapped_column('canceled_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)


class AIOpsRunbook(Base):

    __tablename__ = 'aiops_runbook'
    STATUS_DRAFT = 'draft'
    STATUS_PUBLISHED = 'published'
    STATUS_ARCHIVED = 'archived'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    title: Mapped[str] = mapped_column('title', String(160), nullable=False, unique=False, index=False, primary_key=False)
    slug: Mapped[str] = mapped_column('slug', String(160), nullable=False, unique=True, index=False, primary_key=False)
    environment: Mapped[str] = mapped_column('environment', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    service: Mapped[str] = mapped_column('service', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    status: Mapped[str] = mapped_column('status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='draft')
    version: Mapped[int] = mapped_column('version', Integer, nullable=False, unique=False, index=False, primary_key=False, default=1)
    content: Mapped[str] = mapped_column('content', Text, nullable=False, unique=False, index=False, primary_key=False, default='')
    evidence: Mapped[dict[str, object] | list[object]] = mapped_column('evidence', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    tags: Mapped[dict[str, object] | list[object]] = mapped_column('tags', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    source_refs: Mapped[dict[str, object] | list[object]] = mapped_column('source_refs', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    source_task_id: Mapped[int | None] = mapped_column('source_task_id', Integer, ForeignKey('aiops_externaltask.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    source_session_id: Mapped[int | None] = mapped_column('source_session_id', Integer, ForeignKey('aiops_chatsession.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    created_by: Mapped[str] = mapped_column('created_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    updated_by: Mapped[str] = mapped_column('updated_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    published_at: Mapped[datetime | None] = mapped_column('published_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    archived_at: Mapped[datetime | None] = mapped_column('archived_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class AIOpsRunbookVersion(Base):

    __tablename__ = 'aiops_runbookversion'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    runbook_id: Mapped[int] = mapped_column('runbook_id', Integer, ForeignKey('aiops_runbook.id', ondelete='CASCADE'), nullable=False, unique=False, index=False, primary_key=False)
    version: Mapped[int] = mapped_column('version', Integer, nullable=False, unique=False, index=False, primary_key=False)
    status: Mapped[str] = mapped_column('status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='draft')
    title: Mapped[str] = mapped_column('title', String(160), nullable=False, unique=False, index=False, primary_key=False)
    content: Mapped[str] = mapped_column('content', Text, nullable=False, unique=False, index=False, primary_key=False, default='')
    evidence: Mapped[dict[str, object] | list[object]] = mapped_column('evidence', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    tags: Mapped[dict[str, object] | list[object]] = mapped_column('tags', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    source_refs: Mapped[dict[str, object] | list[object]] = mapped_column('source_refs', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    change_note: Mapped[str] = mapped_column('change_note', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_by: Mapped[str] = mapped_column('created_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)


class AIOpsReviewKnowledge(Base):

    __tablename__ = 'aiops_reviewknowledge'
    SOURCE_SESSION = 'session'
    SOURCE_TASK = 'task'
    SOURCE_RUNBOOK = 'runbook'
    SOURCE_MANUAL = 'manual'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    slug: Mapped[str] = mapped_column('slug', String(160), nullable=False, unique=True, index=False, primary_key=False)
    title: Mapped[str] = mapped_column('title', String(160), nullable=False, unique=False, index=False, primary_key=False)
    summary: Mapped[str] = mapped_column('summary', Text, nullable=False, unique=False, index=False, primary_key=False, default='')
    environment: Mapped[str] = mapped_column('environment', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    service: Mapped[str] = mapped_column('service', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    source_type: Mapped[str] = mapped_column('source_type', String(16), nullable=False, unique=False, index=False, primary_key=False, default='manual')
    evidence: Mapped[dict[str, object] | list[object]] = mapped_column('evidence', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    tags: Mapped[dict[str, object] | list[object]] = mapped_column('tags', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    source_refs: Mapped[dict[str, object] | list[object]] = mapped_column('source_refs', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    source_session_id: Mapped[int | None] = mapped_column('source_session_id', Integer, ForeignKey('aiops_chatsession.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    source_task_id: Mapped[int | None] = mapped_column('source_task_id', Integer, ForeignKey('aiops_externaltask.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    source_runbook_id: Mapped[int | None] = mapped_column('source_runbook_id', Integer, ForeignKey('aiops_runbook.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    created_by: Mapped[str] = mapped_column('created_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    updated_by: Mapped[str] = mapped_column('updated_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


__all__ = ['AIOpsModelProvider', 'AIOpsAgentConfig', 'AIOpsMCPServer', 'AIOpsSkill', 'AIOpsKnowledgeEnvironment', 'AIOpsChatSession', 'AIOpsChatMessage', 'AIOpsPendingAction', 'AIOpsToolInvocation', 'AIOpsModelInvocation', 'AIOpsExternalTask', 'AIOpsRunbook', 'AIOpsRunbookVersion', 'AIOpsReviewKnowledge']
