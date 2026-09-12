import pytest
from pydantic import ValidationError

from app.core.config import Settings


def make_settings(**overrides: object) -> Settings:
    """构造不依赖本地 `.env` 的测试配置。"""
    values = {
        "mysql_host": "127.0.0.1",
        "mysql_port": 3306,
        "mysql_database": "ai_ops",
        "mysql_test_database": "ai_ops_test",
        "mysql_user": "ai_ops",
        "mysql_password": "p@ss:/word",
        "database_mode": "test",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_test_database_must_be_isolated() -> None:
    with pytest.raises(ValidationError, match="测试数据库不能与开发数据库相同"):
        make_settings(mysql_test_database="ai_ops")


def test_test_database_must_end_with_test() -> None:
    with pytest.raises(ValidationError, match="必须以 _test 结尾"):
        make_settings(mysql_test_database="ai_ops_ci")


def test_database_url_percent_encodes_password() -> None:
    url = make_settings().database_url.render_as_string(hide_password=False)
    assert "p%40ss%3A%2Fword" in url
    assert url.endswith("/ai_ops_test?charset=utf8mb4")


def test_aiops_database_mode_environment_variable_is_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIOPS_DATABASE_MODE", "test")
    settings = Settings(_env_file=None, mysql_user="offline", mysql_password="offline")
    assert settings.active_database == "ai_ops_test"
