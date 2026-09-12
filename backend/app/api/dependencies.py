from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import digest_token
from app.models import User
from app.selectors.accounts import get_user_by_token_digest
from app.selectors.permissions import user_has_permissions


SessionDependency = Annotated[AsyncSession, Depends(get_session)]


@dataclass(frozen=True)
class AuthContext:
    """携带已认证用户和仅用于当前请求撤销的原始令牌。"""

    user: User
    raw_token: str


async def get_auth_context(
    session: SessionDependency,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthContext:
    """解析 `Authorization: Token` 并按摘要查询启用账号。"""
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未提供认证令牌。")
    scheme, separator, raw_token = authorization.partition(" ")
    if scheme != "Token" or not separator or not raw_token.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证令牌格式无效。")
    raw_token = raw_token.strip()
    user = await get_user_by_token_digest(session, digest_token(raw_token))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证令牌无效。")
    return AuthContext(user=user, raw_token=raw_token)


AuthDependency = Annotated[AuthContext, Depends(get_auth_context)]


def require_permissions(*codes: str):
    """创建权限依赖，要求普通用户具备全部权限而超级管理员直接通过。"""

    async def dependency(session: SessionDependency, auth: AuthDependency) -> User:
        """执行当前接口声明的服务端权限检查。"""
        if not await user_has_permissions(session, auth.user, tuple(codes)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前用户没有执行此操作的权限。")
        return auth.user

    return dependency
