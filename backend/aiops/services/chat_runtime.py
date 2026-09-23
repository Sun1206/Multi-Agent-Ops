import asyncio
import json
from dataclasses import dataclass
from time import perf_counter

from aidevops import restricted_http as model_client
from aiops.tools.runner import (
    FatalToolExecutionError,
    ToolExecutionError,
    run_tool,
)


MAX_TOOL_ROUNDS = 4
SAFE_TOOL_FAILURE = {
    "error_code": "tool_failed",
    "message": "工具查询失败或无权访问。",
}


# 对话运行错误携带已发生的安全模型调用摘要，便于终态事务落库。
class ChatRuntimeError(Exception):
    def __init__(
        self,
        message: str,
        model_invocations: list[dict[str, object]],
        tool_calls: list[dict[str, object]],
    ):
        super().__init__(message)
        self.model_invocations = model_invocations
        self.tool_calls = tool_calls


# 返回最终文本以及本次对话内产生的模型和工具调用摘要。
@dataclass(frozen=True)
class ChatRuntimeResult:
    content: str
    model_invocations: list[dict[str, object]]
    tool_calls: list[dict[str, object]]


def _request_summary(messages: list[dict[str, object]], round_index: int, tool_count: int):
    return {
        "message_count": len(messages),
        "content_length": sum(
            len(message.get("content", ""))
            for message in messages
            if isinstance(message.get("content"), str)
        ),
        "round": round_index,
        "tool_count": tool_count,
    }


# 在固定轮次内交替请求模型和执行白名单只读工具。
async def run_chat(
    *,
    factory,
    actor_id: int,
    session_id: int,
    message_id: int,
    username: str,
    provider: dict[str, object],
    target,
    key: str,
    payload: dict[str, object],
    allowed_names: set[str] | tuple[str, ...],
    registry: dict,
    tool_authorizer=None,
    invocation_sink: list[dict[str, object]] | None = None,
    trace_sink: list[dict[str, object]] | None = None,
) -> ChatRuntimeResult:
    messages = list(payload["messages"])
    schemas = [registry[name].openai_schema() for name in sorted(allowed_names)]
    invocations = invocation_sink if invocation_sink is not None else []
    traces = trace_sink if trace_sink is not None else []
    for round_index in range(1, MAX_TOOL_ROUNDS + 1):
        request_payload = {**payload, "messages": messages}
        if schemas:
            request_payload.update(tools=schemas, tool_choice="auto")
        started = perf_counter()
        result = None
        parsed = None
        status = "failed"
        termination = "failure"
        failure = None
        try:
            result = await model_client.request_completion(
                target, key, request_payload, provider["timeout_seconds"]
            )
            parsed = model_client.parse_completion_choice(result)
            status = "success"
            termination = "tool_calls" if parsed.tool_calls else "completed"
        except asyncio.CancelledError:
            termination = "cancelled"
            raise
        except Exception as error:
            failure = error
        finally:
            invocations.append(
                {
                    "provider": provider,
                    "session_id": session_id,
                    "message_id": message_id,
                    "username": username,
                    "latency_ms": round((perf_counter() - started) * 1000),
                    "result": result,
                    "status": status,
                    "termination": termination,
                    "request_summary": _request_summary(
                        messages, round_index, len(schemas)
                    ),
                }
            )
        if failure is not None:
            raise ChatRuntimeError(
                "模型不可用或响应格式无效。", invocations, traces
            ) from failure
        if parsed.content is not None:
            return ChatRuntimeResult(
                parsed.content.replace(key, "***"), invocations, traces
            )
        messages.append(parsed.assistant_message)
        for call in parsed.tool_calls:
            try:
                if tool_authorizer is not None:
                    await tool_authorizer(call.name)
                _, output = await run_tool(
                    factory,
                    actor_id=actor_id,
                    session_id=session_id,
                    message_id=message_id,
                    call_id=call.identifier,
                    tool_name=call.name,
                    arguments=call.arguments,
                    allowed_names=allowed_names,
                    registry=registry,
                )
                call_status = "success"
                tool_content = output
            except FatalToolExecutionError:
                raise
            except ToolExecutionError:
                call_status = "failed"
                tool_content = SAFE_TOOL_FAILURE
            traces.append(
                {"id": call.identifier, "name": call.name, "status": call_status}
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.identifier,
                    "name": call.name,
                    "content": json.dumps(
                        tool_content, ensure_ascii=False, default=str
                    ),
                }
            )
    return ChatRuntimeResult(
        "已达到平台查询轮次上限，当前证据不足，请缩小问题范围后重试。",
        invocations,
        traces,
    )
