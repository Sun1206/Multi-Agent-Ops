import asyncio
import codecs
import json
import math
import re
from uuid import uuid4

import httpx

from app.services.mcp_tools import McpError


PROTOCOL_VERSION = '2025-03-26'
MAX_RESPONSE_BYTES = 1024 * 1024


# 严格拒绝NaN、Infinity及浮点溢出，防止非法远端JSON在响应序列化阶段变成500。
def finite_number(raw):
    value = float(raw)
    if not math.isfinite(value):
        raise McpError('MCP响应包含非法JSON数值。')
    return value


# JSON规范不包含NaN或Infinity；遇到这些常量直接作为远端协议失败处理。
def reject_constant(raw):
    raise McpError('MCP响应包含非法JSON常量。')


# JSON和SSE统一使用严格数值解析，避免不同传输分支的校验规则不一致。
def decode_json(raw):
    return json.loads(raw, parse_float=finite_number, parse_constant=reject_constant)


# 只接受本次请求ID对应的合法JSON-RPC结果，不把空响应或error当作握手成功。
def rpc_result(payload, identifier):
    messages = payload if isinstance(payload, list) else [payload]
    matches = [message for message in messages if isinstance(message, dict) and message.get('id') == identifier]
    if not matches:
        return None
    if len(matches) != 1:
        raise McpError('MCP返回重复响应。')
    message = matches[0]
    if message.get('jsonrpc') != '2.0' or 'error' in message or not isinstance(message.get('result'), dict):
        raise McpError('MCP响应协议或结果不合法。')
    return message['result']


# 从未压缩传输读取有界原始字节，避免先透明解压再检查大小。
async def response_chunks(response):
    if response.is_stream_consumed:
        yield response.content
    else:
        async for chunk in response.aiter_raw():
            yield chunk


# 按UTF-8增量解析SSE事件；找到对应响应便停止，不等待服务器关闭长连接。
async def read_result(response, identifier):
    size, buffer, data_lines = 0, '', []
    media_type = response.headers.get('content-type', '').split(';')[0].strip().lower()
    if media_type not in ('application/json', 'text/event-stream'):
        raise McpError('MCP响应媒体类型不受支持。')
    sse = media_type == 'text/event-stream'
    decoder = codecs.getincrementaldecoder('utf-8')()
    raw = bytearray()
    async for chunk in response_chunks(response):
        size += len(chunk)
        if size > MAX_RESPONSE_BYTES:
            raise McpError('MCP响应超过允许大小。')
        if not sse:
            raw.extend(chunk)
            continue
        buffer += decoder.decode(chunk)
        while True:
            match = re.search(r'\r\n|\r|\n', buffer)
            if match is None or (match.group() == '\r' and match.end() == len(buffer)):
                break
            line, buffer = buffer[:match.start()], buffer[match.end():]
            if line.startswith('data:'):
                data_lines.append(line[5:].lstrip(' '))
            elif not line and data_lines:
                result = rpc_result(decode_json('\n'.join(data_lines)), identifier)
                data_lines = []
                if result is not None:
                    return result
    if sse:
        buffer += decoder.decode(b'', final=True)
        if buffer.startswith('data:'):
            data_lines.append(buffer[5:].strip())
        result = rpc_result(decode_json('\n'.join(data_lines)), identifier) if data_lines else None
    else:
        result = rpc_result(decode_json(raw.decode('utf-8')), identifier)
    if result is None:
        raise McpError('MCP未返回匹配的请求结果。')
    return result


# 生命周期只包含initialize、initialized通知、tools/list及session清理；没有工具执行方法。
class HttpMcpSession:
    # 保存单次诊断的客户端、目标和总截止时间；会话标识仅用于内部后续请求。
    def __init__(self, client, target, auth_headers, deadline):
        self.client, self.target, self.auth_headers, self.deadline = client, target, auth_headers, deadline
        self.session_id = ''
        self.request_count = 0

    # 每一条请求都扣除同一个总预算，分页不会重新获得完整超时窗口。
    def remaining(self):
        budget = self.deadline - asyncio.get_running_loop().time()
        if budget <= 0:
            raise McpError('MCP请求超时。')
        return budget

    # 服务端固定协议头优先于鉴权头；只有握手获得合法标识后才携带session。
    def headers(self):
        values = {**self.auth_headers, 'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json', 'Accept-Encoding': 'identity', 'MCP-Protocol-Version': PROTOCOL_VERSION}
        if self.session_id:
            values['Mcp-Session-Id'] = self.session_id
        return values

    # 流式发送RPC并校验状态、编码及会话；通知只接受202，普通请求必须解析结果。
    async def post(self, message):
        self.request_count += 1
        async with self.client.stream('POST', self.target.url, headers=self.headers(), json=message, timeout=self.remaining()) as response:
            if not 200 <= response.status_code < 300:
                raise McpError('MCP服务请求失败。')
            if response.headers.get('content-encoding', 'identity').strip().lower() != 'identity':
                raise McpError('MCP响应编码不受支持。')
            if 'id' not in message:
                if response.status_code != 202:
                    raise McpError('MCP初始化通知未被正确接受。')
                return None
            if message['method'] == 'initialize':
                session_id = response.headers.get('mcp-session-id', '')
                if session_id and (len(session_id) > 256 or any(not 0x21 <= ord(char) <= 0x7e for char in session_id)):
                    raise McpError('MCP会话标识格式不合法。')
                self.session_id = session_id
            return await read_result(response, message['id'])

    # 独立生成请求ID，以严格匹配结果，避免混用远端通知或其他请求的响应。
    async def request(self, method, params):
        return await self.post({'jsonrpc': '2.0', 'id': uuid4().hex, 'method': method, 'params': params})

    # 先验证旧项目固定协议与服务器信息，再发初始化完成通知，不尝试协议降级。
    async def initialize(self):
        result = await self.request('initialize', {'protocolVersion': PROTOCOL_VERSION, 'capabilities': {}, 'clientInfo': {'name': 'aiops-http-diagnostics', 'version': '1.0.0'}})
        info = result.get('serverInfo')
        if result.get('protocolVersion') != PROTOCOL_VERSION or not isinstance(result.get('capabilities'), dict) or not isinstance(info, dict) or any(not isinstance(info.get(field), str) or not info[field].strip() or len(info[field]) > 255 for field in ('name', 'version')):
            raise McpError('MCP握手信息缺失或协议版本不受支持。')
        await self.post({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        return result

    # 仅发现声明；最多十页和二百条，重复cursor失败，绝不调用tools/call。
    async def list_tools(self):
        rows, cursors, cursor = [], set(), None
        for _ in range(10):
            result = await self.request('tools/list', {'cursor': cursor} if cursor else {})
            tools = result.get('tools')
            if not isinstance(tools, list):
                raise McpError('MCP工具目录格式不合法。')
            rows.extend(tools)
            if len(rows) > 200:
                raise McpError('MCP工具数量超过允许上限。')
            cursor = result.get('nextCursor')
            if cursor is None:
                return rows
            if not isinstance(cursor, str) or not cursor or len(cursor) > 1024 or cursor in cursors:
                raise McpError('MCP工具目录分页标识不合法或重复。')
            cursors.add(cursor)
        raise McpError('MCP工具目录分页超过允许上限。')

    # 有有效session且预算剩余时尽力DELETE；不重试，清理失败不覆盖主诊断结果。
    async def close(self):
        if not self.session_id or self.deadline <= asyncio.get_running_loop().time():
            return
        self.request_count += 1
        try:
            async with self.client.stream('DELETE', self.target.url, headers=self.headers(), timeout=min(self.remaining(), 2)):
                pass
        except (httpx.HTTPError, OSError, McpError):
            pass
