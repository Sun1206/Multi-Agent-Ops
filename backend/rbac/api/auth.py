from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from aidevops.dependencies import AuthDependency, SessionDependency, require_permissions
from rbac.models import User
from rbac.schemas.auth import LoginRequest, LoginResponse, SyncResponse, UserResponse
from rbac.schemas.common import SuccessResponse
from rbac.services.user_serialization import serialize_user
from rbac.services.accounts import authenticate_credentials, issue_token, revoke_token
from rbac.services.authorization import sync_rbac


router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/login/", response_model=LoginResponse, description="公开验证账号并返回不透明 Token 和用户资料。")
async def login(payload: LoginRequest, session: SessionDependency) -> LoginResponse:
    await sync_rbac(session)
    user = await authenticate_credentials(session, payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名或密码错误。")
    raw_token = await issue_token(session, user)
    response = LoginResponse(token=raw_token, user=await serialize_user(session, user))
    await session.commit()
    return response


@router.post("/logout/", response_model=SuccessResponse, description="认证用户撤销当前 Token 并立即退出。")
async def logout(session: SessionDependency, auth: AuthDependency) -> SuccessResponse:
    await revoke_token(session, auth.raw_token)
    await session.commit()
    return SuccessResponse()


@router.get("/me/", response_model=UserResponse, description="认证用户读取资料和实时有效权限。")
async def current_user(session: SessionDependency, auth: AuthDependency) -> UserResponse:
    return await serialize_user(session, auth.user)


@router.post("/sync/", response_model=SyncResponse, description="有权限用户幂等同步内置权限与角色目录。")
async def sync_permissions(
    session: SessionDependency,
    user: Annotated[User, Depends(require_permissions("rbac.permission.view"))],
) -> SyncResponse:
    await sync_rbac(session)
    await session.commit()
    return SyncResponse(message="内置权限与角色已同步。")
