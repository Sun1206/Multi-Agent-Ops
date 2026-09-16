from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ops.modules.models import SystemModuleSetting
from rbac.models import User
from aidevops.exceptions import BusinessError
from ops.modules.schemas import ModuleSettingResponse, ModuleToggle


class ModuleCatalogItem(TypedDict):

    code: str
    title: str
    required: bool
    description: str
    sort_order: int


SYSTEM_MODULE_CATALOG: list[ModuleCatalogItem] = [
    {"code": "dashboard", "title": "仪表盘", "required": True, "description": "平台首页与核心概览入口。", "sort_order": 10},
    {"code": "aiops", "title": "AIOps", "required": True, "description": "智能助手、知识图谱与配置入口。", "sort_order": 20},
    {"code": "observability", "title": "可观测性", "required": True, "description": "监控、日志、链路与告警入口。", "sort_order": 30},
    {"code": "events", "title": "事件中心", "required": True, "description": "事件流、事件源与分析入口。", "sort_order": 40},
    {"code": "tasks", "title": "任务中心", "required": True, "description": "资源、工作台与定时任务入口。", "sort_order": 50},
    {"code": "workorders", "title": "工单系统", "required": False, "description": "发布、SQL 审计与事务工单入口。", "sort_order": 60},
    {"code": "containers", "title": "容器管理", "required": False, "description": "K8s 与 Docker 管理入口。", "sort_order": 70},
    {"code": "system", "title": "系统管理", "required": True, "description": "用户、审计与模块配置入口。", "sort_order": 80},
]


async def sync_modules(session: AsyncSession) -> None:
    existing = {item.code for item in (await session.scalars(select(SystemModuleSetting))).all()}
    session.add_all(SystemModuleSetting(code=item["code"], enabled=True) for item in SYSTEM_MODULE_CATALOG if item["code"] not in existing)
    await session.flush()


async def list_module_settings(session: AsyncSession) -> list[ModuleSettingResponse]:
    await sync_modules(session)
    rows = {item.code: item for item in (await session.scalars(select(SystemModuleSetting))).all()}
    return [ModuleSettingResponse(**catalog, enabled=rows[catalog["code"]].enabled, updated_by=rows[catalog["code"]].updated_by, updated_at=rows[catalog["code"]].updated_at) for catalog in SYSTEM_MODULE_CATALOG]


async def update_module_settings(session: AsyncSession, updates: list[ModuleToggle], actor: User) -> list[ModuleSettingResponse]:
    catalog = {item["code"]: item for item in SYSTEM_MODULE_CATALOG}
    unknown = sorted({item.code for item in updates} - set(catalog))
    if unknown:
        raise BusinessError(f"未知模块编码: {', '.join(unknown)}")
    update_map = {item.code: item.enabled for item in updates}
    await sync_modules(session)
    rows = (await session.scalars(select(SystemModuleSetting).with_for_update())).all()
    for row in rows:
        definition = catalog[row.code]
        row.enabled = True if definition["required"] else update_map.get(row.code, row.enabled)
        row.updated_by = actor.username
    await session.flush()
    return await list_module_settings(session)
