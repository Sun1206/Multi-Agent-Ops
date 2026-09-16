"""集中注册各领域路由，保持既有 OpenAPI 顺序和路径。"""

from fastapi import FastAPI

from aiops.api.agent_config import router as agent_config_router
from aiops.api.chat import router as chat_router
from eventwall.api import router as events_router
from ops.alerts.api import router as alerts_router
from ops.alerts.config_api import router as alert_config_router
from ops.modules.api import router as module_router
from ops.observability.metrics.api import router as metrics_router
from rbac.api.auth import router as auth_router
from rbac.api.groups import router as groups_router
from rbac.api.permissions import router as permissions_router
from rbac.api.roles import router as roles_router
from rbac.api.users import router as users_router


ROUTERS = (
    auth_router,
    module_router,
    users_router,
    roles_router,
    groups_router,
    permissions_router,
    events_router,
    agent_config_router,
    chat_router,
    alerts_router,
    alert_config_router,
    metrics_router,
)


def register_routes(application: FastAPI) -> None:
    """按稳定顺序把所有领域 API 注册到 FastAPI 应用。"""
    for router in ROUTERS:
        application.include_router(router)
