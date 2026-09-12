from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import AuthDependency, SessionDependency, require_permissions
from app.models import User
from app.schemas.module import ModuleSettingResponse, ModuleSettingsBody, ModuleToggle, ModuleUpdateResponse, normalize_module_payload
from app.services.events import record_event
from app.services.modules import list_module_settings, update_module_settings


router = APIRouter(prefix="/api/module-settings", tags=["模块设置"])


@router.get("/", response_model=list[ModuleSettingResponse])
async def get_modules(session: SessionDependency, auth: AuthDependency) -> list[ModuleSettingResponse]:
    """GET /api/module-settings/：认证用户读取完整模块显示配置。"""
    return await list_module_settings(session)


async def write_modules(
    request: Request,
    payload: list[ModuleToggle] | ModuleSettingsBody,
    session: SessionDependency,
    actor: User,
) -> ModuleUpdateResponse:
    """更新模块并在同一事务写入脱敏审计事件。"""
    updates = normalize_module_payload(payload)
    items = await update_module_settings(session, updates, actor)
    correlation_id = getattr(request.state, "correlation_id", "")
    client_ip = request.client.host if request.client else ""
    await record_event(
        session,
        actor=actor,
        method=request.method,
        path=request.url.path,
        ip_address=client_ip,
        correlation_id=correlation_id,
        action="update_module_settings",
        title="更新系统模块显示配置",
        resource_type="rbac_system_module_setting",
        resource_id="module-settings",
        metadata={"updated_count": len(items)},
    )
    await session.commit()
    return ModuleUpdateResponse(data=items)


@router.put("/", response_model=ModuleUpdateResponse)
async def put_modules(
    request: Request,
    payload: list[ModuleToggle] | ModuleSettingsBody,
    session: SessionDependency,
    actor: Annotated[User, Depends(require_permissions("rbac.module.manage"))],
) -> ModuleUpdateResponse:
    """PUT /api/module-settings/：有管理权限用户整体更新模块开关。"""
    return await write_modules(request, payload, session, actor)


@router.patch("/", response_model=ModuleUpdateResponse)
async def patch_modules(
    request: Request,
    payload: list[ModuleToggle] | ModuleSettingsBody,
    session: SessionDependency,
    actor: Annotated[User, Depends(require_permissions("rbac.module.manage"))],
) -> ModuleUpdateResponse:
    """PATCH /api/module-settings/：有管理权限用户局部更新模块开关。"""
    return await write_modules(request, payload, session, actor)
