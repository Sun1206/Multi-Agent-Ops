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


class Host(Base):

    __tablename__ = 'ops_host'
    ENV_CHOICES = [('prod', '生产'), ('test', '测试'), ('dev', '开发')]
    STATUS_CHOICES = [('online', '在线'), ('offline', '离线'), ('warning', '告警')]
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    hostname: Mapped[str] = mapped_column('hostname', String(128), nullable=False, unique=True, index=False, primary_key=False)
    ip_address: Mapped[str] = mapped_column('ip_address', String(45), nullable=False, unique=False, index=False, primary_key=False)
    business_line: Mapped[str] = mapped_column('business_line', String(50), nullable=False, unique=False, index=False, primary_key=False, default='')
    environment: Mapped[str] = mapped_column('environment', String(20), nullable=False, unique=False, index=False, primary_key=False, default='')
    admin_user: Mapped[str] = mapped_column('admin_user', String(50), nullable=False, unique=False, index=False, primary_key=False, default='')
    os_type: Mapped[str] = mapped_column('os_type', String(64), nullable=False, unique=False, index=False, primary_key=False, default='Linux')
    description: Mapped[str] = mapped_column('description', String(200), nullable=False, unique=False, index=False, primary_key=False, default='')
    status: Mapped[str] = mapped_column('status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='online')
    cpu_usage: Mapped[float] = mapped_column('cpu_usage', Float, nullable=False, unique=False, index=False, primary_key=False, default=0)
    memory_usage: Mapped[float] = mapped_column('memory_usage', Float, nullable=False, unique=False, index=False, primary_key=False, default=0)
    disk_usage: Mapped[float] = mapped_column('disk_usage', Float, nullable=False, unique=False, index=False, primary_key=False, default=0)
    ssh_port: Mapped[int] = mapped_column('ssh_port', Integer, nullable=False, unique=False, index=False, primary_key=False, default=22)
    ssh_user: Mapped[str] = mapped_column('ssh_user', String(64), nullable=False, unique=False, index=False, primary_key=False, default='root')
    ssh_password: Mapped[str] = mapped_column('ssh_password', String(256), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class TaskResourceGroup(Base):

    __tablename__ = 'ops_taskresourcegroup'
    GROUP_ENVIRONMENT = 'environment'
    GROUP_SYSTEM = 'system'
    __table_args__ = (
        Index('ix_ops_taskresourcegroup_group_type_parent_id_sort_order', 'group_type', 'parent_id', 'sort_order'),
    )
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(80), nullable=False, unique=False, index=False, primary_key=False)
    code: Mapped[str] = mapped_column('code', String(80), nullable=False, unique=False, index=False, primary_key=False, default='')
    group_type: Mapped[str] = mapped_column('group_type', String(20), nullable=False, unique=False, index=False, primary_key=False)
    parent_id: Mapped[int | None] = mapped_column('parent_id', Integer, ForeignKey('ops_taskresourcegroup.id', ondelete='CASCADE'), nullable=True, unique=False, index=False, primary_key=False)
    event_environment_id: Mapped[int | None] = mapped_column('event_environment_id', Integer, ForeignKey('event_environments.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    description: Mapped[str] = mapped_column('description', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    sort_order: Mapped[int] = mapped_column('sort_order', Integer, nullable=False, unique=False, index=False, primary_key=False, default=100)
    created_by: Mapped[str] = mapped_column('created_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='system')
    updated_by: Mapped[str] = mapped_column('updated_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class TaskResource(Base):

    __tablename__ = 'ops_taskresource'
    RESOURCE_HOST = 'host'
    RESOURCE_K8S = 'k8s'
    STATUS_ACTIVE = 'active'
    STATUS_INACTIVE = 'inactive'
    STATUS_WARNING = 'warning'
    __table_args__ = (
        Index('ix_ops_taskresource_resource_type_status', 'resource_type', 'status'),
        Index('ix_ops_taskresource_environment_id_system_id_resource_type', 'environment_id', 'system_id', 'resource_type'),
    )
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=False, index=False, primary_key=False)
    resource_type: Mapped[str] = mapped_column('resource_type', String(16), nullable=False, unique=False, index=False, primary_key=False, default='host')
    environment_id: Mapped[int] = mapped_column('environment_id', Integer, ForeignKey('ops_taskresourcegroup.id', ondelete='RESTRICT'), nullable=False, unique=False, index=False, primary_key=False)
    system_id: Mapped[int | None] = mapped_column('system_id', Integer, ForeignKey('ops_taskresourcegroup.id', ondelete='RESTRICT'), nullable=True, unique=False, index=False, primary_key=False)
    status: Mapped[str] = mapped_column('status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='active')
    ip_address: Mapped[str | None] = mapped_column('ip_address', String(45), nullable=True, unique=False, index=False, primary_key=False)
    ssh_port: Mapped[int] = mapped_column('ssh_port', Integer, nullable=False, unique=False, index=False, primary_key=False, default=22)
    ssh_user: Mapped[str] = mapped_column('ssh_user', String(64), nullable=False, unique=False, index=False, primary_key=False, default='root')
    ssh_password: Mapped[str] = mapped_column('ssh_password', String(256), nullable=False, unique=False, index=False, primary_key=False, default='')
    cluster_id: Mapped[int | None] = mapped_column('cluster_id', Integer, ForeignKey('ops_k8scluster.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    namespace: Mapped[str] = mapped_column('namespace', String(128), nullable=False, unique=False, index=False, primary_key=False, default='default')
    owner: Mapped[str] = mapped_column('owner', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    description: Mapped[str] = mapped_column('description', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    metadata_data: Mapped[dict[str, object] | list[object]] = mapped_column('metadata', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    created_by: Mapped[str] = mapped_column('created_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='system')
    updated_by: Mapped[str] = mapped_column('updated_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class HostTask(Base):

    __tablename__ = 'ops_hosttask'
    TARGET_HOST = 'host'
    TARGET_K8S = 'k8s'
    TASK_CHECK_CONNECTION = 'check_connection'
    TASK_REFRESH_METRICS = 'refresh_metrics'
    TASK_RUN_COMMAND = 'run_command'
    TASK_SERVICE_STATUS = 'service_status'
    TASK_RUN_PLAYBOOK = 'run_playbook'
    TASK_K8S_RESTART_POD = 'k8s_restart_pod'
    TASK_K8S_POD_EXEC = 'k8s_pod_exec'
    TASK_K8S_SCALE_WORKLOAD = 'k8s_scale_workload'
    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_SUCCESS = 'success'
    STATUS_PARTIAL = 'partial'
    STATUS_FAILED = 'failed'
    STATUS_CANCELED = 'canceled'
    LIFECYCLE_PENDING_CONFIRMATION = 'pending_confirmation'
    LIFECYCLE_PENDING_APPROVAL = 'pending_approval'
    LIFECYCLE_PENDING_EXECUTION = 'pending_execution'
    LIFECYCLE_RUNNING = 'running'
    LIFECYCLE_SUCCESS = 'success'
    LIFECYCLE_PARTIAL = 'partial'
    LIFECYCLE_FAILED = 'failed'
    LIFECYCLE_CANCELED = 'canceled'
    RISK_LOW = 'low'
    RISK_MEDIUM = 'medium'
    RISK_HIGH = 'high'
    RISK_CRITICAL = 'critical'
    STRATEGY_CONTINUE = 'continue'
    STRATEGY_STOP_ON_ERROR = 'stop_on_error'
    EXECUTION_MODE_SSH = 'ssh'
    EXECUTION_MODE_ANSIBLE = 'ansible'
    EXECUTION_MODE_K8S_API = 'k8s_api'
    TRIGGER_SOURCE_MANUAL = 'manual'
    TRIGGER_SOURCE_SCHEDULE = 'schedule'
    TRIGGER_SOURCE_AIOPS = 'aiops'
    TRIGGER_SOURCE_EVENT_CENTER = 'event_center'
    TRIGGER_SOURCE_API = 'api'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=False, index=False, primary_key=False)
    target_type: Mapped[str] = mapped_column('target_type', String(16), nullable=False, unique=False, index=False, primary_key=False, default='host')
    task_type: Mapped[str] = mapped_column('task_type', String(32), nullable=False, unique=False, index=False, primary_key=False)
    status: Mapped[str] = mapped_column('status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='pending')
    description: Mapped[str] = mapped_column('description', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    payload: Mapped[dict[str, object] | list[object]] = mapped_column('payload', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    selection_filters: Mapped[dict[str, object] | list[object]] = mapped_column('selection_filters', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    target_snapshot: Mapped[dict[str, object] | list[object]] = mapped_column('target_snapshot', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    execution_mode: Mapped[str] = mapped_column('execution_mode', String(16), nullable=False, unique=False, index=False, primary_key=False, default='ssh')
    execution_strategy: Mapped[str] = mapped_column('execution_strategy', String(20), nullable=False, unique=False, index=False, primary_key=False, default='continue')
    timeout_seconds: Mapped[int] = mapped_column('timeout_seconds', Integer, nullable=False, unique=False, index=False, primary_key=False, default=15)
    target_count: Mapped[int] = mapped_column('target_count', Integer, nullable=False, unique=False, index=False, primary_key=False, default=0)
    success_count: Mapped[int] = mapped_column('success_count', Integer, nullable=False, unique=False, index=False, primary_key=False, default=0)
    failed_count: Mapped[int] = mapped_column('failed_count', Integer, nullable=False, unique=False, index=False, primary_key=False, default=0)
    skipped_count: Mapped[int] = mapped_column('skipped_count', Integer, nullable=False, unique=False, index=False, primary_key=False, default=0)
    cancel_requested: Mapped[bool] = mapped_column('cancel_requested', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=False)
    cancel_requested_by: Mapped[str] = mapped_column('cancel_requested_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    cancel_requested_at: Mapped[datetime | None] = mapped_column('cancel_requested_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    schedule_id: Mapped[int | None] = mapped_column('schedule_id', Integer, ForeignKey('ops_hosttaskschedule.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    trigger_source: Mapped[str] = mapped_column('trigger_source', String(16), nullable=False, unique=False, index=False, primary_key=False, default='manual')
    lifecycle_status: Mapped[str] = mapped_column('lifecycle_status', String(32), nullable=False, unique=False, index=False, primary_key=False, default='pending_execution')
    risk_level: Mapped[str] = mapped_column('risk_level', String(16), nullable=False, unique=False, index=False, primary_key=False, default='low')
    correlation_id: Mapped[str] = mapped_column('correlation_id', String(128), nullable=False, unique=False, index=True, primary_key=False, default='')
    source_context: Mapped[dict[str, object] | list[object]] = mapped_column('source_context', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    created_by: Mapped[str] = mapped_column('created_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='system')
    summary: Mapped[str] = mapped_column('summary', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    started_at: Mapped[datetime | None] = mapped_column('started_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    finished_at: Mapped[datetime | None] = mapped_column('finished_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class HostTaskTemplate(Base):

    __tablename__ = 'ops_hosttasktemplate'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=False, index=False, primary_key=False)
    target_type: Mapped[str] = mapped_column('target_type', String(16), nullable=False, unique=False, index=False, primary_key=False, default='host')
    task_type: Mapped[str] = mapped_column('task_type', String(32), nullable=False, unique=False, index=False, primary_key=False)
    description: Mapped[str] = mapped_column('description', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    payload: Mapped[dict[str, object] | list[object]] = mapped_column('payload', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    execution_mode: Mapped[str] = mapped_column('execution_mode', String(16), nullable=False, unique=False, index=False, primary_key=False, default='ssh')
    execution_strategy: Mapped[str] = mapped_column('execution_strategy', String(20), nullable=False, unique=False, index=False, primary_key=False, default='continue')
    timeout_seconds: Mapped[int] = mapped_column('timeout_seconds', Integer, nullable=False, unique=False, index=False, primary_key=False, default=15)
    is_builtin: Mapped[bool] = mapped_column('is_builtin', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=False)
    created_by: Mapped[str] = mapped_column('created_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='system')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class HostTaskSchedule(Base):

    __tablename__ = 'ops_hosttaskschedule'
    SCHEDULE_TYPE_ONCE = 'once'
    SCHEDULE_TYPE_INTERVAL = 'interval'
    SCHEDULE_TYPE_CRON = 'cron'
    OVERLAP_SKIP = 'skip'
    OVERLAP_ALLOW = 'allow'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=False, index=False, primary_key=False)
    description: Mapped[str] = mapped_column('description', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    enabled: Mapped[bool] = mapped_column('enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    task_type: Mapped[str] = mapped_column('task_type', String(32), nullable=False, unique=False, index=False, primary_key=False)
    payload: Mapped[dict[str, object] | list[object]] = mapped_column('payload', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    selection_filters: Mapped[dict[str, object] | list[object]] = mapped_column('selection_filters', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    target_host_ids: Mapped[dict[str, object] | list[object]] = mapped_column('target_host_ids', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    target_snapshot: Mapped[dict[str, object] | list[object]] = mapped_column('target_snapshot', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    target_count: Mapped[int] = mapped_column('target_count', Integer, nullable=False, unique=False, index=False, primary_key=False, default=0)
    execution_mode: Mapped[str] = mapped_column('execution_mode', String(16), nullable=False, unique=False, index=False, primary_key=False, default='ssh')
    execution_strategy: Mapped[str] = mapped_column('execution_strategy', String(20), nullable=False, unique=False, index=False, primary_key=False, default='continue')
    timeout_seconds: Mapped[int] = mapped_column('timeout_seconds', Integer, nullable=False, unique=False, index=False, primary_key=False, default=15)
    schedule_type: Mapped[str] = mapped_column('schedule_type', String(16), nullable=False, unique=False, index=False, primary_key=False, default='cron')
    cron_expression: Mapped[str] = mapped_column('cron_expression', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    interval_seconds: Mapped[int | None] = mapped_column('interval_seconds', Integer, nullable=True, unique=False, index=False, primary_key=False)
    run_at: Mapped[datetime | None] = mapped_column('run_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    timezone: Mapped[str] = mapped_column('timezone', String(64), nullable=False, unique=False, index=False, primary_key=False, default='Asia/Shanghai')
    overlap_policy: Mapped[str] = mapped_column('overlap_policy', String(16), nullable=False, unique=False, index=False, primary_key=False, default='skip')
    next_run_at: Mapped[datetime | None] = mapped_column('next_run_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    last_run_at: Mapped[datetime | None] = mapped_column('last_run_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    last_status: Mapped[str] = mapped_column('last_status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='')
    consecutive_failures: Mapped[int] = mapped_column('consecutive_failures', Integer, nullable=False, unique=False, index=False, primary_key=False, default=0)
    total_run_count: Mapped[int] = mapped_column('total_run_count', Integer, nullable=False, unique=False, index=False, primary_key=False, default=0)
    last_error: Mapped[str] = mapped_column('last_error', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_by: Mapped[str] = mapped_column('created_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='system')
    updated_by: Mapped[str] = mapped_column('updated_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class HostTaskScheduleExecution(Base):

    __tablename__ = 'ops_hosttaskscheduleexecution'
    TRIGGER_SCHEDULER = 'scheduler'
    TRIGGER_MANUAL = 'manual'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    schedule_id: Mapped[int] = mapped_column('schedule_id', Integer, ForeignKey('ops_hosttaskschedule.id', ondelete='CASCADE'), nullable=False, unique=False, index=False, primary_key=False)
    host_task_id: Mapped[int | None] = mapped_column('host_task_id', Integer, ForeignKey('ops_hosttask.id', ondelete='SET NULL'), nullable=True, unique=True, index=False, primary_key=False)
    trigger_source: Mapped[str] = mapped_column('trigger_source', String(16), nullable=False, unique=False, index=False, primary_key=False, default='scheduler')
    status: Mapped[str] = mapped_column('status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='pending')
    summary: Mapped[str] = mapped_column('summary', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    target_count: Mapped[int] = mapped_column('target_count', Integer, nullable=False, unique=False, index=False, primary_key=False, default=0)
    success_count: Mapped[int] = mapped_column('success_count', Integer, nullable=False, unique=False, index=False, primary_key=False, default=0)
    failed_count: Mapped[int] = mapped_column('failed_count', Integer, nullable=False, unique=False, index=False, primary_key=False, default=0)
    skipped_count: Mapped[int] = mapped_column('skipped_count', Integer, nullable=False, unique=False, index=False, primary_key=False, default=0)
    error_message: Mapped[str] = mapped_column('error_message', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    requested_by: Mapped[str] = mapped_column('requested_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='system')
    requested_at: Mapped[datetime] = mapped_column('requested_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    started_at: Mapped[datetime | None] = mapped_column('started_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    finished_at: Mapped[datetime | None] = mapped_column('finished_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)


class HostTaskExecution(Base):

    __tablename__ = 'ops_hosttaskexecution'
    STATUS_RUNNING = 'running'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_SKIPPED = 'skipped'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    task_id: Mapped[int] = mapped_column('task_id', Integer, ForeignKey('ops_hosttask.id', ondelete='CASCADE'), nullable=False, unique=False, index=False, primary_key=False)
    target_type: Mapped[str] = mapped_column('target_type', String(16), nullable=False, unique=False, index=False, primary_key=False, default='host')
    host_id: Mapped[int | None] = mapped_column('host_id', Integer, ForeignKey('ops_host.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    host_name: Mapped[str] = mapped_column('host_name', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    host_ip: Mapped[str] = mapped_column('host_ip', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    target_id: Mapped[str] = mapped_column('target_id', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    target_name: Mapped[str] = mapped_column('target_name', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    target_namespace: Mapped[str] = mapped_column('target_namespace', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    target_kind: Mapped[str] = mapped_column('target_kind', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    status: Mapped[str] = mapped_column('status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='success')
    command: Mapped[str] = mapped_column('command', Text, nullable=False, unique=False, index=False, primary_key=False, default='')
    output: Mapped[str] = mapped_column('output', Text, nullable=False, unique=False, index=False, primary_key=False, default='')
    error_message: Mapped[str] = mapped_column('error_message', Text, nullable=False, unique=False, index=False, primary_key=False, default='')
    duration_ms: Mapped[int] = mapped_column('duration_ms', Integer, nullable=False, unique=False, index=False, primary_key=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column('started_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    finished_at: Mapped[datetime | None] = mapped_column('finished_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)


class Deployment(Base):

    __tablename__ = 'ops_deployment'
    DEPLOY_MODE_CHOICES = [('docker_compose', 'Docker 环境'), ('k8s', 'K8s 集群')]
    STATUS_CHOICES = [('pending', '待执行'), ('rejected', '已驳回'), ('deploying', '发布中'), ('running', '运行中'), ('stopped', '已停止'), ('failed', '发布失败'), ('removed', '已下线')]
    APPROVAL_STATUS_CHOICES = [('pending', '待审批'), ('approved', '已通过'), ('rejected', '已拒绝')]
    ACTION_TYPE_CHOICES = [('deploy', '应用发布'), ('rollback', '版本回滚'), ('rerun', '重新执行')]
    RELEASE_STRATEGY_CHOICES = [('standard', '标准发布'), ('canary', '灰度发布'), ('batch', '批次发布')]
    ENV_CHOICES = [('prod', '生产'), ('test', '测试'), ('dev', '开发')]
    __table_args__ = (
        Index('ix_ops_deployment_approval_status_status', 'approval_status', 'status'),
        Index('ix_ops_deployment_business_line_app_name_environment_deployed_a', 'business_line', 'app_name', 'environment', 'deployed_at'),
        Index('ix_ops_deployment_is_current_deploy_mode', 'is_current', 'deploy_mode'),
    )
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    app_name: Mapped[str] = mapped_column('app_name', String(128), nullable=False, unique=False, index=False, primary_key=False)
    business_line: Mapped[str] = mapped_column('business_line', String(50), nullable=False, unique=False, index=False, primary_key=False, default='')
    version: Mapped[str] = mapped_column('version', String(64), nullable=False, unique=False, index=False, primary_key=False)
    image: Mapped[str] = mapped_column('image', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    environment: Mapped[str] = mapped_column('environment', String(32), nullable=False, unique=False, index=False, primary_key=False, default='test')
    deploy_mode: Mapped[str] = mapped_column('deploy_mode', String(32), nullable=False, unique=False, index=False, primary_key=False, default='docker_compose')
    status: Mapped[str] = mapped_column('status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='pending')
    approval_status: Mapped[str] = mapped_column('approval_status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='pending')
    action_type: Mapped[str] = mapped_column('action_type', String(16), nullable=False, unique=False, index=False, primary_key=False, default='deploy')
    release_strategy: Mapped[str] = mapped_column('release_strategy', String(16), nullable=False, unique=False, index=False, primary_key=False, default='standard')
    submitter: Mapped[str] = mapped_column('submitter', String(64), nullable=False, unique=False, index=False, primary_key=False, default='admin')
    deployer: Mapped[str] = mapped_column('deployer', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    approver: Mapped[str] = mapped_column('approver', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    approval_comment: Mapped[str] = mapped_column('approval_comment', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    change_summary: Mapped[str] = mapped_column('change_summary', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    description: Mapped[str] = mapped_column('description', Text, nullable=False, unique=False, index=False, primary_key=False, default='')
    env_config: Mapped[dict[str, object] | list[object]] = mapped_column('env_config', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    deploy_log: Mapped[str] = mapped_column('deploy_log', Text, nullable=False, unique=False, index=False, primary_key=False, default='')
    deploy_dir: Mapped[str] = mapped_column('deploy_dir', String(256), nullable=False, unique=False, index=False, primary_key=False, default='')
    release_name: Mapped[str] = mapped_column('release_name', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    namespace: Mapped[str] = mapped_column('namespace', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    replicas: Mapped[int] = mapped_column('replicas', Integer, nullable=False, unique=False, index=False, primary_key=False, default=1)
    container_port: Mapped[int | None] = mapped_column('container_port', Integer, nullable=True, unique=False, index=False, primary_key=False)
    service_port: Mapped[int | None] = mapped_column('service_port', Integer, nullable=True, unique=False, index=False, primary_key=False)
    canary_percent: Mapped[int] = mapped_column('canary_percent', Integer, nullable=False, unique=False, index=False, primary_key=False, default=10)
    batch_total: Mapped[int] = mapped_column('batch_total', Integer, nullable=False, unique=False, index=False, primary_key=False, default=1)
    batch_current: Mapped[int] = mapped_column('batch_current', Integer, nullable=False, unique=False, index=False, primary_key=False, default=0)
    batch_size: Mapped[int] = mapped_column('batch_size', Integer, nullable=False, unique=False, index=False, primary_key=False, default=1)
    strategy_config: Mapped[dict[str, object] | list[object]] = mapped_column('strategy_config', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    host_id: Mapped[int | None] = mapped_column('host_id', Integer, ForeignKey('ops_host.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    docker_host_id: Mapped[int | None] = mapped_column('docker_host_id', Integer, ForeignKey('ops_dockerhost.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    cluster_id: Mapped[int | None] = mapped_column('cluster_id', Integer, ForeignKey('ops_k8scluster.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    approval_flow_id: Mapped[int | None] = mapped_column('approval_flow_id', Integer, ForeignKey('ops_deploymentapprovalflow.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    previous_success_id: Mapped[int | None] = mapped_column('previous_success_id', Integer, ForeignKey('ops_deployment.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    rollback_source_id: Mapped[int | None] = mapped_column('rollback_source_id', Integer, ForeignKey('ops_deployment.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    rerun_source_id: Mapped[int | None] = mapped_column('rerun_source_id', Integer, ForeignKey('ops_deployment.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    approved_at: Mapped[datetime | None] = mapped_column('approved_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    executed_at: Mapped[datetime | None] = mapped_column('executed_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    finished_at: Mapped[datetime | None] = mapped_column('finished_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    execution_count: Mapped[int] = mapped_column('execution_count', Integer, nullable=False, unique=False, index=False, primary_key=False, default=0)
    is_current: Mapped[bool] = mapped_column('is_current', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=False)
    deployed_at: Mapped[datetime] = mapped_column('deployed_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)


class DeploymentApprovalFlow(Base):

    __tablename__ = 'ops_deploymentapprovalflow'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=False, index=False, primary_key=False)
    environment: Mapped[str] = mapped_column('environment', String(32), nullable=False, unique=False, index=False, primary_key=False, default='')
    description: Mapped[str] = mapped_column('description', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    is_active: Mapped[bool] = mapped_column('is_active', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    created_by: Mapped[str] = mapped_column('created_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class DeploymentApprovalNode(Base):

    __tablename__ = 'ops_deploymentapprovalnode'
    APPROVER_TYPE_CHOICES = [('user', '指定用户'), ('role', '指定角色'), ('group', '指定用户组')]
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    flow_id: Mapped[int] = mapped_column('flow_id', Integer, ForeignKey('ops_deploymentapprovalflow.id', ondelete='CASCADE'), nullable=False, unique=False, index=False, primary_key=False)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=False, index=False, primary_key=False)
    order: Mapped[int] = mapped_column('order', Integer, nullable=False, unique=False, index=False, primary_key=False, default=1)
    approver_type: Mapped[str] = mapped_column('approver_type', String(16), nullable=False, unique=False, index=False, primary_key=False, default='user')
    approver_value: Mapped[str] = mapped_column('approver_value', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    description: Mapped[str] = mapped_column('description', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')


class DeploymentApprovalStep(Base):

    __tablename__ = 'ops_deploymentapprovalstep'
    STEP_STATUS_CHOICES = [('pending', '待审批'), ('approved', '已通过'), ('rejected', '已拒绝')]
    __table_args__ = (
        Index('ix_ops_deploymentapprovalstep_deployment_id_status_is_current', 'deployment_id', 'status', 'is_current'),
    )
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    deployment_id: Mapped[int] = mapped_column('deployment_id', Integer, ForeignKey('ops_deployment.id', ondelete='CASCADE'), nullable=False, unique=False, index=False, primary_key=False)
    flow_id: Mapped[int | None] = mapped_column('flow_id', Integer, ForeignKey('ops_deploymentapprovalflow.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    node_name: Mapped[str] = mapped_column('node_name', String(128), nullable=False, unique=False, index=False, primary_key=False)
    node_order: Mapped[int] = mapped_column('node_order', Integer, nullable=False, unique=False, index=False, primary_key=False, default=1)
    approver_type: Mapped[str] = mapped_column('approver_type', String(16), nullable=False, unique=False, index=False, primary_key=False, default='user')
    approver_value: Mapped[str] = mapped_column('approver_value', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    status: Mapped[str] = mapped_column('status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='pending')
    is_current: Mapped[bool] = mapped_column('is_current', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=False)
    approver: Mapped[str] = mapped_column('approver', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    comment: Mapped[str] = mapped_column('comment', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    acted_at: Mapped[datetime | None] = mapped_column('acted_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)


class Alert(Base):

    __tablename__ = 'ops_alert'
    SOURCE_PROMETHEUS = 'prometheus'
    SOURCE_ZABBIX = 'zabbix'
    SOURCE_NIGHTINGALE = 'nightingale'
    SOURCE_ALIYUN = 'aliyun'
    SOURCE_GENERIC = 'generic'
    STATUS_ACTIVE = 'active'
    STATUS_RESOLVED = 'resolved'
    STATUS_CLOSED = 'closed'
    STATUS_MUTED = 'muted'
    LEVEL_CHOICES = [('critical', '严重'), ('warning', '警告'), ('info', '信息')]
    __table_args__ = (
        Index('ix_ops_alert_status_level', 'status', 'level'),
        Index('ix_ops_alert_source_type_source', 'source_type', 'source'),
        Index('ix_ops_alert_service_environment', 'service', 'environment'),
        Index('ix_ops_alert_cluster_namespace', 'cluster', 'namespace'),
        Index('ix_ops_alert_resource_type_resource', 'resource_type', 'resource'),
        Index('ix_ops_alert_is_acknowledged_created_at', 'is_acknowledged', 'created_at'),
    )
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    integration_id: Mapped[int | None] = mapped_column('integration_id', Integer, ForeignKey('ops_alertintegration.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    title: Mapped[str] = mapped_column('title', String(256), nullable=False, unique=False, index=False, primary_key=False)
    level: Mapped[str] = mapped_column('level', String(16), nullable=False, unique=False, index=False, primary_key=False, default='info')
    status: Mapped[str] = mapped_column('status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='active')
    source: Mapped[str] = mapped_column('source', String(128), nullable=False, unique=False, index=False, primary_key=False)
    source_type: Mapped[str] = mapped_column('source_type', String(32), nullable=False, unique=False, index=False, primary_key=False, default='generic')
    external_id: Mapped[str] = mapped_column('external_id', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    fingerprint: Mapped[str] = mapped_column('fingerprint', String(128), nullable=False, unique=False, index=True, primary_key=False, default='')
    group_key: Mapped[str] = mapped_column('group_key', String(256), nullable=False, unique=False, index=True, primary_key=False, default='')
    message: Mapped[str] = mapped_column('message', Text, nullable=False, unique=False, index=False, primary_key=False)
    is_acknowledged: Mapped[bool] = mapped_column('is_acknowledged', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=False)
    acknowledged_by: Mapped[str] = mapped_column('acknowledged_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    acknowledged_at: Mapped[datetime | None] = mapped_column('acknowledged_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    claimed_by: Mapped[str] = mapped_column('claimed_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    claimed_at: Mapped[datetime | None] = mapped_column('claimed_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    host_id: Mapped[int | None] = mapped_column('host_id', Integer, ForeignKey('ops_host.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    service: Mapped[str] = mapped_column('service', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    environment: Mapped[str] = mapped_column('environment', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    cluster: Mapped[str] = mapped_column('cluster', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    namespace: Mapped[str] = mapped_column('namespace', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    region: Mapped[str] = mapped_column('region', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    business_line: Mapped[str] = mapped_column('business_line', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    resource_type: Mapped[str] = mapped_column('resource_type', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    resource: Mapped[str] = mapped_column('resource', String(256), nullable=False, unique=False, index=False, primary_key=False, default='')
    metric_name: Mapped[str] = mapped_column('metric_name', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    runbook_url: Mapped[str] = mapped_column('runbook_url', String(500), nullable=False, unique=False, index=False, primary_key=False, default='')
    labels: Mapped[dict[str, object] | list[object]] = mapped_column('labels', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    annotations: Mapped[dict[str, object] | list[object]] = mapped_column('annotations', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    raw_payload: Mapped[dict[str, object] | list[object]] = mapped_column('raw_payload', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    starts_at: Mapped[datetime | None] = mapped_column('starts_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    ends_at: Mapped[datetime | None] = mapped_column('ends_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    last_received_at: Mapped[datetime] = mapped_column('last_received_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    occurrence_count: Mapped[int] = mapped_column('occurrence_count', Integer, nullable=False, unique=False, index=False, primary_key=False, default=1)
    is_suppressed: Mapped[bool] = mapped_column('is_suppressed', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=False)
    suppressed_by: Mapped[str] = mapped_column('suppressed_by', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    suppressed_until: Mapped[datetime | None] = mapped_column('suppressed_until', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    mute_until: Mapped[datetime | None] = mapped_column('mute_until', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    muted_by: Mapped[str] = mapped_column('muted_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    muted_reason: Mapped[str] = mapped_column('muted_reason', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    escalation_level: Mapped[int] = mapped_column('escalation_level', Integer, nullable=False, unique=False, index=False, primary_key=False, default=0)
    escalated_at: Mapped[datetime | None] = mapped_column('escalated_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    closed_at: Mapped[datetime | None] = mapped_column('closed_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class AlertClaim(Base):

    __tablename__ = 'ops_alertclaim'
    __table_args__ = (
        Index('ix_ops_alertclaim_alert_id_claimant', 'alert_id', 'claimant'),
    )
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    alert_id: Mapped[int] = mapped_column('alert_id', Integer, ForeignKey('ops_alert.id', ondelete='CASCADE'), nullable=False, unique=False, index=False, primary_key=False)
    claimant: Mapped[str] = mapped_column('claimant', String(64), nullable=False, unique=False, index=False, primary_key=False)
    claimed_at: Mapped[datetime] = mapped_column('claimed_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)


class AlertIntegration(Base):

    __tablename__ = 'ops_alertintegration'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=False, index=False, primary_key=False)
    provider: Mapped[str] = mapped_column('provider', String(32), nullable=False, unique=False, index=False, primary_key=False)
    token: Mapped[str] = mapped_column('token', String(64), nullable=False, unique=True, index=False, primary_key=False)
    secret: Mapped[str] = mapped_column('secret', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    is_enabled: Mapped[bool] = mapped_column('is_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    default_labels: Mapped[dict[str, object] | list[object]] = mapped_column('default_labels', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    description: Mapped[str] = mapped_column('description', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    last_received_at: Mapped[datetime | None] = mapped_column('last_received_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class AlertRecipient(Base):

    __tablename__ = 'ops_alertrecipient'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(64), nullable=False, unique=False, index=False, primary_key=False)
    user_id: Mapped[int | None] = mapped_column('user_id', Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    phone: Mapped[str] = mapped_column('phone', String(32), nullable=False, unique=False, index=False, primary_key=False, default='')
    email: Mapped[str] = mapped_column('email', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    dingtalk_user_id: Mapped[str] = mapped_column('dingtalk_user_id', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    feishu_user_id: Mapped[str] = mapped_column('feishu_user_id', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    wecom_user_id: Mapped[str] = mapped_column('wecom_user_id', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    is_enabled: Mapped[bool] = mapped_column('is_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    description: Mapped[str] = mapped_column('description', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class AlertRecipientGroup(Base):

    __tablename__ = 'ops_alertrecipientgroup'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=True, index=False, primary_key=False)
    description: Mapped[str] = mapped_column('description', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    is_enabled: Mapped[bool] = mapped_column('is_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class AlertNotificationChannel(Base):

    __tablename__ = 'ops_alertnotificationchannel'
    CHANNEL_SMS = 'sms'
    CHANNEL_VOICE = 'voice'
    CHANNEL_EMAIL = 'email'
    CHANNEL_DINGTALK = 'dingtalk'
    CHANNEL_FEISHU = 'feishu'
    CHANNEL_WECOM = 'wecom'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=False, index=False, primary_key=False)
    channel_type: Mapped[str] = mapped_column('channel_type', String(32), nullable=False, unique=False, index=False, primary_key=False)
    is_enabled: Mapped[bool] = mapped_column('is_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    send_resolved: Mapped[bool] = mapped_column('send_resolved', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    timeout_seconds: Mapped[int] = mapped_column('timeout_seconds', Integer, nullable=False, unique=False, index=False, primary_key=False, default=8)
    config: Mapped[dict[str, object] | list[object]] = mapped_column('config', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    template_title: Mapped[str] = mapped_column('template_title', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    template_body: Mapped[str] = mapped_column('template_body', Text, nullable=False, unique=False, index=False, primary_key=False, default='')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class AlertAggregationRule(Base):

    __tablename__ = 'ops_alertaggregationrule'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=False, index=False, primary_key=False)
    is_enabled: Mapped[bool] = mapped_column('is_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    matchers: Mapped[dict[str, object] | list[object]] = mapped_column('matchers', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    group_by: Mapped[dict[str, object] | list[object]] = mapped_column('group_by', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    window_minutes: Mapped[int] = mapped_column('window_minutes', Integer, nullable=False, unique=False, index=False, primary_key=False, default=5)
    repeat_interval_minutes: Mapped[int] = mapped_column('repeat_interval_minutes', Integer, nullable=False, unique=False, index=False, primary_key=False, default=30)
    description: Mapped[str] = mapped_column('description', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class AlertInhibitionRule(Base):

    __tablename__ = 'ops_alertinhibitionrule'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=False, index=False, primary_key=False)
    is_enabled: Mapped[bool] = mapped_column('is_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    source_matchers: Mapped[dict[str, object] | list[object]] = mapped_column('source_matchers', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    target_matchers: Mapped[dict[str, object] | list[object]] = mapped_column('target_matchers', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    equal_labels: Mapped[dict[str, object] | list[object]] = mapped_column('equal_labels', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    duration_minutes: Mapped[int] = mapped_column('duration_minutes', Integer, nullable=False, unique=False, index=False, primary_key=False, default=60)
    description: Mapped[str] = mapped_column('description', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class AlertMuteRule(Base):

    __tablename__ = 'ops_alertmuterule'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=False, index=False, primary_key=False)
    is_enabled: Mapped[bool] = mapped_column('is_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    matchers: Mapped[dict[str, object] | list[object]] = mapped_column('matchers', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    starts_at: Mapped[datetime | None] = mapped_column('starts_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    ends_at: Mapped[datetime | None] = mapped_column('ends_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    reason: Mapped[str] = mapped_column('reason', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_by: Mapped[str] = mapped_column('created_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class AlertEscalationPolicy(Base):

    __tablename__ = 'ops_alertescalationpolicy'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=False, index=False, primary_key=False)
    is_enabled: Mapped[bool] = mapped_column('is_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    matchers: Mapped[dict[str, object] | list[object]] = mapped_column('matchers', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    levels: Mapped[dict[str, object] | list[object]] = mapped_column('levels', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    repeat_interval_minutes: Mapped[int] = mapped_column('repeat_interval_minutes', Integer, nullable=False, unique=False, index=False, primary_key=False, default=30)
    description: Mapped[str] = mapped_column('description', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class AlertNotificationRule(Base):

    __tablename__ = 'ops_alertnotificationrule'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=False, index=False, primary_key=False)
    is_enabled: Mapped[bool] = mapped_column('is_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    matchers: Mapped[dict[str, object] | list[object]] = mapped_column('matchers', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    min_level: Mapped[str] = mapped_column('min_level', String(16), nullable=False, unique=False, index=False, primary_key=False, default='')
    aggregation_rule_id: Mapped[int | None] = mapped_column('aggregation_rule_id', Integer, ForeignKey('ops_alertaggregationrule.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    escalation_policy_id: Mapped[int | None] = mapped_column('escalation_policy_id', Integer, ForeignKey('ops_alertescalationpolicy.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    notify_on_fire: Mapped[bool] = mapped_column('notify_on_fire', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    notify_on_resolved: Mapped[bool] = mapped_column('notify_on_resolved', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    notify_on_escalation: Mapped[bool] = mapped_column('notify_on_escalation', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    description: Mapped[str] = mapped_column('description', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class AlertNotificationLog(Base):

    __tablename__ = 'ops_alertnotificationlog'
    STATUS_SUCCESS = 'success'
    STATUS_SKIPPED = 'skipped'
    STATUS_ERROR = 'error'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    alert_id: Mapped[int] = mapped_column('alert_id', Integer, ForeignKey('ops_alert.id', ondelete='CASCADE'), nullable=False, unique=False, index=False, primary_key=False)
    rule_id: Mapped[int | None] = mapped_column('rule_id', Integer, ForeignKey('ops_alertnotificationrule.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    channel_id: Mapped[int | None] = mapped_column('channel_id', Integer, ForeignKey('ops_alertnotificationchannel.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    action: Mapped[str] = mapped_column('action', String(32), nullable=False, unique=False, index=False, primary_key=False, default='fire')
    status: Mapped[str] = mapped_column('status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='success')
    recipient_summary: Mapped[str] = mapped_column('recipient_summary', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    request_payload: Mapped[dict[str, object] | list[object]] = mapped_column('request_payload', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    response_body: Mapped[str] = mapped_column('response_body', Text, nullable=False, unique=False, index=False, primary_key=False, default='')
    error_message: Mapped[str] = mapped_column('error_message', Text, nullable=False, unique=False, index=False, primary_key=False, default='')
    sent_at: Mapped[datetime | None] = mapped_column('sent_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)


class AlertAction(Base):

    __tablename__ = 'ops_alertaction'
    ACTION_WEBHOOK = 'webhook'
    ACTION_NOTIFY = 'notify'
    ACTION_ACKNOWLEDGE = 'acknowledge'
    ACTION_CLAIM = 'claim'
    ACTION_UNCLAIM = 'unclaim'
    ACTION_MUTE = 'mute'
    ACTION_ESCALATE = 'escalate'
    ACTION_RESOLVE = 'resolve'
    ACTION_CLOSE = 'close'
    ACTION_REOPEN = 'reopen'
    ACTION_COMMENT = 'comment'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    alert_id: Mapped[int] = mapped_column('alert_id', Integer, ForeignKey('ops_alert.id', ondelete='CASCADE'), nullable=False, unique=False, index=False, primary_key=False)
    action: Mapped[str] = mapped_column('action', String(32), nullable=False, unique=False, index=False, primary_key=False)
    actor: Mapped[str] = mapped_column('actor', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    note: Mapped[str] = mapped_column('note', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    metadata_data: Mapped[dict[str, object] | list[object]] = mapped_column('metadata', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)


class AlertInteractionToken(Base):

    __tablename__ = 'ops_alertinteractiontoken'
    token: Mapped[str] = mapped_column('token', String(45), nullable=False, unique=False, index=False, primary_key=True, default=_uuid_string)
    alert_id: Mapped[int] = mapped_column('alert_id', Integer, ForeignKey('ops_alert.id', ondelete='CASCADE'), nullable=False, unique=False, index=False, primary_key=False)
    action: Mapped[str] = mapped_column('action', String(32), nullable=False, unique=False, index=False, primary_key=False)
    provider: Mapped[str] = mapped_column('provider', String(32), nullable=False, unique=False, index=False, primary_key=False, default='')
    expires_at: Mapped[datetime] = mapped_column('expires_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False)
    used_at: Mapped[datetime | None] = mapped_column('used_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    metadata_data: Mapped[dict[str, object] | list[object]] = mapped_column('metadata', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)


class LogEntry(Base):

    __tablename__ = 'ops_logentry'
    LEVEL_CHOICES = [('error', 'ERROR'), ('warning', 'WARNING'), ('info', 'INFO'), ('debug', 'DEBUG')]
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    level: Mapped[str] = mapped_column('level', String(16), nullable=False, unique=False, index=False, primary_key=False, default='info')
    service: Mapped[str] = mapped_column('service', String(128), nullable=False, unique=False, index=False, primary_key=False)
    message: Mapped[str] = mapped_column('message', Text, nullable=False, unique=False, index=False, primary_key=False)
    host_id: Mapped[int | None] = mapped_column('host_id', Integer, ForeignKey('ops_host.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    timestamp: Mapped[datetime] = mapped_column('timestamp', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)


class LogDataSource(Base):

    __tablename__ = 'ops_logdatasource'
    PROVIDER_CHOICES = [('loki', 'Loki'), ('elk', 'ELK / Elasticsearch'), ('sls', '阿里云 SLS')]
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=True, index=False, primary_key=False)
    provider: Mapped[str] = mapped_column('provider', String(16), nullable=False, unique=False, index=False, primary_key=False)
    description: Mapped[str] = mapped_column('description', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    config: Mapped[dict[str, object] | list[object]] = mapped_column('config', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    is_enabled: Mapped[bool] = mapped_column('is_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    is_default: Mapped[bool] = mapped_column('is_default', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=False)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class TracingDataSource(Base):

    __tablename__ = 'ops_tracingdatasource'
    PROVIDER_CHOICES = [('skywalking', 'SkyWalking'), ('tempo', 'Tempo / OpenTelemetry'), ('jaeger', 'Jaeger / OpenTelemetry'), ('zipkin', 'Zipkin / OpenTelemetry')]
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=True, index=False, primary_key=False)
    provider: Mapped[str] = mapped_column('provider', String(16), nullable=False, unique=False, index=False, primary_key=False)
    description: Mapped[str] = mapped_column('description', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    config: Mapped[dict[str, object] | list[object]] = mapped_column('config', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    is_enabled: Mapped[bool] = mapped_column('is_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    is_default: Mapped[bool] = mapped_column('is_default', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=False)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class MetricDataSource(Base):

    __tablename__ = 'ops_metricdatasource'
    PROVIDER_PROMETHEUS = 'prometheus'
    __table_args__ = (
        Index('ix_ops_metricdatasource_environment_is_enabled', 'environment', 'is_enabled'),
        Index('ix_ops_metricdatasource_provider_is_enabled', 'provider', 'is_enabled'),
    )
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=True, index=False, primary_key=False)
    provider: Mapped[str] = mapped_column('provider', String(32), nullable=False, unique=False, index=False, primary_key=False, default='prometheus')
    description: Mapped[str] = mapped_column('description', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    environment: Mapped[str] = mapped_column('environment', String(32), nullable=False, unique=False, index=False, primary_key=False, default='')
    cluster_name: Mapped[str] = mapped_column('cluster_name', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    tsdb_type: Mapped[str] = mapped_column('tsdb_type', String(32), nullable=False, unique=False, index=False, primary_key=False, default='prometheus')
    config: Mapped[dict[str, object] | list[object]] = mapped_column('config', JSON, nullable=False, unique=False, index=False, primary_key=False, default=dict)
    is_enabled: Mapped[bool] = mapped_column('is_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    is_default: Mapped[bool] = mapped_column('is_default', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=False)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class ObservabilityDataSourceLink(Base):

    __tablename__ = 'ops_observabilitydatasourcelink'
    __table_args__ = (
        UniqueConstraint('log_datasource_id', 'tracing_datasource_id', name='uq_ops_observabilitydatasourcelink_log_datasource_id_tracing_da'),
    )
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=True, index=False, primary_key=False)
    log_datasource_id: Mapped[int] = mapped_column('log_datasource_id', Integer, ForeignKey('ops_logdatasource.id', ondelete='CASCADE'), nullable=False, unique=False, index=False, primary_key=False)
    tracing_datasource_id: Mapped[int] = mapped_column('tracing_datasource_id', Integer, ForeignKey('ops_tracingdatasource.id', ondelete='CASCADE'), nullable=False, unique=False, index=False, primary_key=False)
    description: Mapped[str] = mapped_column('description', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    is_enabled: Mapped[bool] = mapped_column('is_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    is_default: Mapped[bool] = mapped_column('is_default', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=False)
    log_to_trace_enabled: Mapped[bool] = mapped_column('log_to_trace_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    trace_to_log_enabled: Mapped[bool] = mapped_column('trace_to_log_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    log_to_grafana_enabled: Mapped[bool] = mapped_column('log_to_grafana_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    trace_to_grafana_enabled: Mapped[bool] = mapped_column('trace_to_grafana_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    grafana_to_log_enabled: Mapped[bool] = mapped_column('grafana_to_log_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    grafana_to_trace_enabled: Mapped[bool] = mapped_column('grafana_to_trace_enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    trace_id_fields: Mapped[dict[str, object] | list[object]] = mapped_column('trace_id_fields', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    trace_id_regex: Mapped[str] = mapped_column('trace_id_regex', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    log_query_template: Mapped[str] = mapped_column('log_query_template', Text, nullable=False, unique=False, index=False, primary_key=False, default='')
    log_label_mappings: Mapped[dict[str, object] | list[object]] = mapped_column('log_label_mappings', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    grafana_dashboard_key: Mapped[str] = mapped_column('grafana_dashboard_key', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    grafana_variable_mappings: Mapped[dict[str, object] | list[object]] = mapped_column('grafana_variable_mappings', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    span_start_shift: Mapped[str] = mapped_column('span_start_shift', String(16), nullable=False, unique=False, index=False, primary_key=False, default='-5m')
    span_end_shift: Mapped[str] = mapped_column('span_end_shift', String(16), nullable=False, unique=False, index=False, primary_key=False, default='5m')
    window_minutes: Mapped[int] = mapped_column('window_minutes', Integer, nullable=False, unique=False, index=False, primary_key=False, default=10)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class GrafanaSetting(Base):

    __tablename__ = 'ops_grafanasetting'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(64), nullable=False, unique=True, index=False, primary_key=False, default='default')
    enabled: Mapped[bool] = mapped_column('enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    url: Mapped[str] = mapped_column('url', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    default_path: Mapped[str] = mapped_column('default_path', String(255), nullable=False, unique=False, index=False, primary_key=False, default='')
    folders: Mapped[dict[str, object] | list[object]] = mapped_column('folders', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    dashboards: Mapped[dict[str, object] | list[object]] = mapped_column('dashboards', JSON, nullable=False, unique=False, index=False, primary_key=False, default=list)
    updated_by: Mapped[str] = mapped_column('updated_by', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class K8sCluster(Base):

    __tablename__ = 'ops_k8scluster'
    STATUS_CHOICES = [('connected', '已连接'), ('disconnected', '未连接'), ('error', '异常')]
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=True, index=False, primary_key=False)
    api_server: Mapped[str] = mapped_column('api_server', String(256), nullable=False, unique=False, index=False, primary_key=False, default='')
    kubeconfig: Mapped[str] = mapped_column('kubeconfig', Text, nullable=False, unique=False, index=False, primary_key=False)
    status: Mapped[str] = mapped_column('status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='disconnected')
    description: Mapped[str] = mapped_column('description', String(256), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class K8sConfigRevision(Base):

    __tablename__ = 'ops_k8sconfigrevision'
    ACTION_CHOICES = [('update', 'Update Snapshot'), ('rollback', 'Rollback Snapshot')]
    __table_args__ = (
        Index('ix_ops_k8sconfigrevision_cluster_id_resource_type_namespace_res', 'cluster_id', 'resource_type', 'namespace', 'resource_name'),
    )
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    cluster_id: Mapped[int] = mapped_column('cluster_id', Integer, ForeignKey('ops_k8scluster.id', ondelete='CASCADE'), nullable=False, unique=False, index=False, primary_key=False)
    resource_type: Mapped[str] = mapped_column('resource_type', String(32), nullable=False, unique=False, index=False, primary_key=False)
    namespace: Mapped[str] = mapped_column('namespace', String(128), nullable=False, unique=False, index=False, primary_key=False)
    resource_name: Mapped[str] = mapped_column('resource_name', String(255), nullable=False, unique=False, index=False, primary_key=False)
    secret_type: Mapped[str] = mapped_column('secret_type', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    content: Mapped[str] = mapped_column('content', Text, nullable=False, unique=False, index=False, primary_key=False)
    operator: Mapped[str] = mapped_column('operator', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    action: Mapped[str] = mapped_column('action', String(32), nullable=False, unique=False, index=False, primary_key=False, default='update')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)


class DockerHost(Base):

    __tablename__ = 'ops_dockerhost'
    STATUS_CHOICES = [('connected', '已连接'), ('disconnected', '未连接'), ('error', '异常')]
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=True, index=False, primary_key=False)
    ip_address: Mapped[str] = mapped_column('ip_address', String(45), nullable=False, unique=False, index=False, primary_key=False)
    ssh_port: Mapped[int] = mapped_column('ssh_port', Integer, nullable=False, unique=False, index=False, primary_key=False, default=22)
    ssh_user: Mapped[str] = mapped_column('ssh_user', String(64), nullable=False, unique=False, index=False, primary_key=False, default='root')
    ssh_password: Mapped[str] = mapped_column('ssh_password', String(256), nullable=False, unique=False, index=False, primary_key=False, default='')
    docker_api_version: Mapped[str] = mapped_column('docker_api_version', String(16), nullable=False, unique=False, index=False, primary_key=False, default='')
    status: Mapped[str] = mapped_column('status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='disconnected')
    description: Mapped[str] = mapped_column('description', String(256), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class NginxEnvironment(Base):

    __tablename__ = 'ops_nginxenvironment'
    STATUS_CHOICES = [('connected', '已连接'), ('disconnected', '未连接'), ('error', '异常')]
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    name: Mapped[str] = mapped_column('name', String(128), nullable=False, unique=True, index=False, primary_key=False)
    ip_address: Mapped[str] = mapped_column('ip_address', String(45), nullable=False, unique=False, index=False, primary_key=False)
    ssh_port: Mapped[int] = mapped_column('ssh_port', Integer, nullable=False, unique=False, index=False, primary_key=False, default=22)
    ssh_user: Mapped[str] = mapped_column('ssh_user', String(64), nullable=False, unique=False, index=False, primary_key=False, default='root')
    ssh_password: Mapped[str] = mapped_column('ssh_password', String(256), nullable=False, unique=False, index=False, primary_key=False, default='')
    nginx_path: Mapped[str] = mapped_column('nginx_path', String(256), nullable=False, unique=False, index=False, primary_key=False, default='/etc/nginx')
    status: Mapped[str] = mapped_column('status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='disconnected')
    description: Mapped[str] = mapped_column('description', String(256), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class NginxCertificate(Base):

    __tablename__ = 'ops_nginxcertificate'
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    domain: Mapped[str] = mapped_column('domain', String(256), nullable=False, unique=False, index=False, primary_key=False)
    cert_content: Mapped[str] = mapped_column('cert_content', Text, nullable=False, unique=False, index=False, primary_key=False, default='')
    key_content: Mapped[str] = mapped_column('key_content', Text, nullable=False, unique=False, index=False, primary_key=False, default='')
    expires_at: Mapped[datetime | None] = mapped_column('expires_at', UTCDateTime(), nullable=True, unique=False, index=False, primary_key=False)
    description: Mapped[str] = mapped_column('description', String(256), nullable=False, unique=False, index=False, primary_key=False, default='')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class NginxDomain(Base):

    __tablename__ = 'ops_nginxdomain'
    __table_args__ = (
        UniqueConstraint('environment_id', 'domain', 'listen_port', name='uq_ops_nginxdomain_environment_id_domain_listen_port'),
    )
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    environment_id: Mapped[int] = mapped_column('environment_id', Integer, ForeignKey('ops_nginxenvironment.id', ondelete='CASCADE'), nullable=False, unique=False, index=False, primary_key=False)
    domain: Mapped[str] = mapped_column('domain', String(256), nullable=False, unique=False, index=False, primary_key=False)
    listen_port: Mapped[int] = mapped_column('listen_port', Integer, nullable=False, unique=False, index=False, primary_key=False, default=80)
    ssl_port: Mapped[int] = mapped_column('ssl_port', Integer, nullable=False, unique=False, index=False, primary_key=False, default=443)
    certificate_id: Mapped[int | None] = mapped_column('certificate_id', Integer, ForeignKey('ops_nginxcertificate.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    enabled: Mapped[bool] = mapped_column('enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class NginxRoute(Base):

    __tablename__ = 'ops_nginxroute'
    __table_args__ = (
        UniqueConstraint('nginx_domain_id', 'location', name='uq_ops_nginxroute_nginx_domain_id_location'),
    )
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    nginx_domain_id: Mapped[int] = mapped_column('nginx_domain_id', Integer, ForeignKey('ops_nginxdomain.id', ondelete='CASCADE'), nullable=False, unique=False, index=False, primary_key=False)
    location: Mapped[str] = mapped_column('location', String(256), nullable=False, unique=False, index=False, primary_key=False, default='/')
    upstream_servers: Mapped[str] = mapped_column('upstream_servers', Text, nullable=False, unique=False, index=False, primary_key=False, default='')
    redirect_url: Mapped[str] = mapped_column('redirect_url', String(512), nullable=False, unique=False, index=False, primary_key=False, default='')
    redirect_code: Mapped[int] = mapped_column('redirect_code', Integer, nullable=False, unique=False, index=False, primary_key=False, default=301)
    custom_headers: Mapped[str] = mapped_column('custom_headers', Text, nullable=False, unique=False, index=False, primary_key=False, default='')
    proxy_set_headers: Mapped[str] = mapped_column('proxy_set_headers', Text, nullable=False, unique=False, index=False, primary_key=False, default='')
    client_max_body_size: Mapped[str] = mapped_column('client_max_body_size', String(32), nullable=False, unique=False, index=False, primary_key=False, default='10m')
    extra_directives: Mapped[str] = mapped_column('extra_directives', Text, nullable=False, unique=False, index=False, primary_key=False, default='')
    enabled: Mapped[bool] = mapped_column('enabled', Boolean, nullable=False, unique=False, index=False, primary_key=False, default=True)
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)


class TransactionTicket(Base):

    __tablename__ = 'ops_transactionticket'
    TYPE_CHANGE = 'change'
    TYPE_INSPECTION = 'inspection'
    TYPE_ACCESS = 'access'
    TYPE_INCIDENT = 'incident'
    PRIORITY_HIGH = 'high'
    PRIORITY_MEDIUM = 'medium'
    PRIORITY_LOW = 'low'
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_PROCESSING = 'processing'
    STATUS_DONE = 'done'
    STATUS_REJECTED = 'rejected'
    __table_args__ = (
        Index('ix_ops_transactionticket_status_priority_updated_at', 'status', 'priority', 'updated_at'),
        Index('ix_ops_transactionticket_business_line_environment', 'business_line', 'environment'),
    )
    id: Mapped[int] = mapped_column('id', Integer, nullable=False, unique=False, index=False, primary_key=True)
    title: Mapped[str] = mapped_column('title', String(200), nullable=False, unique=False, index=False, primary_key=False)
    ticket_type: Mapped[str] = mapped_column('ticket_type', String(32), nullable=False, unique=False, index=False, primary_key=False, default='change')
    priority: Mapped[str] = mapped_column('priority', String(16), nullable=False, unique=False, index=False, primary_key=False, default='medium')
    business_line: Mapped[str] = mapped_column('business_line', String(50), nullable=False, unique=False, index=False, primary_key=False, default='')
    environment: Mapped[str] = mapped_column('environment', String(32), nullable=False, unique=False, index=False, primary_key=False, default='')
    approval_flow_id: Mapped[int | None] = mapped_column('approval_flow_id', Integer, ForeignKey('ops_deploymentapprovalflow.id', ondelete='SET NULL'), nullable=True, unique=False, index=False, primary_key=False)
    owner: Mapped[str] = mapped_column('owner', String(64), nullable=False, unique=False, index=False, primary_key=False, default='')
    applicant: Mapped[str] = mapped_column('applicant', String(64), nullable=False, unique=False, index=False, primary_key=False, default='system')
    window: Mapped[str] = mapped_column('window', String(128), nullable=False, unique=False, index=False, primary_key=False, default='')
    description: Mapped[str] = mapped_column('description', Text, nullable=False, unique=False, index=False, primary_key=False, default='')
    status: Mapped[str] = mapped_column('status', String(16), nullable=False, unique=False, index=False, primary_key=False, default='pending')
    created_at: Mapped[datetime] = mapped_column('created_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column('updated_at', UTCDateTime(), nullable=False, unique=False, index=False, primary_key=False, default=_utc_now, onupdate=_utc_now)




Table(
    'ops_alertrecipientgroup_recipients', Base.metadata,
    Column('source_id', ForeignKey('ops_alertrecipientgroup.id', ondelete='CASCADE'), primary_key=True),
    Column('target_id', ForeignKey('ops_alertrecipient.id', ondelete='CASCADE'), primary_key=True),
)


Table(
    'ops_alertrecipientgroup_users', Base.metadata,
    Column('source_id', ForeignKey('ops_alertrecipientgroup.id', ondelete='CASCADE'), primary_key=True),
    Column('target_id', ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
)


Table(
    'ops_alertnotificationrule_channels', Base.metadata,
    Column('source_id', ForeignKey('ops_alertnotificationrule.id', ondelete='CASCADE'), primary_key=True),
    Column('target_id', ForeignKey('ops_alertnotificationchannel.id', ondelete='CASCADE'), primary_key=True),
)


Table(
    'ops_alertnotificationrule_recipients', Base.metadata,
    Column('source_id', ForeignKey('ops_alertnotificationrule.id', ondelete='CASCADE'), primary_key=True),
    Column('target_id', ForeignKey('ops_alertrecipient.id', ondelete='CASCADE'), primary_key=True),
)


Table(
    'ops_alertnotificationrule_recipient_groups', Base.metadata,
    Column('source_id', ForeignKey('ops_alertnotificationrule.id', ondelete='CASCADE'), primary_key=True),
    Column('target_id', ForeignKey('ops_alertrecipientgroup.id', ondelete='CASCADE'), primary_key=True),
)


Table(
    'ops_nginxcertificate_environments', Base.metadata,
    Column('source_id', ForeignKey('ops_nginxcertificate.id', ondelete='CASCADE'), primary_key=True),
    Column('target_id', ForeignKey('ops_nginxenvironment.id', ondelete='CASCADE'), primary_key=True),
)


__all__ = ['Host', 'TaskResourceGroup', 'TaskResource', 'HostTask', 'HostTaskTemplate', 'HostTaskSchedule', 'HostTaskScheduleExecution', 'HostTaskExecution', 'Deployment', 'DeploymentApprovalFlow', 'DeploymentApprovalNode', 'DeploymentApprovalStep', 'Alert', 'AlertClaim', 'AlertIntegration', 'AlertRecipient', 'AlertRecipientGroup', 'AlertNotificationChannel', 'AlertAggregationRule', 'AlertInhibitionRule', 'AlertMuteRule', 'AlertEscalationPolicy', 'AlertNotificationRule', 'AlertNotificationLog', 'AlertAction', 'AlertInteractionToken', 'LogEntry', 'LogDataSource', 'TracingDataSource', 'MetricDataSource', 'ObservabilityDataSourceLink', 'GrafanaSetting', 'K8sCluster', 'K8sConfigRevision', 'DockerHost', 'NginxEnvironment', 'NginxCertificate', 'NginxDomain', 'NginxRoute', 'TransactionTicket']
