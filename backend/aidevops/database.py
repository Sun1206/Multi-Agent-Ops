from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from aidevops.config import Settings


class Base(DeclarativeBase):
    pass


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=10,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def load_domain_models() -> None:
    """加载全部领域模型并统一设置 MySQL 表选项。"""
    import ops.modules.models  # noqa: F401
    import aiops.models  # noqa: F401
    import eventwall.models  # noqa: F401
    import ops.models  # noqa: F401
    import rbac.models  # noqa: F401

    for table in Base.metadata.tables.values():
        table.kwargs["mysql_engine"] = "InnoDB"
        table.kwargs["mysql_charset"] = "utf8mb4"
