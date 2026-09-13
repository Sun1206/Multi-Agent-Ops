import asyncio
import re

import asyncmy

from app.core.config import Settings


IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


def quote_identifier(name: str) -> str:
    if not IDENTIFIER_PATTERN.fullmatch(name):
        raise ValueError("数据库名称只能包含英文字母、数字和下划线")
    return f"`{name}`"


async def create_databases(settings: Settings) -> tuple[str, str]:
    development_name = quote_identifier(settings.mysql_database)
    test_name = quote_identifier(settings.mysql_test_database)
    connection = await asyncmy.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password.get_secret_value(),
        autocommit=True,
    )
    try:
        async with connection.cursor() as cursor:
            for database_name in (development_name, test_name):
                await cursor.execute(
                    "CREATE DATABASE IF NOT EXISTS "
                    f"{database_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
    finally:
        connection.close()
    return settings.mysql_database, settings.mysql_test_database


async def main() -> None:
    settings = Settings(database_mode="test")
    databases = await create_databases(settings)
    print(f"数据库已可用: {databases[0]}, {databases[1]}")


if __name__ == "__main__":
    asyncio.run(main())
