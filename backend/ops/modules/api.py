from typing import Annotated

from fastapi import APIRouter, Depends, Request

from aidevops.dependencies import AuthDependency, SessionDependency, require_permissions
from rbac.models import User
from ops.modules.schemas import ModuleSettingResponse, ModuleSettingsBody, ModuleToggle, ModuleUpdateResponse, normalize_module_payload
from eventwall.services import record_event
from ops.modules.services import list_module_settings, update_module_settings


router = APIRouter(prefix="/api/module-settings", tags=["模块设置"])


@router.get("/", response_model=list[ModuleSettingResponse], description="认证用户读取完整模块显示配置。")
async def get_modules(session: SessionDependency, auth: AuthDependency) -> list[ModuleSettingResponse]:
    return await list_module_settings(session)


async def write_modules(
    request: Request,
    payload: list[ModuleToggle] | ModuleSettingsBody,
    session: SessionDependency,
    actor: User,
) -> ModuleUpdateResponse:
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


@router.put("/", response_model=ModuleUpdateResponse, description="有管理权限用户整体更新模块开关。")
async def put_modules(
    request: Request,
    payload: list[ModuleToggle] | ModuleSettingsBody,
    session: SessionDependency,
    actor: Annotated[User, Depends(require_permissions("rbac.module.manage"))],
) -> ModuleUpdateResponse:
    return await write_modules(request, payload, session, actor)


@router.patch("/", response_model=ModuleUpdateResponse, description="有管理权限用户局部更新模块开关。")
async def patch_modules(
    request: Request,
    payload: list[ModuleToggle] | ModuleSettingsBody,
    session: SessionDependency,
    actor: Annotated[User, Depends(require_permissions("rbac.module.manage"))],
) -> ModuleUpdateResponse:
    return await write_modules(request, payload, session, actor)
