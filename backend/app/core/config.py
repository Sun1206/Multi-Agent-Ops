from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_database: str = "ai_ops"
    mysql_test_database: str = "ai_ops_test"
    mysql_user: str
    mysql_password: SecretStr
    database_mode: Literal["development", "test"] = Field(
        default="development",
        validation_alias=AliasChoices("AIOPS_DATABASE_MODE", "database_mode"),
    )
    aiops_admin_initial_password: SecretStr | None = None
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]

    @model_validator(mode="after")
    def validate_test_database(self) -> "Settings":
        if self.database_mode == "test":
            if self.mysql_test_database == self.mysql_database:
                raise ValueError("测试数据库不能与开发数据库相同")
            if not self.mysql_test_database.endswith("_test"):
                raise ValueError("MYSQL_TEST_DATABASE 必须以 _test 结尾")
        return self

    @property
    def active_database(self) -> str:
        if self.database_mode == "test":
            return self.mysql_test_database
        return self.mysql_database

    @property
    def database_url(self) -> URL:
        return URL.create(
            "mysql+asyncmy",
            username=self.mysql_user,
            password=self.mysql_password.get_secret_value(),
            host=self.mysql_host,
            port=self.mysql_port,
            database=self.active_database,
            query={"charset": "utf8mb4"},
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
