# 显式填充智能体配置目录，不重置管理员或覆盖已有配置。

import asyncio

from aidevops.config import get_settings
from aidevops.database import create_engine, create_session_factory
from aiops.services.agent_config import bootstrap_agent_catalog


async def main() -> None:
    engine = create_engine(get_settings())
    try:
        async with create_session_factory(engine)() as session:
            try:
                await bootstrap_agent_catalog(session)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        print('智能体配置目录已补齐；未修改已有内容或管理员密码。')
    finally:
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
