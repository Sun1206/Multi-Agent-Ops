"""显式启用的 MySQL 验收，要求已初始化且无用户的独立测试库。"""

import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from aidevops.config import Settings
from aidevops.database import Base
from aidevops.exceptions import BusinessError
from aidevops.security import hash_password
from rbac.models import AuthToken, User
from rbac.services.users import update_user
from rbac.services.users import reset_password
from rbac.services.accounts import authenticate_credentials, issue_token


pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(os.environ.get("AIOPS_RUN_MYSQL_TESTS") != "1", reason="需要显式启用独立 MySQL 测试库")]


@pytest_asyncio.fixture
async def isolated_mysql():
    settings = Settings(database_mode="test")
    assert settings.active_database.endswith("_test")
    assert settings.active_database != settings.mysql_database
    engine = create_async_engine(settings.database_url, connect_args={"connect_timeout": 5})
    ids = []
    try:
        try:
            async with engine.connect() as connection:
                names = await connection.run_sync(lambda conn: set(inspect(conn).get_table_names()))
                if not set(Base.metadata.tables) <= names:
                    pytest.skip("请先在独立测试库运行完整 Alembic 迁移")
                count = (await connection.execute(select(func.count()).select_from(User))).scalar_one()
                if count:
                    pytest.skip("管理员并发测试要求测试库无现存用户；不会清空数据库")
        except Exception as error:
            original = getattr(error, "orig", error)
            args = getattr(original, "args", ())
            pytest.skip("测试库不可访问；错误代码：" + str(args[0] if args and isinstance(args[0], int) else "unknown"))
        factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        prefix = "test-rbac-" + uuid4().hex[:12]
        async with factory() as session:
            for index in range(2):
                user = User(username=f"{prefix}-{index}", password_hash=hash_password("mysql-test-secret"), is_superuser=True, is_staff=True)
                session.add(user)
                await session.flush()
                ids.append(user.id)
            await session.commit()
        yield factory, ids
    finally:
        if ids:
            async with async_sessionmaker(engine)() as session:
                await session.execute(delete(User).where(User.id.in_(ids)))
                await session.commit()
        await engine.dispose()


async def test_mysql_concurrent_disable_keeps_one_active_admin(isolated_mysql):
    factory, ids = isolated_mysql
    barrier = asyncio.Event()
    ready = 0
    async def disable(id_):
        nonlocal ready
        async with factory() as session:
            actor = await session.get(User, id_)
            ready += 1
            if ready == 2:
                barrier.set()
            await barrier.wait()
            try:
                await update_user(session, actor, id_, {"is_active": False})
                await session.commit()
                return "disabled"
            except BusinessError:
                await session.rollback()
                return "protected"
    results = await asyncio.wait_for(asyncio.gather(*(disable(id_) for id_ in ids)), timeout=20)
    assert sorted(results) == ["disabled", "protected"]
    async with factory() as session:
        count = await session.scalar(select(func.count()).select_from(User).where(User.id.in_(ids), User.is_active.is_(True)))
        assert count == 1


async def test_mysql_transaction_rollback_and_user_token_cascade(isolated_mysql):
    factory, ids = isolated_mysql
    async with factory() as session:
        actor = await session.get(User, ids[0])
        await update_user(session, actor, ids[1], {"email": "uncommitted@example.com"})
        await session.rollback()
    async with factory() as session:
        target = await session.get(User, ids[1])
        assert target.email == ""
        session.add(AuthToken(user_id=target.id, token_digest=uuid4().hex + uuid4().hex))
        await session.commit()
        await session.execute(delete(User).where(User.id == ids[1]))
        await session.commit()
        assert await session.scalar(select(func.count()).select_from(AuthToken).where(AuthToken.user_id == ids[1])) == 0


async def test_mysql_old_password_login_waits_for_reset_and_cannot_issue_token(isolated_mysql):
    factory, ids = isolated_mysql
    login_started = asyncio.Event()
    async with factory() as resetting, factory() as logging_in:
        actor = await resetting.get(User, ids[0])
        target = await reset_password(resetting, actor, ids[1], "new-mysql-secret")
        username = target.username
        original = logging_in.execute
        async def execute(statement, *args, **kwargs):
            login_started.set()
            return await original(statement, *args, **kwargs)
        logging_in.execute = execute
        async def login():
            user = await authenticate_credentials(logging_in, username, "mysql-test-secret")
            if user is not None:
                await issue_token(logging_in, user)
            await logging_in.commit()
            return user
        task = asyncio.create_task(login())
        try:
            await asyncio.wait_for(login_started.wait(), timeout=5)
            assert not task.done(), "登录密码读取必须等待重置事务释放锁"
            await resetting.commit()
            assert await asyncio.wait_for(task, timeout=10) is None
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(AuthToken).where(AuthToken.user_id == ids[1])) == 0
