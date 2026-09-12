from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.dependencies import SessionDependency, require_permissions
from app.models import User
from app.schemas.rbac import GroupResponse
from app.selectors.rbac import get_group, list_groups, serialize_group
from app.schemas.rbac import GroupCreate, GroupPatch
from app.services import group_management as mutations
from app.api.audit import audit_and_commit


router = APIRouter(prefix="/api/groups", tags=["用户组管理"])
Viewer = Annotated[User, Depends(require_permissions("rbac.group.view"))]
Manager = Annotated[User, Depends(require_permissions("rbac.group.manage"))]


@router.get("/", response_model=list[GroupResponse])
async def groups_list(session: SessionDependency, actor: Viewer, search: str = "") -> list[GroupResponse]:
    """GET /api/groups/：返回用户组数组及角色、成员映射。"""
    return [serialize_group(group) for group in await list_groups(session, search.strip())]


@router.get("/{group_id}/", response_model=GroupResponse)
async def group_detail(group_id: int, session: SessionDependency, actor: Viewer) -> GroupResponse:
    """GET /api/groups/{id}/：读取指定用户组的角色和成员。"""
    return serialize_group(await get_group(session, group_id))


@router.post("/", response_model=GroupResponse, status_code=201)
async def group_create(payload: GroupCreate, request: Request, session: SessionDependency, actor: Manager) -> GroupResponse:
    """POST /api/groups/：创建用户组、角色和成员关系并记录审计。"""
    data = payload.model_dump(exclude_unset=True)
    group = await mutations.create_group(session, actor, data)
    result = serialize_group(group)
    await audit_and_commit(session, request, actor, action="create_group", resource_type="group", resource_id=group.id, fields=list(data), data=data)
    return result


@router.patch("/{group_id}/", response_model=GroupResponse)
async def group_update(group_id: int, payload: GroupPatch, request: Request, session: SessionDependency, actor: Manager) -> GroupResponse:
    """PATCH /api/groups/{id}/：部分修改用户组并替换显式关系集合。"""
    data = payload.model_dump(exclude_unset=True)
    group = await mutations.update_group(session, actor, group_id, data)
    result = serialize_group(group)
    await audit_and_commit(session, request, actor, action="update_group", resource_type="group", resource_id=group.id, fields=list(data), data=data)
    return result


@router.delete("/{group_id}/", status_code=204)
async def group_delete(group_id: int, request: Request, session: SessionDependency, actor: Manager) -> Response:
    """DELETE /api/groups/{id}/：删除用户组并解除角色和成员绑定。"""
    await mutations.delete_group(session, actor, group_id)
    await audit_and_commit(session, request, actor, action="delete_group", resource_type="group", resource_id=group_id, fields=[])
    return Response(status_code=204)
