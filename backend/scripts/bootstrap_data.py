import asyncio

from aidevops.config import get_settings
from aidevops.database import create_engine, create_session_factory
from rbac.services.accounts import ensure_admin
from ops.modules.services import sync_modules
from rbac.services.authorization import sync_rbac


async def bootstrap_data() -> bool:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            try:
                await sync_rbac(session)
                await sync_modules(session)
                secret = settings.aiops_admin_initial_password
                admin = await ensure_admin(
                    session,
                    secret.get_secret_value() if secret is not None else None,
                )
                await session.commit()
                return admin is not None
            except Exception:
                await session.rollback()
                raise
    finally:
        await engine.dispose()


async def main() -> None:
    admin_configured = await bootstrap_data()
    print("权限与模块已同步。")
    print("admin 已创建或升级。" if admin_configured else "未配置 admin 初始密码，已跳过账号初始化。")


if __name__ == "__main__":
    asyncio.run(main())
