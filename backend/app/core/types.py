"""统一数据库时间存储和接口输出使用的 UTC 时区。"""

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


def ensure_utc(value: datetime) -> datetime:
    """将无时区数据库值视为 UTC，并把其他时区转换为 UTC。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class UTCDateTime(TypeDecorator[datetime]):
    """以无时区 UTC 写入 MySQL，并在读取后恢复 UTC 时区。"""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """写库前统一为 UTC，避免 MySQL 丢弃时区造成时间偏移。"""
        return None if value is None else ensure_utc(value).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """为驱动返回的时间补回 UTC，保持接口时间格式一致。"""
        return None if value is None else ensure_utc(value)
