import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator


ProviderName = Literal["loki", "elk", "sls"]
ELK_SECRET_FIELDS = ("password", "api_key", "bearer_token")
SLS_SECRET_FIELDS = ("access_key_id", "access_key_secret")


def parse_elk_index_pattern(value: str) -> tuple[list[str], list[str]]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("ELK 索引范围不能为空。")
    included = []
    excluded = []
    for raw in value.split(","):
        selector = raw.strip()
        negative = selector.startswith("-")
        pattern = selector[1:] if negative else selector
        if not pattern or pattern == "_all" or ":" in pattern or not re.fullmatch(r"[a-z0-9._-][a-z0-9._*-]*", pattern):
            raise ValueError("ELK 索引范围包含不支持的选择器。")
        if not negative and (pattern.startswith("*") or not any(character.isalnum() for character in pattern.replace("*", ""))):
            raise ValueError("ELK 索引范围不能包含无界通配符。")
        (excluded if negative else included).append(pattern)
    if not included:
        raise ValueError("ELK 索引范围至少需要一个包含规则。")
    return included, excluded


def depth(value, level=0):
    if isinstance(value, dict):
        return max((depth(item, level + 1) for item in value.values()), default=level)
    if isinstance(value, list):
        return max((depth(item, level + 1) for item in value), default=level)
    return level


def clean_config(value):
    if not isinstance(value, dict) or depth(value) > 20 or len(json.dumps(value, ensure_ascii=False).encode()) > 65536:
        raise ValueError("日志数据源配置无效或超过限制。")
    return value


class LogDataSourceWrite(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=1, max_length=128)
    provider: ProviderName
    description: str = Field(default="", max_length=255)
    config: dict[str, Any]
    is_enabled: StrictBool = True
    is_default: StrictBool = False

    @field_validator("name")
    @classmethod
    def strip_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("日志数据源名称不能为空。")
        return value

    @field_validator("description")
    @classmethod
    def strip_description(cls, value):
        return value.strip()

    @field_validator("config")
    @classmethod
    def validate_config(cls, value):
        return clean_config(value)

    @model_validator(mode="after")
    def validate_provider_config(self):
        required = {"loki": ("endpoint",), "elk": ("endpoint", "index_pattern"), "sls": ("endpoint", "project", "logstore")}[self.provider]
        if any(not isinstance(self.config.get(key), str) or not self.config[key].strip() for key in required):
            raise ValueError("日志数据源缺少必要连接配置。")
        if self.provider == "elk":
            pattern = self.config.get("index_pattern", "").strip()
            parse_elk_index_pattern(pattern)
            auth = self.config.get("auth_type", "none")
            if auth not in {"none", "basic", "api_key", "bearer"}:
                raise ValueError("ELK 认证方式无效。")
            if any(key in self.config and not isinstance(self.config[key], str) for key in ELK_SECRET_FIELDS):
                raise ValueError("ELK 认证凭据必须是字符串。")
            required_secret = {"basic": "password", "api_key": "api_key", "bearer": "bearer_token"}.get(auth)
            if required_secret and required_secret not in self.config:
                raise ValueError("ELK 缺少认证凭据。")
        if self.provider == "sls":
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", self.config.get("project", "")):
                raise ValueError("SLS Project 名称无效。")
            if any(key in self.config and not isinstance(self.config[key], str) for key in SLS_SECRET_FIELDS):
                raise ValueError("SLS AccessKey 凭据必须是字符串。")
            if not all(key in self.config for key in SLS_SECRET_FIELDS):
                raise ValueError("SLS 缺少 AccessKey 凭据。")
        return self


class LogCatalogRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    datasource_id: int = Field(gt=0)
    action: Literal["labels", "label_values", "sources"]
    label: str = Field(default="", max_length=128, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    index_pattern: str = Field(default="", max_length=512)

    @model_validator(mode="after")
    def validate_catalog(self):
        if self.action == "label_values" and not self.label:
            raise ValueError("读取标签值必须指定标签名。")
        return self


class LogQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    datasource_id: int = Field(gt=0)
    provider: ProviderName
    query: str = Field(min_length=1, max_length=8192)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    limit: int = Field(default=200, ge=1, le=2000)
    source: str = Field(default="", max_length=512)
    index_pattern: str = Field(default="", max_length=512)
    time_field: str = Field(default="@timestamp", max_length=128)
    message_fields: str = Field(default="message,log,msg", max_length=512)
    logstore: str = Field(default="", max_length=128)
    topic: str = Field(default="", max_length=128)

    @field_validator("query")
    @classmethod
    def strip_query(cls, value):
        value = value.strip()
        if not value or any(ord(char) == 0 for char in value):
            raise ValueError("日志查询语句无效。")
        return value

    @model_validator(mode="after")
    def validate_range(self):
        if self.start_ms >= self.end_ms:
            raise ValueError("开始时间必须早于结束时间。")
        if self.end_ms - self.start_ms > 31 * 86_400_000:
            raise ValueError("日志查询范围不能超过 31 天。")
        return self
