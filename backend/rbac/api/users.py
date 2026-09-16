from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from aidevops.dependencies import SessionDependency, require_permissions
from rbac.models import User
from rbac.schemas.auth import UserResponse
from rbac.schemas.authorization import UserPageResponse
from rbac.selectors.users import get_user, list_users
from rbac.services.user_serialization import permission_map, serialize_user, user_response
from rbac.schemas.authorization import UserCreate, UserPatch, PasswordReset
from rbac.schemas.common import SuccessResponse
from rbac.services import users as mutations
from rbac.audit.api import audit_and_commit


router = APIRouter(prefix="/api/users", tags=["用户管理"])
Viewer = Annotated[User, Depends(require_permissions("rbac.user.view"))]
Manager = Annotated[User, Depends(require_permissions("rbac.user.manage"))]


@router.get("/", response_model=UserPageResponse, description="分页搜索账号，并批量返回角色、用户组和有效权限。")
async def users_list(request: Request, session: SessionDependency, actor: Viewer, page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1)] = 20, search: str = "") -> UserPageResponse:
    size = min(page_size, 200)
    count, users = await list_users(session, page=page, page_size=size, search=search.strip())
    permissions = await permission_map(session, users)
    return UserPageResponse(count=count, next=str(request.url.include_query_params(page=page + 1, page_size=size)) if page * size < count else None, previous=str(request.url.include_query_params(page=page - 1, page_size=size)) if page > 1 else None, results=[user_response(user, permissions[user.id]) for user in users])


@router.get("/{user_id}/", response_model=UserResponse, description="读取指定账号的完整前端兼容资料。")
async def user_detail(user_id: int, session: SessionDependency, actor: Viewer) -> UserResponse:
    return await serialize_user(session, await get_user(session, user_id))


@router.post("/", response_model=UserResponse, status_code=201, description="创建账号并原子写入角色/用户组绑定及审计。")
async def user_create(payload: UserCreate, request: Request, session: SessionDependency, actor: Manager) -> UserResponse:
    data = payload.model_dump(exclude_unset=True)
    user = await mutations.create_user(session, actor, data)
    result = await serialize_user(session, user)
    await audit_and_commit(session, request, actor, action="create_user", resource_type="user", resource_id=user.id, fields=list(data), data=data)
    return result


@router.patch("/{user_id}/", response_model=UserResponse, description="部分更新账号，缺省关系和密码保持不变。")
async def user_update(user_id: int, payload: UserPatch, request: Request, session: SessionDependency, actor: Manager) -> UserResponse:
    data = payload.model_dump(exclude_unset=True)
    user = await mutations.update_user(session, actor, user_id, data)
    result = await serialize_user(session, user)
    await audit_and_commit(session, request, actor, action="update_user", resource_type="user", resource_id=user.id, fields=list(data), data=data)
    return result


@router.post("/{user_id}/reset_password/", response_model=SuccessResponse, description="重置密码并撤销账号全部令牌。")
async def user_reset_password(user_id: int, payload: PasswordReset, request: Request, session: SessionDependency, actor: Manager) -> SuccessResponse:
    await mutations.reset_password(session, actor, user_id, payload.password)
    await audit_and_commit(session, request, actor, action="reset_user_password", resource_type="user", resource_id=user_id, fields=["password"])
    return SuccessResponse()


@router.delete("/{user_id}/", status_code=204, description="删除账号及关系，保留历史审计。")
async def user_delete(user_id: int, request: Request, session: SessionDependency, actor: Manager) -> Response:
    await mutations.delete_user(session, actor, user_id)
    await audit_and_commit(session, request, actor, action="delete_user", resource_type="user", resource_id=user_id, fields=[])
    return Response(status_code=204)
