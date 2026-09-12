from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import AuthDependency, SessionDependency, require_permissions
from app.models import User
from app.schemas.auth import LoginRequest, LoginResponse, SyncResponse, UserResponse
from app.schemas.common import SuccessResponse
from app.services.user_serialization import serialize_user
from app.services.accounts import authenticate_credentials, issue_token, revoke_token
from app.services.rbac import sync_rbac


router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/login/", response_model=LoginResponse)
async def login(payload: LoginRequest, session: SessionDependency) -> LoginResponse:
    """POST /api/auth/login/：公开验证账号并返回不透明 Token 和用户资料。"""
    await sync_rbac(session)
    user = await authenticate_credentials(session, payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名或密码错误。")
    raw_token = await issue_token(session, user)
    response = LoginResponse(token=raw_token, user=await serialize_user(session, user))
    await session.commit()
    return response


@router.post("/logout/", response_model=SuccessResponse)
async def logout(session: SessionDependency, auth: AuthDependency) -> SuccessResponse:
    """POST /api/auth/logout/：认证用户撤销当前 Token 并立即退出。"""
    await revoke_token(session, auth.raw_token)
    await session.commit()
    return SuccessResponse()


@router.get("/me/", response_model=UserResponse)
async def current_user(session: SessionDependency, auth: AuthDependency) -> UserResponse:
    """GET /api/auth/me/：认证用户读取资料和实时有效权限。"""
    return await serialize_user(session, auth.user)


@router.post("/sync/", response_model=SyncResponse)
async def sync_permissions(
    session: SessionDependency,
    user: Annotated[User, Depends(require_permissions("rbac.permission.view"))],
) -> SyncResponse:
    """POST /api/auth/sync/：有权限用户幂等同步内置权限与角色目录。"""
    await sync_rbac(session)
    await session.commit()
    return SyncResponse(message="内置权限与角色已同步。")
