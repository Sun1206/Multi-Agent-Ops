from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rbac.models import AuthToken, User, UserGroup


def user_load_options() -> tuple[object, ...]:
    return (
        selectinload(User.roles),
        selectinload(User.groups).selectinload(UserGroup.roles),
    )


async def get_user_by_username(session: AsyncSession, username: str, *, for_update: bool = False) -> User | None:
    statement = select(User).where(User.username == username).options(*user_load_options())
    if for_update:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return (await session.execute(statement)).scalar_one_or_none()


async def get_user_by_token_digest(session: AsyncSession, token_digest: str) -> User | None:
    statement = (
        select(User)
        .join(AuthToken, AuthToken.user_id == User.id)
        .where(AuthToken.token_digest == token_digest, User.is_active.is_(True))
        .options(*user_load_options())
    )
    return (await session.execute(statement)).scalar_one_or_none()
