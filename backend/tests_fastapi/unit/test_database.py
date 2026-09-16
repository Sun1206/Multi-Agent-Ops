import pytest
from pydantic import ValidationError

from aidevops.config import Settings
from aidevops.database import create_engine, create_session_factory


def make_settings(**overrides: object) -> Settings:
    """构造隔离的数据库层测试配置。"""
    values = {
        "mysql_host": "127.0.0.1",
        "mysql_port": 3306,
        "mysql_database": "ai_ops",
        "mysql_test_database": "ai_ops_test",
        "mysql_user": "ai_ops",
        "mysql_password": "local-only",
        "database_mode": "test",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_engine_and_session_factory_use_asyncmy() -> None:
    engine = create_engine(make_settings())
    factory = create_session_factory(engine)
    assert engine.url.drivername == "mysql+asyncmy"
    assert engine.url.database == "ai_ops_test"
    assert factory.class_.__name__ == "AsyncSession"


def test_engine_rejects_unsafe_test_database() -> None:
    with pytest.raises(ValidationError):
        create_engine(make_settings(mysql_test_database="production"))
