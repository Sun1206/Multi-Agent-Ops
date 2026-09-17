import asyncio
import ipaddress
import json
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from aidevops.restricted_http import PinnedBackend


MAX_RESPONSE_BYTES = 8 * 1024 * 1024
LOG_CONCURRENCY = asyncio.Semaphore(16)


class LogAddressError(ValueError):
    pass


@dataclass(frozen=True)
class LogTarget:
    url: str
    host: str
    port: int
    internal_allowed: bool


def validate_addresses(addresses, internal_allowed):
    result = []
    if not addresses:
        raise ValueError("日志地址未能解析。")
    for raw in addresses:
        address = ipaddress.ip_address(raw)
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        if address.is_link_local or address.is_multicast or address.is_unspecified or (address.is_reserved and not address.is_loopback):
            raise ValueError("日志地址禁止访问。")
        if not address.is_global and not (internal_allowed and (address.is_private or address.is_loopback)):
            raise ValueError("日志地址未获服务端授权。")
        if raw not in result:
            result.append(raw)
    return result


def validate_origin(endpoint, allowed_origins):
    parsed = urlsplit(endpoint.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("日志服务地址格式无效。")
    host = parsed.hostname.encode("idna").decode().lower()
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    origin = f"{parsed.scheme}://{host}:{port}"
    allowed = origin in allowed_origins or f"{parsed.scheme}://{host}" in allowed_origins
    if not allowed and (parsed.scheme != "https" or port != 443):
        raise ValueError("日志服务地址未获服务端授权。")
    authority = f"[{host}]" if ":" in host else host
    return LogTarget(f"{parsed.scheme}://{authority}:{port}{parsed.path.rstrip('/')}", host, port, allowed)


async def resolve_addresses(target):
    rows = await asyncio.get_running_loop().getaddrinfo(target.host, target.port, type=socket.SOCK_STREAM)
    return validate_addresses([row[4][0] for row in rows], target.internal_allowed)


async def request_json(target, method, suffix, *, headers=None, params=None, body=None, timeout=8):
    try:
        async with LOG_CONCURRENCY, asyncio.timeout(min(float(timeout), 30)):
            try:
                addresses = await resolve_addresses(target)
            except ValueError:
                raise LogAddressError("日志地址解析到未获授权的网络。") from None
            transport = httpx.AsyncHTTPTransport(verify=True, trust_env=False, retries=0)
            transport._pool._network_backend = PinnedBackend(target.host, target.port, addresses[0])
            safe_headers = {"Accept": "application/json", "Accept-Encoding": "identity", **(headers or {})}
            async with httpx.AsyncClient(transport=transport, trust_env=False, follow_redirects=False, timeout=timeout) as client:
                async with client.stream(method, target.url + suffix, headers=safe_headers, params=params, json=body) as response:
                    if not 200 <= response.status_code < 300 or response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise ValueError("日志服务请求失败。")
                    data = bytearray()
                    async for chunk in response.aiter_bytes(65536):
                        data.extend(chunk)
                        if len(data) > MAX_RESPONSE_BYTES:
                            raise ValueError("日志服务响应超过限制。")
            return json.loads(data)
    except asyncio.CancelledError:
        raise
    except LogAddressError:
        raise
    except TimeoutError:
        raise TimeoutError("日志服务请求超时。") from None
    except (httpx.HTTPError, OSError, UnicodeError, json.JSONDecodeError, ValueError):
        raise ValueError("日志服务请求失败，请检查数据源配置。") from None
