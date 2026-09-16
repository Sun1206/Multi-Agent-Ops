# 查询指标数据源并按调用者权限生成不泄露连接配置的响应投影。

from collections.abc import Mapping

from fastapi import HTTPException
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ops.models import MetricDataSource


SAFE_FIELDS = (
    "id",
    "name",
    "provider",
    "description",
    "environment",
    "cluster_name",
    "tsdb_type",
    "is_enabled",
    "is_default",
)
PROVIDER_LABELS = {"prometheus": "Prometheus"}


# 解析布尔筛选值，拒绝容易产生误判的任意真值字符串。
def boolean_filter(raw: str) -> bool:
    normalized = raw.strip().lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    raise HTTPException(status_code=422, detail="is_enabled 筛选值无效。")


# 生成数据源列表查询，筛选字段和排序均保持稳定且无网络副作用。
def filtered_data_sources(params: Mapping[str, str]) -> Select:
    statement = select(MetricDataSource)
    provider = params.get("provider", "").strip()
    environment = params.get("environment")
    enabled = params.get("is_enabled")
    search = params.get("search", "").strip()
    if provider:
        statement = statement.where(MetricDataSource.provider == provider)
    if environment is not None:
        statement = statement.where(MetricDataSource.environment == environment.strip())
    if enabled is not None and enabled != "":
        statement = statement.where(MetricDataSource.is_enabled.is_(boolean_filter(enabled)))
    if search:
        pattern = f"%{search}%"
        statement = statement.where(
            or_(
                MetricDataSource.name.ilike(pattern),
                MetricDataSource.description.ilike(pattern),
                MetricDataSource.environment.ilike(pattern),
                MetricDataSource.cluster_name.ilike(pattern),
            )
        )
    return statement.order_by(MetricDataSource.is_default.desc(), MetricDataSource.name, MetricDataSource.id)


# 获取单个数据源；写路径可请求行锁，未命中统一返回 404。
async def get_data_source(session: AsyncSession, identifier: int, *, lock: bool = False) -> MetricDataSource:
    statement = select(MetricDataSource).where(MetricDataSource.id == identifier).execution_options(populate_existing=True)
    if lock:
        statement = statement.with_for_update()
    item = await session.scalar(statement)
    if item is None:
        raise HTTPException(status_code=404, detail="指标数据源不存在。")
    return item


# 按显式 ID、环境默认、环境其他、全局默认、其他启用项的顺序选择数据源。
async def choose_data_source(
    session: AsyncSession,
    identifier: int | None,
    environment: str,
) -> MetricDataSource:
    if identifier is not None:
        item = await get_data_source(session, identifier)
        if not item.is_enabled:
            raise HTTPException(status_code=400, detail="指标数据源未启用。")
        return item
    rows = list(
        (
            await session.scalars(
                select(MetricDataSource)
                .where(MetricDataSource.is_enabled.is_(True))
                .order_by(MetricDataSource.name, MetricDataSource.id)
            )
        ).all()
    )
    normalized = environment.strip()
    groups = (
        [item for item in rows if normalized and item.environment == normalized and item.is_default],
        [item for item in rows if normalized and item.environment == normalized and not item.is_default],
        [item for item in rows if not item.environment and item.is_default],
        rows,
    )
    for group in groups:
        if group:
            return group[0]
    raise HTTPException(status_code=400, detail="没有可用的指标数据源。")


# 精简投影只从公开白名单构造；完整投影额外加入脱敏配置和时间字段。
def project_data_source(item: MetricDataSource, *, include_config: bool) -> dict[str, object]:
    from ops.observability.metrics.config_service import mask_metric_config

    response = {field: getattr(item, field) for field in SAFE_FIELDS}
    response["provider_display"] = PROVIDER_LABELS.get(item.provider, item.provider)
    if include_config:
        response.update(config=mask_metric_config(item.config if isinstance(item.config, dict) else {}), created_at=item.created_at, updated_at=item.updated_at)
    return response
