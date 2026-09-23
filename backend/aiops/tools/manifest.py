from aiops.tools.platform import build_registry


PLATFORM_MCP_NAME = "平台只读工具"
PLATFORM_MCP_ENDPOINT = "platform://readonly"
PLATFORM_TOOL_TITLES = {
    "query_alerts": "告警列表查询",
    "get_alert_detail": "告警详情查询",
    "query_metrics": "指标查询",
    "query_logs": "日志查询",
    "query_recent_changes": "最近变更查询",
}


# 从真实运行注册表读取并稳定排序工具名称，避免展示目录维护第二份清单。
def platform_tool_names() -> tuple[str, ...]:
    return tuple(sorted(build_registry()))


# 为 MCP 主列表生成一工具一行的内置目录定义，并校验展示映射未偏离运行注册表。
def platform_server_definitions() -> list[dict[str, object]]:
    registry = build_registry()
    if set(PLATFORM_TOOL_TITLES) != set(registry):
        raise RuntimeError("平台工具展示映射与运行注册表不一致。")
    rows = []
    for tool_name, title in PLATFORM_TOOL_TITLES.items():
        definition = registry[tool_name]
        rows.append(
            {
                "name": title,
                "server_type": "platform_builtin",
                "endpoint_or_command": f"platform://readonly/{tool_name}",
                "description": definition.description,
                "tool_whitelist": [tool_name],
                "is_builtin": True,
                "is_enabled": True,
            }
        )
    return rows


# 将 OpenAI-compatible 工具定义转换为现有 MCP 工具弹窗使用的字段结构。
def platform_tool_declarations() -> list[dict[str, object]]:
    rows = []
    for name, definition in sorted(build_registry().items()):
        function = definition.openai_schema()["function"]
        rows.append(
            {
                "name": name,
                "description": definition.description,
                "inputSchema": function["parameters"],
            }
        )
    return rows


# 生成前端平台 MCP 概览使用的只读能力清单，不包含执行入口或敏感配置。
def platform_manifest() -> dict[str, object]:
    tools = []
    for name, definition in sorted(build_registry().items()):
        tools.append(
            {
                "title": definition.description.rstrip("。"),
                "name": name,
                "permission": ", ".join(definition.required_permissions),
                "available": True,
                "annotations": {"readOnlyHint": True},
            }
        )
    return {"tools": tools, "rate_limit": {"per_minute": 0}}
