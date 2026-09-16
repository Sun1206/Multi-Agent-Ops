from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from aidevops.database import get_session
from aidevops.security import digest_token
from rbac.public import User, effective_permission_codes, get_user_by_token_digest, user_has_permissions


SessionDependency = Annotated[AsyncSession, Depends(get_session)]


@dataclass(frozen=True)
class AuthContext:

    user: User
    raw_token: str


async def get_auth_context(
    session: SessionDependency,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthContext:
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

    async def dependency(session: SessionDependency, auth: AuthDependency) -> User:
        if not await user_has_permissions(session, auth.user, tuple(codes)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前用户没有执行此操作的权限。")
        return auth.user

    return dependency


# 接受指定权限中的任意一个，用于同一路由按权限返回不同安全投影。
def require_any_permission(*codes: str):

    async def dependency(session: SessionDependency, auth: AuthDependency) -> User:
        if auth.user.is_superuser:
            return auth.user
        granted = set(await effective_permission_codes(session, auth.user))
        if not granted.intersection(codes):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前用户没有执行此操作的权限。")
        return auth.user

    return dependency
