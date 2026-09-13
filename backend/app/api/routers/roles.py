from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.dependencies import SessionDependency, require_permissions
from app.models import User
from app.schemas.rbac import RoleResponse
from app.selectors.rbac import get_role, list_roles, serialize_role
from app.schemas.rbac import RoleCreate, RolePatch
from app.services import role_management as mutations
from app.api.audit import audit_and_commit


router = APIRouter(prefix="/api/roles", tags=["角色管理"])
Viewer = Annotated[User, Depends(require_permissions("rbac.role.view"))]
Manager = Annotated[User, Depends(require_permissions("rbac.role.manage"))]


@router.get("/", response_model=list[RoleResponse], description="直接返回角色数组及权限绑定，兼容现有前端。")
async def roles_list(session: SessionDependency, actor: Viewer, search: str = "") -> list[RoleResponse]:
    return [serialize_role(role) for role in await list_roles(session, search.strip())]


@router.get("/{role_id}/", response_model=RoleResponse, description="读取指定角色及其权限集合。")
async def role_detail(role_id: int, session: SessionDependency, actor: Viewer) -> RoleResponse:
    return serialize_role(await get_role(session, role_id))


@router.post("/", response_model=RoleResponse, status_code=201, description="创建自定义角色和权限集合并记录审计。")
async def role_create(payload: RoleCreate, request: Request, session: SessionDependency, actor: Manager) -> RoleResponse:
    data = payload.model_dump(exclude_unset=True)
    role = await mutations.create_role(session, actor, data)
    result = serialize_role(role)
    await audit_and_commit(session, request, actor, action="create_role", resource_type="role", resource_id=role.id, fields=list(data), data=data)
    return result


@router.patch("/{role_id}/", response_model=RoleResponse, description="部分更新角色资料及权限绑定。")
async def role_update(role_id: int, payload: RolePatch, request: Request, session: SessionDependency, actor: Manager) -> RoleResponse:
    data = payload.model_dump(exclude_unset=True)
    role = await mutations.update_role(session, actor, role_id, data)
    result = serialize_role(role)
    await audit_and_commit(session, request, actor, action="update_role", resource_type="role", resource_id=role.id, fields=list(data), data=data)
    return result


@router.delete("/{role_id}/", status_code=204, description="删除角色并级联解除所有授权绑定。")
async def role_delete(role_id: int, request: Request, session: SessionDependency, actor: Manager) -> Response:
    await mutations.delete_role(session, actor, role_id)
    await audit_and_commit(session, request, actor, action="delete_role", resource_type="role", resource_id=role_id, fields=[])
    return Response(status_code=204)
