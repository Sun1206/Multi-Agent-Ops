import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ConfigDict


SENSITIVE_KEY_PARTS = (
    "access_key",
    "api_key",
    "authorization",
    "cookie",
    "credential",
    "database_url",
    "dsn",
    "password",
    "private_key",
    "secret",
    "token",
)
MAX_DEPTH = 12
MAX_ITEMS = 200
MAX_STRING_BYTES = 8192
MAX_OUTPUT_BYTES = 131072


# 所有工具参数拒绝模型生成的未知字段，避免静默扩大查询范围。
class StrictToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


# 工具上下文只携带运行所需标识，不携带密钥或数据库连接信息。
@dataclass(frozen=True)
class ToolContext:
    factory: object
    actor_id: int
    session_id: int
    message_id: int
    call_id: str


ToolExecutor = Callable[[ToolContext, StrictToolArguments], Awaitable[dict[str, object]]]


# 工具定义统一描述参数、权限、风险和执行入口。
@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    arguments_model: type[StrictToolArguments]
    required_permissions: tuple[str, ...]
    risk_level: str
    executor: ToolExecutor

    # 生成 OpenAI-compatible function tool schema。
    def openai_schema(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.arguments_model.model_json_schema(),
            },
        }


# 构建注册表时拒绝重复名称，防止后注册工具覆盖安全定义。
def build_tool_registry(definitions: tuple[ToolDefinition, ...]) -> dict[str, ToolDefinition]:
    registry: dict[str, ToolDefinition] = {}
    for definition in definitions:
        if definition.name in registry:
            raise ValueError(f"工具名称重复：{definition.name}")
        registry[definition.name] = definition
    return registry


def _is_sensitive_key(key: str) -> bool:
    lowered = key.casefold()
    return any(fragment in lowered for fragment in SENSITIVE_KEY_PARTS)


def _trim_text(value: str) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= MAX_STRING_BYTES:
        return value
    return encoded[: MAX_STRING_BYTES - 3].decode("utf-8", errors="ignore") + "..."


def _sanitize(value: Any, depth: int) -> Any:
    if depth > MAX_DEPTH:
        return "[truncated]"
    if isinstance(value, dict):
        return {
            _trim_text(str(key)): "***" if _is_sensitive_key(str(key)) else _sanitize(item, depth + 1)
            for key, item in list(value.items())[:MAX_ITEMS]
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize(item, depth + 1) for item in list(value)[:MAX_ITEMS]]
    if isinstance(value, str):
        return _trim_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _trim_text(str(value))


def _largest_list(value: object) -> list | None:
    candidates: list[list] = []
    if isinstance(value, list):
        candidates.append(value)
        for item in value:
            nested = _largest_list(item)
            if nested is not None:
                candidates.append(nested)
    elif isinstance(value, dict):
        for item in value.values():
            nested = _largest_list(item)
            if nested is not None:
                candidates.append(nested)
    return max(candidates, key=len, default=None)


# 对工具结果递归脱敏并施加深度、条数、字符串和整体字节限制。
def sanitize_tool_output(value: object) -> dict[str, object]:
    output = _sanitize(value, 0)
    if not isinstance(output, dict):
        output = {"result": output}
    truncated = False
    while len(json.dumps(output, ensure_ascii=False, default=str).encode("utf-8")) > MAX_OUTPUT_BYTES:
        largest = _largest_list(output)
        if largest is None or len(largest) <= 1:
            return {"truncated": True, "summary": "工具结果超过安全输出上限。"}
        del largest[max(1, len(largest) // 2) :]
        truncated = True
    if truncated:
        output["truncated"] = True
    return output


# 审计只记录聚合信息，不保存原始查询结果。
def tool_output_summary(output: dict[str, object]) -> dict[str, object]:
    rows = output.get("results", output.get("result", []))
    count = output.get("count", len(rows) if isinstance(rows, list) else 0)
    return {
        "result": "success",
        "result_count": count if isinstance(count, int) and count >= 0 else 0,
        "truncated": bool(output.get("truncated", False)),
        "output_bytes": len(json.dumps(output, ensure_ascii=False, default=str).encode("utf-8")),
    }
