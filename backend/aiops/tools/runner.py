import asyncio
from time import perf_counter

from sqlalchemy import select

from aiops.models import (
    AIOpsAgentConfig,
    AIOpsChatMessage,
    AIOpsChatSession,
    AIOpsToolInvocation,
)
from aiops.tools.contracts import (
    ToolContext,
    sanitize_tool_output,
    tool_output_summary,
)
from rbac.models import User
from rbac.selectors.permissions import user_has_permissions


WORKER_TAG = "platform_readonly_tools_v1"
TOOL_TIMEOUT_SECONDS = 30


# 可恢复的工具错误允许模型基于已有证据继续回答。
class ToolExecutionError(Exception):
    pass


# 账号、权限、会话或配置变化属于致命错误，必须终止后续工具调用。
class FatalToolExecutionError(ToolExecutionError):
    pass


# 每次执行前后重新读取账号、会话、消息、配置和权限。
async def _authorize(
    factory, context: ToolContext, permissions: tuple[str, ...]
) -> None:
    async with factory() as database:
        actor = await database.get(User, context.actor_id)
        chat = await database.get(AIOpsChatSession, context.session_id)
        message = await database.get(AIOpsChatMessage, context.message_id)
        config = await database.scalar(
            select(AIOpsAgentConfig).where(AIOpsAgentConfig.name == "default")
        )
        if (
            actor is None
            or not actor.is_active
            or chat is None
            or chat.user_id != context.actor_id
            or message is None
            or message.session_id != chat.id
            or config is None
            or not config.is_enabled
        ):
            raise FatalToolExecutionError("账号、会话或智能助手配置已变化。")
        if not await user_has_permissions(database, actor, permissions):
            raise FatalToolExecutionError("当前账号无权使用该工具。")


# 在执行真实查询前独立提交 pending 调用记录。
async def _create_pending(
    factory,
    context: ToolContext,
    name: str,
    argument_keys: list[str],
) -> int:
    summary = {
        "worker_tag": WORKER_TAG,
        "call_id": context.call_id,
        "argument_keys": argument_keys,
    }
    async with factory() as database:
        row = AIOpsToolInvocation(
            session_id=context.session_id,
            message_id=context.message_id,
            tool_name=name,
            status=AIOpsToolInvocation.STATUS_PENDING,
            request_payload=summary,
            response_summary={},
        )
        database.add(row)
        await database.commit()
        await database.refresh(row)
        return row.id


# 用独立事务把工具调用更新为成功或失败终态。
async def _finish(
    factory,
    identifier: int,
    status: str,
    latency_ms: int,
    summary: dict[str, object],
) -> AIOpsToolInvocation:
    async with factory() as database:
        row = await database.get(
            AIOpsToolInvocation, identifier, with_for_update=True
        )
        if row is None:
            raise FatalToolExecutionError("工具审计记录不存在。")
        row.status = status
        row.latency_ms = max(0, latency_ms)
        row.response_summary = summary
        await database.commit()
        await database.refresh(row)
        return row


# 校验白名单和参数、执行只读工具，并保证审计记录进入终态。
async def run_tool(
    factory,
    *,
    actor_id: int,
    session_id: int,
    message_id: int,
    call_id: str,
    tool_name: str,
    arguments: dict[str, object],
    allowed_names: set[str] | tuple[str, ...],
    registry: dict,
):
    definition = registry.get(tool_name)
    if definition is None or tool_name not in allowed_names:
        raise ToolExecutionError("请求的工具当前不可用。")
    context = ToolContext(factory, actor_id, session_id, message_id, call_id)
    await _authorize(factory, context, definition.required_permissions)
    try:
        parsed = definition.arguments_model.model_validate(arguments)
    except Exception as error:
        raise ToolExecutionError("工具参数不符合要求。") from error
    identifier = await _create_pending(
        factory, context, tool_name, sorted(parsed.model_fields_set)
    )
    started = perf_counter()
    try:
        raw_output = await asyncio.wait_for(
            definition.executor(context, parsed), timeout=TOOL_TIMEOUT_SECONDS
        )
        output = sanitize_tool_output(raw_output)
        await _authorize(factory, context, definition.required_permissions)
        row = await _finish(
            factory,
            identifier,
            AIOpsToolInvocation.STATUS_SUCCESS,
            round((perf_counter() - started) * 1000),
            tool_output_summary(output),
        )
        return row, output
    except asyncio.CancelledError:
        await _finish(
            factory,
            identifier,
            AIOpsToolInvocation.STATUS_FAILED,
            round((perf_counter() - started) * 1000),
            {"result": "failed", "error_code": "cancelled"},
        )
        raise
    except FatalToolExecutionError:
        await _finish(
            factory,
            identifier,
            AIOpsToolInvocation.STATUS_FAILED,
            round((perf_counter() - started) * 1000),
            {"result": "failed", "error_code": "authorization_changed"},
        )
        raise
    except Exception as error:
        error_code = (
            "timeout" if isinstance(error, TimeoutError) else "execution_failed"
        )
        await _finish(
            factory,
            identifier,
            AIOpsToolInvocation.STATUS_FAILED,
            round((perf_counter() - started) * 1000),
            {"result": "failed", "error_code": error_code},
        )
        raise ToolExecutionError(
            "平台只读查询失败，请检查数据源配置或稍后重试。"
        ) from error


# 服务启动或关闭时仅恢复当前运行版本遗留的 pending 工具记录。
async def recover_interrupted_tools(factory) -> None:
    async with factory() as database:
        rows = list(
            (
                await database.scalars(
                    select(AIOpsToolInvocation).where(
                        AIOpsToolInvocation.status
                        == AIOpsToolInvocation.STATUS_PENDING
                    )
                )
            ).all()
        )
        for row in rows:
            payload = row.request_payload if isinstance(row.request_payload, dict) else {}
            if payload.get("worker_tag") == WORKER_TAG:
                row.status = AIOpsToolInvocation.STATUS_FAILED
                row.response_summary = {
                    "result": "failed",
                    "error_code": "worker_restarted",
                }
        await database.commit()
