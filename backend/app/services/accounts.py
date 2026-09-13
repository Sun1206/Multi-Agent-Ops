from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import digest_token, generate_token, hash_password, verify_password
from app.models import AuthToken, User
from app.selectors.accounts import get_user_by_username


async def authenticate_credentials(session: AsyncSession, username: str, password: str) -> User | None:
    # 密码校验、最后登录时间和令牌签发共用一个事务，阻止旧密码与重置并发。
    user = await get_user_by_username(session, username, for_update=True)
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        return None
    user.last_login = datetime.now(timezone.utc)
    await session.flush()
    return user


async def issue_token(session: AsyncSession, user: User) -> str:
    raw_token = generate_token()
    session.add(AuthToken(user_id=user.id, token_digest=digest_token(raw_token)))
    await session.flush()
    return raw_token


async def revoke_token(session: AsyncSession, raw_token: str) -> None:
    await session.execute(delete(AuthToken).where(AuthToken.token_digest == digest_token(raw_token)))


async def ensure_admin(session: AsyncSession, initial_password: str | None) -> User | None:
    if not initial_password:
        return None
    admin = (await session.execute(select(User).where(User.username == "admin").with_for_update())).scalar_one_or_none()
    if admin is None:
        admin = User(username="admin", email="admin@example.com", password_hash=hash_password(initial_password))
        session.add(admin)
    else:
        admin.password_hash = hash_password(initial_password)
    admin.is_active = True
    admin.is_staff = True
    admin.is_superuser = True
    await session.flush()
    return admin
