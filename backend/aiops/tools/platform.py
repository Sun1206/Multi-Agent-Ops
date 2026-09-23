from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy import or_, select

from aiops.tools.contracts import (
    StrictToolArguments,
    ToolContext,
    ToolDefinition,
    build_tool_registry,
)
from eventwall.models import EventRecord
from eventwall.selectors import internal_audit_conditions
from ops.alerts.selectors import filtered_alerts, get_alert, project_alerts
from ops.models import Alert, Deployment
from ops.observability.logs.runtime import query as execute_log_query
from ops.observability.logs.schemas import LogQuery
from ops.observability.metrics.runtime import execute_metric_query
from ops.observability.metrics.schemas import MetricQuery
from rbac.models import User


# 为所有按时间查询的工具提供默认窗口和七天硬限制。
class WindowArguments(StrictToolArguments):
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_window(self):
        end = self.end or datetime.now(timezone.utc)
        start = self.start or end - timedelta(minutes=30)
        if start >= end or end - start > timedelta(days=7):
            raise ValueError("查询时间范围必须大于 0 且不超过 7 天。")
        self.start = start.astimezone(timezone.utc)
        self.end = end.astimezone(timezone.utc)
        return self


# 告警列表必须限定环境或具体搜索对象，且最多返回一百条。
class AlertListArguments(WindowArguments):
    search: str = Field(default="", max_length=128)
    severity: Literal["", "critical", "warning", "info"] = ""
    status: Literal["", "active", "resolved", "muted", "closed"] = ""
    environment: str = Field(default="", max_length=64)
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def require_scope(self):
        if not self.environment and not self.search:
            raise ValueError("告警查询必须指定环境或搜索对象。")
        return self


# 告警详情只接受数据库主键，不支持任意筛选表达式。
class AlertDetailArguments(StrictToolArguments):
    alert_id: int = Field(gt=0)


# 指标查询限制环境或数据源、七天窗口以及最大数据点数量。
class MetricQueryArguments(WindowArguments):
    promql: str = Field(min_length=1, max_length=2000)
    metric_datasource_id: int | None = Field(default=None, gt=0)
    environment: str = Field(default="", max_length=32)
    range_query: bool = True
    step: int = Field(default=30, ge=1, le=86400)

    @model_validator(mode="after")
    def require_scope_and_bound_points(self):
        if self.metric_datasource_id is None and not self.environment:
            raise ValueError("指标查询必须指定环境或数据源。")
        if self.range_query and (self.end - self.start).total_seconds() / self.step > 11000:
            raise ValueError("指标查询数据点数量超过限制。")
        return self


# 日志查询沿用现有三种提供商字段，并将结果条数收紧到二百条。
class LogQueryArguments(StrictToolArguments):
    datasource_id: int = Field(gt=0)
    provider: Literal["loki", "elk", "sls"]
    query: str = Field(min_length=1, max_length=8192)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    limit: int = Field(default=100, ge=1, le=200)
    source: str = Field(default="", max_length=512)
    index_pattern: str = Field(default="", max_length=512)
    time_field: str = Field(default="@timestamp", max_length=128)
    message_fields: str = Field(default="message,log,msg", max_length=512)
    logstore: str = Field(default="", max_length=128)
    topic: str = Field(default="", max_length=128)

    @model_validator(mode="after")
    def validate_window(self):
        if self.start_ms >= self.end_ms or self.end_ms - self.start_ms > 7 * 86_400_000:
            raise ValueError("日志查询时间范围必须大于 0 且不超过 7 天。")
        return self


# 最近变更必须限定环境或应用，避免读取无界事件时间线。
class RecentChangesArguments(WindowArguments):
    environment: str = Field(default="", max_length=32)
    application: str = Field(default="", max_length=128)
    limit: int = Field(default=50, ge=1, le=100)

    @model_validator(mode="after")
    def require_scope(self):
        if not self.environment and not self.application:
            raise ValueError("最近变更查询必须指定环境或应用。")
        return self


# 为现有指标和日志运行时构造最小只读请求上下文。
def runtime_request(context: ToolContext):
    return SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path=f"/api/aiops/internal/tools/{context.call_id}"),
        client=None,
        state=SimpleNamespace(
            correlation_id=f"aiops-tool:{context.message_id}:{context.call_id}"
        ),
        app=SimpleNamespace(state=SimpleNamespace(session_factory=context.factory)),
    )


# 查询符合环境、对象和时间窗口的告警列表。
async def query_alerts(
    context: ToolContext, args: AlertListArguments
) -> dict[str, object]:
    params = {
        "page": "1",
        "page_size": str(args.limit),
        "search": args.search,
        "level": args.severity,
        "status": args.status,
        "environment": args.environment,
    }
    async with context.factory() as database:
        actor = await database.get(User, context.actor_id)
        statement = await filtered_alerts(database, params)
        statement = statement.where(
            Alert.last_received_at >= args.start,
            Alert.last_received_at <= args.end,
        )
        rows = list(
            (await database.scalars(statement.limit(args.limit))).all()
        )
        projected = await project_alerts(database, rows, actor)
    return {"count": len(projected), "results": projected}


# 读取单条告警及其安全投影后的处理记录。
async def get_alert_detail(
    context: ToolContext, args: AlertDetailArguments
) -> dict[str, object]:
    async with context.factory() as database:
        actor = await database.get(User, context.actor_id)
        row = await get_alert(database, args.alert_id)
        return (await project_alerts(database, [row], actor))[0]


# 复用现有指标运行时执行 PromQL，并保留原有权限和操作审计。
async def query_metrics(
    context: ToolContext, args: MetricQueryArguments
) -> dict[str, object]:
    body = MetricQuery.model_validate(args.model_dump())
    return await execute_metric_query(
        context.factory, context.actor_id, runtime_request(context), body
    )


# 复用现有日志运行时执行查询，并保留数据源安全校验和操作审计。
async def query_logs(
    context: ToolContext, args: LogQueryArguments
) -> dict[str, object]:
    body = LogQuery.model_validate(args.model_dump())
    return await execute_log_query(
        context.factory, context.actor_id, runtime_request(context), body
    )


# 合并发布记录和事件墙时间线，只返回关联分析所需白名单字段。
async def query_recent_changes(
    context: ToolContext, args: RecentChangesArguments
) -> dict[str, object]:
    deployment_filters = [
        Deployment.deployed_at >= args.start,
        Deployment.deployed_at <= args.end,
    ]
    event_filters = [
        EventRecord.occurred_at >= args.start,
        EventRecord.occurred_at <= args.end,
        *internal_audit_conditions(),
    ]
    if args.environment:
        deployment_filters.append(Deployment.environment == args.environment)
        event_filters.append(EventRecord.environment == args.environment)
    if args.application:
        deployment_filters.append(Deployment.app_name == args.application)
        event_filters.append(
            or_(
                EventRecord.application == args.application,
                EventRecord.resource_name == args.application,
            )
        )
    async with context.factory() as database:
        deployments = list(
            (
                await database.scalars(
                    select(Deployment)
                    .where(*deployment_filters)
                    .order_by(Deployment.deployed_at.desc(), Deployment.id.desc())
                    .limit(args.limit)
                )
            ).all()
        )
        events = list(
            (
                await database.scalars(
                    select(EventRecord)
                    .where(*event_filters)
                    .order_by(EventRecord.occurred_at.desc(), EventRecord.id.desc())
                    .limit(args.limit)
                )
            ).all()
        )
    rows = [
        {
            "source": "deployment",
            "id": item.id,
            "occurred_at": item.deployed_at,
            "application": item.app_name,
            "environment": item.environment,
            "action": item.action_type,
            "status": item.status,
            "version": item.version,
            "operator": item.deployer or item.submitter,
            "summary": item.change_summary,
        }
        for item in deployments
    ]
    rows.extend(
        {
            "source": "eventwall",
            "id": item.id,
            "occurred_at": item.occurred_at,
            "application": item.application or item.resource_name,
            "environment": item.environment,
            "action": item.action,
            "status": item.result,
            "operator": item.actor_username,
            "summary": item.summary or item.title,
        }
        for item in events
    )
    rows.sort(key=lambda item: item["occurred_at"], reverse=True)
    results = rows[: args.limit]
    return {"count": len(results), "results": results}


# 构建第一阶段固定只读工具注册表。
def build_registry() -> dict[str, ToolDefinition]:
    return build_tool_registry(
        (
            ToolDefinition(
                "query_alerts",
                "按环境、对象和时间范围查询告警列表。",
                AlertListArguments,
                ("aiops.chat.view", "ops.alert.view"),
                "read_only",
                query_alerts,
            ),
            ToolDefinition(
                "get_alert_detail",
                "按告警 ID 读取告警详情和已有处理记录。",
                AlertDetailArguments,
                ("aiops.chat.view", "ops.alert.view"),
                "read_only",
                get_alert_detail,
            ),
            ToolDefinition(
                "query_metrics",
                "通过已配置指标数据源执行受限 PromQL 查询。",
                MetricQueryArguments,
                ("aiops.chat.view", "ops.metric.query"),
                "read_only",
                query_metrics,
            ),
            ToolDefinition(
                "query_logs",
                "通过已配置日志数据源执行受限日志查询。",
                LogQueryArguments,
                ("aiops.chat.view", "ops.log.query"),
                "read_only",
                query_logs,
            ),
            ToolDefinition(
                "query_recent_changes",
                "按环境或应用查询近期发布记录和事件时间线。",
                RecentChangesArguments,
                ("aiops.chat.view", "ops.deployment.view", "eventwall.view"),
                "read_only",
                query_recent_changes,
            ),
        )
    )
