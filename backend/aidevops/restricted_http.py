import asyncio
import ipaddress
import json
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from httpcore._backends.auto import AutoBackend


MAX_RESPONSE_BYTES = 1024 ** 2


class ModelRequestError(ValueError):
    pass


class ModelAdmissionError(ModelRequestError):
    pass


@dataclass(frozen=True)
class ModelTarget:
    url: str
    host: str
    port: int
    internal_allowed: bool


def validate_origin(base_url: str, allowed_origins: list[str]) -> ModelTarget:
    parsed = urlsplit(base_url.strip())
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise ValueError('模型地址格式不合法。')
    try:
        host = parsed.hostname.encode('idna').decode('ascii').lower()
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    except (ValueError, UnicodeError):
        raise ValueError('模型地址格式不合法。') from None
    if not (1 <= port <= 65535) or '%' in host or any(ord(char) < 33 for char in base_url):
        raise ValueError('模型地址格式不合法。')
    permitted = False
    for raw in allowed_origins:
        entry = urlsplit(raw)
        if entry.scheme not in ('http', 'https') or not entry.hostname or entry.username is not None or entry.password is not None or entry.query or entry.fragment or entry.path not in ('', '/') or '*' in raw:
            raise ValueError('服务端模型地址准入配置不合法。')
        entry_host = entry.hostname.encode('idna').decode('ascii').lower()
        entry_port = entry.port or (443 if entry.scheme == 'https' else 80)
        permitted |= (entry.scheme, entry_host, entry_port) == (parsed.scheme, host, port)
    if not permitted and (parsed.scheme != 'https' or port != 443):
        raise ValueError('此模型地址未获服务端授权。')
    try:
        validate_addresses([host], permitted)
    except ValueError:
        # Domain names are validated after resolution, literals must fail immediately.
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if host.lower() == 'localhost' and not permitted:
                raise ValueError('此模型地址未获服务端授权。') from None
        else:
            raise
    authority = '[' + host + ']' if ':' in host else host
    url = f'{parsed.scheme}://{authority}:{port}' + parsed.path.rstrip('/')
    return ModelTarget(url, host, port, permitted)


def validate_addresses(addresses: list[str], internal_allowed: bool) -> list[str]:
    if not addresses:
        raise ValueError('模型地址未能解析。')
    result = []
    for raw in addresses:
        address = ipaddress.ip_address(raw)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        if address.is_link_local or address.is_multicast or address.is_unspecified or (address.is_reserved and not address.is_loopback) or (isinstance(address, ipaddress.IPv6Address) and (address.sixtofour or address.teredo)):
            raise ValueError('模型地址禁止访问。')
        if not address.is_global and not (internal_allowed and (address.is_private or address.is_loopback)):
            raise ValueError('此模型地址未获服务端授权。')
        if raw not in result:
            result.append(raw)
    return result


async def resolve_addresses(target: ModelTarget) -> list[str]:
    rows = await asyncio.get_running_loop().getaddrinfo(target.host, target.port, type=socket.SOCK_STREAM)
    return validate_addresses([row[4][0] for row in rows], target.internal_allowed)


class PinnedBackend(AutoBackend):
    def __init__(self, host: str, port: int, address: str):
        self.host, self.port, self.address = host, port, address

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if (host, port) != (self.host, self.port):
            raise ValueError('模型连接目标与准入地址不一致。')
        return await super().connect_tcp(self.address, port, timeout=timeout, local_address=local_address, socket_options=socket_options)


# 对目录和探测使用同一受限传输；地址固定后才发送凭据，响应按上限读取。
async def request_json(target: ModelTarget, api_key: str, method: str, suffix: str, payload: dict | None, timeout_seconds: float, *, transport: httpx.AsyncBaseTransport | None = None, pinned_addresses: list[str] | None = None):
    if not api_key or any(ord(char) < 32 or ord(char) == 127 for char in api_key):
        raise ModelRequestError('模型凭据不可用。')
    budget = min(float(timeout_seconds), 90.0)
    if budget <= 0:
        raise ModelRequestError('模型请求超时设置不合法。')
    try:
        async with asyncio.timeout(budget):
            if transport is None:
                try:
                    addresses = validate_addresses(pinned_addresses, target.internal_allowed) if pinned_addresses is not None else await resolve_addresses(target)
                except (ValueError, OSError):
                    raise ModelAdmissionError('模型地址未通过服务端准入检查。') from None
                transport = httpx.AsyncHTTPTransport(verify=True, trust_env=False, retries=0)
                # Installed HTTPX/HTTPCore contract is explicitly tested; never fall back to unpinned DNS.
                if not hasattr(transport, '_pool') or not hasattr(transport._pool, '_network_backend'):
                    await transport.aclose()
                    raise ModelRequestError('模型网络客户端版本不兼容。')
                transport._pool._network_backend = PinnedBackend(target.host, target.port, addresses[0])
            async with httpx.AsyncClient(transport=transport, trust_env=False, follow_redirects=False, timeout=budget) as client:
                async with client.stream(method, target.url + suffix, headers={'Authorization': 'Bearer ' + api_key, 'Accept': 'application/json', 'Accept-Encoding': 'identity'}, json=payload) as response:
                    if not 200 <= response.status_code < 300:
                        raise ModelRequestError('模型服务请求失败，请检查服务状态或配置。')
                    if response.headers.get('content-encoding', 'identity').strip().lower() != 'identity':
                        raise ModelRequestError('模型响应编码不受支持。')
                    data = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        data.extend(chunk)
                        if len(data) > MAX_RESPONSE_BYTES:
                            raise ModelRequestError('模型响应超过允许大小。')
            return json.loads(data)
    except asyncio.CancelledError:
        raise
    except ModelRequestError:
        raise
    except (TimeoutError, httpx.TimeoutException):
        raise ModelRequestError('模型请求超时，请稍后重试。') from None
    except (ValueError, OSError, httpx.HTTPError, UnicodeError, RecursionError):
        raise ModelRequestError('模型地址或服务响应不可用，请检查配置。') from None


# 普通聊天仅提取非空正文，忽略工具声明，不把响应中的凭据回显给用户。
def text_content(result):
    choices = result.get('choices') if isinstance(result, dict) else None
    message = choices[0].get('message') if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
    content = message.get('content') if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip() or len(content) > 50000:
        raise ModelRequestError('模型未返回有效文本回答。')
    return content.strip()


async def request_completion(target: ModelTarget, api_key: str, payload: dict, timeout_seconds: float, *, transport: httpx.AsyncBaseTransport | None = None) -> dict:
    result = await request_json(target, api_key, 'POST', '/chat/completions', {**payload, 'stream': False}, timeout_seconds, transport=transport)
    if not isinstance(result, dict):
        raise ModelRequestError('模型未返回有效响应。')
    return result


async def request_text(target: ModelTarget, api_key: str, payload: dict, timeout_seconds: float, *, transport: httpx.AsyncBaseTransport | None = None) -> str:
    result = await request_completion(target, api_key, payload, timeout_seconds, transport=transport)
    return text_content(result).replace(api_key, '***')
