"""负责账号详情及稳定的分页查询，不执行写入。"""

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.selectors.accounts import user_load_options


async def get_user(session: AsyncSession, user_id: int, *, for_update: bool = False) -> User:
    """按 ID 预加载用户关系；不存在时返回统一 404。"""
    statement = select(User).where(User.id == user_id).options(*user_load_options()).execution_options(populate_existing=True)
    if for_update:
        statement = statement.with_for_update()
    user = await session.scalar(statement)
    if user is None:
        raise HTTPException(404, detail="用户不存在。")
    return user


async def list_users(session: AsyncSession, *, page: int, page_size: int, search: str) -> tuple[int, list[User]]:
    """按用户名/邮箱搜索并以 ID 分页，避免跨页重复和不稳定排序。"""
    predicates = []
    if search:
        predicates.append(or_(User.username.icontains(search), User.email.icontains(search)))
    count = await session.scalar(select(func.count()).select_from(User).where(*predicates))
    if page > 1 and (page - 1) * page_size >= count:
        raise HTTPException(404, detail="请求的页码不存在。")
    statement = select(User).where(*predicates).order_by(User.id).offset((page - 1) * page_size).limit(page_size).options(*user_load_options())
    return count, list((await session.scalars(statement)).all())
