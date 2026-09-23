from aiops.agent_registry import action_definitions


PATH_ACTIONS = (
    ("/alerts", "alert.root_cause"),
    ("/logs/query", "log.query_generate"),
    ("/observability/metrics", "slo.analysis"),
    ("/events/", "change.correlation"),
    ("/workorders/releases", "change.correlation"),
)
KEYWORD_ACTIONS = (
    (("告警", "报警", "根因", "故障"), "alert.root_cause"),
    (("日志", "log", "错误记录"), "log.query_generate"),
    (("指标", "promql", "延迟", "错误率", "slo"), "slo.analysis"),
    (("变更", "发布", "上线", "回滚", "事件"), "change.correlation"),
)


# 优先使用页面上下文，再用保守关键词识别运维 Action。
def recognize_action(content: str, page_context: dict[str, object]) -> str | None:
    path = str(page_context.get("path", "")).casefold()
    for prefix, action in PATH_ACTIONS:
        if path.startswith(prefix):
            return action
    lowered = content.casefold()
    for keywords, action in KEYWORD_ACTIONS:
        if any(keyword in lowered for keyword in keywords):
            return action
    return None


# 按 Action code 读取不可变目录定义的副本。
def action_definition(code: str | None) -> dict[str, object] | None:
    if code is None:
        return None
    return next((item for item in action_definitions() if item["code"] == code), None)


# 工具可见性严格取 Action、Skill、注册状态和用户权限的交集。
def select_tool_names(*, action, skills, registered, permitted) -> tuple[str, ...]:
    if action is None:
        return ()
    action_tools = set(action.get("allowed_tools", ()))
    skill_tools: set[str] = set()
    for skill in skills:
        skill_tools.update(skill.get("builtin_tools", ()))
        skill_tools.update(skill.get("recommended_tools", ()))
    return tuple(sorted(action_tools & skill_tools & set(registered) & set(permitted)))
