# 校验指标数据源、PromQL 查询和指标名补全请求的前端兼容输入。

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator


ROUND_TRIP_FIELDS = {"id", "created_at", "updated_at", "provider_display"}
PROTECTED_HEADERS = {
    "host",
    "content-length",
    "transfer-encoding",
    "connection",
    "accept",
    "accept-encoding",
    "content-type",
    "origin",
    "proxy-authorization",
    "proxy-connection",
    "upgrade",
    "trailer",
    "te",
}


# 计算 JSON 嵌套深度，提前拒绝可能导致递归处理失控的配置。
def json_depth(value: object, depth: int = 0) -> int:
    if isinstance(value, dict):
        return max((json_depth(item, depth + 1) for item in value.values()), default=depth)
    if isinstance(value, list):
        return max((json_depth(item, depth + 1) for item in value), default=depth)
    return depth


# 校验页面可编辑配置的总体大小、URL 和自定义请求头安全边界。
def validate_config(value: dict[str, Any]) -> dict[str, Any]:
    if json_depth(value) > 20:
        raise ValueError("指标数据源配置嵌套过深。")
    if len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > 65_536:
        raise ValueError("指标数据源配置不能超过 64 KiB。")
    if "prometheus" in value:
        raise ValueError("不支持嵌套 prometheus 配置，请使用页面兼容的 dotted 字段。")
    for url in (value.get("query_url"), value.get("prometheus.addr")):
        if url is not None and (not isinstance(url, str) or len(url) > 2048):
            raise ValueError("指标查询地址格式无效或长度超限。")
    for headers in (value.get("headers"), value.get("prometheus.headers")):
        if headers is None:
            continue
        if not isinstance(headers, dict) or len(headers) > 64:
            raise ValueError("自定义请求头必须是最多包含 64 项的对象。")
        for name, header_value in headers.items():
            lowered = str(name).lower()
            if not isinstance(name, str) or not name or len(name) > 128:
                raise ValueError("自定义请求头名称格式无效。")
            if lowered in PROTECTED_HEADERS or lowered.startswith("proxy-"):
                raise ValueError("自定义请求头不能覆盖连接层保护字段。")
            if not isinstance(header_value, str) or len(header_value) > 8192:
                raise ValueError("自定义请求头值必须是长度不超过 8192 的字符串。")
    auth_type = value.get("auth_type")
    if auth_type is not None and (not isinstance(auth_type, str) or auth_type not in {"none", "basic", "bearer"}):
        raise ValueError("auth_type 仅支持 none、basic 或 bearer。")
    if "tls_skip_verify" in value and type(value["tls_skip_verify"]) is not bool:
        raise ValueError("tls_skip_verify 必须是布尔值。")
    for key in ("timeout", "prometheus.timeout"):
        if key not in value:
            continue
        timeout = value[key]
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 1 <= timeout <= 30:
            raise ValueError("指标数据源超时必须在 1 到 30 秒之间。")
    return value


# 为创建和完整更新定义数据库已有字段，并忽略页面安全往返展示字段。
class MetricDataSourceCreate(BaseModel):

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    provider: Literal["prometheus"] = "prometheus"
    description: str = Field(default="", max_length=255)
    environment: str = Field(default="", max_length=32)
    cluster_name: str = Field(default="", max_length=128)
    tsdb_type: Literal["prometheus"] = "prometheus"
    config: dict[str, Any] = Field(default_factory=dict)
    is_enabled: StrictBool = True
    is_default: StrictBool = False

    # 只移除接口自身曾返回的只读字段，真正未知字段仍由 extra=forbid 拒绝。
    @model_validator(mode="before")
    @classmethod
    def remove_round_trip_fields(cls, value):
        if isinstance(value, dict):
            return {key: item for key, item in value.items() if key not in ROUND_TRIP_FIELDS}
        return value

    # 名称去除首尾空白后仍必须非空。
    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("数据源名称不能为空。")
        return value

    # 环境、集群和描述只清理首尾空白，不改变正文。
    @field_validator("description", "environment", "cluster_name")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()

    # 配置边界在进入加密和数据库服务前统一验证。
    @field_validator("config")
    @classmethod
    def validate_metric_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_config(value)


# 为局部更新定义与创建相同的字段类型，遗漏字段由服务层保留当前值。
class MetricDataSourcePatch(BaseModel):

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    provider: Literal["prometheus"] | None = None
    description: str | None = Field(default=None, max_length=255)
    environment: str | None = Field(default=None, max_length=32)
    cluster_name: str | None = Field(default=None, max_length=128)
    tsdb_type: Literal["prometheus"] | None = None
    config: dict[str, Any] | None = None
    is_enabled: StrictBool | None = None
    is_default: StrictBool | None = None

    # 可选表示可以省略，不表示数据库非空字段能够显式写入 null。
    @model_validator(mode="after")
    def reject_explicit_null(self):
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} 不能为 null。")
        return self

    # PATCH 也兼容页面整行回传的只读展示字段。
    @model_validator(mode="before")
    @classmethod
    def remove_round_trip_fields(cls, value):
        if isinstance(value, dict):
            return {key: item for key, item in value.items() if key not in ROUND_TRIP_FIELDS}
        return value

    # 可选名称一旦提交就必须是非空正式名称。
    @field_validator("name")
    @classmethod
    def normalize_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("数据源名称不能为空。")
        return value

    # 可选文本只在显式提交时清理首尾空白。
    @field_validator("description", "environment", "cluster_name")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    # PATCH 中显式提交的配置遵守与创建相同的边界。
    @field_validator("config")
    @classmethod
    def validate_optional_config(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_config(value) if value is not None else None


# 校验连接测试使用的安全即时查询语句。
class MetricConnectionTest(BaseModel):

    model_config = ConfigDict(extra="forbid")

    query: str = Field(default="up", min_length=1, max_length=2000)

    # 查询去除首尾空白，空白字符串不能绕过最小长度。
    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("查询语句不能为空。")
        return value


# 校验指标名补全参数及旧页面使用的参数别名。
class MetricSeriesNames(BaseModel):

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    metric_datasource_id: int | None = Field(default=None, validation_alias=AliasChoices("metric_datasource_id", "datasource_id"), gt=0)
    environment: str = Field(default="", max_length=32)
    q: str = Field(default="", validation_alias=AliasChoices("q", "keyword"), max_length=256)
    limit: int = Field(default=80, ge=1, le=200)

    # 空字符串表示页面尚未选中数据源，归一为空后由服务层选择默认项。
    @field_validator("metric_datasource_id", mode="before")
    @classmethod
    def normalize_blank_identifier(cls, value):
        return None if value == "" else value


# 校验 PromQL 即时或区间查询，并兼容旧接口字段名。
class MetricQuery(BaseModel):

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    promql: str = Field(validation_alias=AliasChoices("promql", "query"), min_length=1, max_length=2000)
    metric_datasource_id: int | None = Field(default=None, validation_alias=AliasChoices("metric_datasource_id", "datasource_id"), gt=0)
    environment: str = Field(default="", max_length=32)
    range_query: StrictBool = Field(default=True, validation_alias=AliasChoices("range_query", "range"))
    start: datetime | None = Field(default=None, validation_alias=AliasChoices("start", "start_time"))
    end: datetime | None = Field(default=None, validation_alias=AliasChoices("end", "end_time"))
    step: Annotated[int, Field(strict=True, ge=1, le=86_400)] = 30

    # 空字符串表示页面尚未选中数据源，归一为空后由服务层选择默认项。
    @field_validator("metric_datasource_id", mode="before")
    @classmethod
    def normalize_blank_identifier(cls, value):
        return None if value == "" else value

    # query_type 是旧调用方的枚举别名，只在正式布尔字段未出现时转换。
    @model_validator(mode="before")
    @classmethod
    def normalize_query_type(cls, value):
        if not isinstance(value, dict):
            return value
        output = dict(value)
        if "query_type" in output:
            query_type = output.pop("query_type")
            if not isinstance(query_type, str) or query_type not in {"range", "instant"}:
                raise ValueError("query_type 仅支持 range 或 instant。")
            if "range_query" not in output and "range" not in output:
                output["range_query"] = query_type == "range"
        return output

    # PromQL 去除首尾空白，审计只会记录规范化后的长度。
    @field_validator("promql")
    @classmethod
    def normalize_promql(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("PromQL 不能为空。")
        return value

    # 时间统一转换为 UTC，避免下游比较混用本地和无时区时间。
    @field_validator("start", "end")
    @classmethod
    def normalize_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    # 同时提交时间时校验顺序和 31 天上限；缺省值由同一次服务时钟生成。
    @model_validator(mode="after")
    def validate_time_range(self):
        if (self.start is None) != (self.end is None):
            raise ValueError("开始和结束时间必须同时提交。")
        if self.start is not None and self.end is not None:
            if self.start >= self.end:
                raise ValueError("开始时间必须早于结束时间。")
            if self.end - self.start > timedelta(days=31):
                raise ValueError("查询区间不能超过 31 天。")
        return self
