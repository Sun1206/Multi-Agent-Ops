import importlib

import httpx
import pytest


def module():
    return importlib.import_module('aidevops.restricted_http')


@pytest.mark.parametrize('url', ['file:///x', 'https://user:password@example.com/v1', 'https://example.com/v1?key=secret', 'https://example.com/#x', 'http://localhost:11434/v1', 'https://example.com:8443/v1', 'https://example.com:invalid/v1'])
def test_untrusted_origins_are_rejected(url):
    with pytest.raises(ValueError):
        module().validate_origin(url, [])


def test_exact_internal_origin_opt_in():
    target = module().validate_origin('http://localhost:11434/v1/', ['http://localhost:11434'])
    assert target.host == 'localhost' and target.port == 11434
    assert target.internal_allowed is True and target.url.endswith('/v1')
    with pytest.raises(ValueError):
        module().validate_origin('http://localhost:11435/v1', ['http://localhost:11434'])


@pytest.mark.parametrize('address', ['169.254.169.254', '0.0.0.0', '224.0.0.1', '::', '::ffff:169.254.169.254'])
def test_metadata_and_special_addresses_are_always_rejected(address):
    with pytest.raises(ValueError):
        module().validate_addresses([address], True)


def test_mixed_dns_answers_fail_closed():
    with pytest.raises(ValueError):
        module().validate_addresses(['8.8.8.8', '127.0.0.1'], False)
    assert module().validate_addresses(['127.0.0.1'], True) == ['127.0.0.1']


@pytest.mark.asyncio
async def test_backend_connects_only_validated_ip(monkeypatch):
    client = module()
    calls = []
    async def connect(self, host, port, **kwargs):
        calls.append((host, port))
        return 'stream'
    monkeypatch.setattr(client.AutoBackend, 'connect_tcp', connect)
    backend = client.PinnedBackend('example.com', 443, '8.8.8.8')
    assert await backend.connect_tcp('example.com', 443) == 'stream'
    assert calls == [('8.8.8.8', 443)]
    with pytest.raises(ValueError):
        await backend.connect_tcp('other.example.com', 443)


@pytest.mark.asyncio
async def test_model_text_request_is_single_non_streaming_and_secret_safe():
    client = module()
    requests = []
    def reply(request):
        requests.append(request)
        return httpx.Response(200, json={'choices': [{'message': {'content': 'answer secret-key'}}]})
    target = client.validate_origin('https://example.com/v1', [])
    result = await client.request_text(target, 'secret-key', {'model': 'model', 'messages': [{'role': 'user', 'content': 'hello'}]}, 5, transport=httpx.MockTransport(reply))
    assert result == 'answer ***' and len(requests) == 1
    assert requests[0].url.path == '/v1/chat/completions'
    assert requests[0].headers['authorization'] == 'Bearer secret-key'


@pytest.mark.parametrize('status,payload', [(302, {}), (401, {'error': {'message': 'secret-key'}}), (200, {'choices': [{'message': {'tool_calls': [{'id': 'a'}]}}]}), (200, {'choices': [{'message': {'content': ''}}]})])
@pytest.mark.asyncio
async def test_bad_responses_never_become_answers(status, payload):
    client = module()
    requests = []
    def reply(request):
        requests.append(request)
        return httpx.Response(status, json=payload, headers={'location': 'https://other.example.com'})
    target = client.validate_origin('https://example.com/v1', [])
    with pytest.raises(client.ModelRequestError) as error:
        await client.request_text(target, 'secret-key', {}, 5, transport=httpx.MockTransport(reply))
    assert 'secret-key' not in str(error.value) and len(requests) == 1


@pytest.mark.asyncio
async def test_oversized_response_is_rejected():
    client = module()
    target = client.validate_origin('https://example.com/v1', [])
    with pytest.raises(client.ModelRequestError):
        await client.request_text(target, 'key', {}, 5, transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b'x' * (1024 * 1024 + 1))))


def test_explicit_ipv6_loopback_is_supported():
    assert module().validate_addresses(['::1'], True) == ['::1']


@pytest.mark.asyncio
async def test_unexpected_compression_is_rejected_before_decoding():
    import gzip
    client = module()
    target = client.validate_origin('https://example.com/v1', [])
    body = gzip.compress(b'{"choices":[{"message":{"content":"answer"}}]}')
    with pytest.raises(client.ModelRequestError):
        await client.request_text(target, 'key', {}, 5, transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body, headers={'Content-Encoding': 'gzip'})))


@pytest.mark.asyncio
async def test_production_transport_pins_ip_preserves_tls_hostname_and_ignores_proxy(monkeypatch):
    import json
    client = module()
    calls, written, tls = [], bytearray(), []
    body = json.dumps({'choices': [{'message': {'content': 'answer'}}]}).encode()
    class Stream:
        response = b'HTTP/1.1 200 OK\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body
        async def read(self, max_bytes, timeout=None):
            data, self.response = self.response, b''
            return data
        async def write(self, data, timeout=None):
            written.extend(data)
        async def aclose(self):
            pass
        async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            tls.append((server_hostname, ssl_context.check_hostname))
            return self
        def get_extra_info(self, info):
            return None
    async def connect(self, host, port, **kwargs):
        calls.append((host, port))
        return Stream()
    async def addresses(target):
        return ['8.8.8.8']
    monkeypatch.setenv('HTTPS_PROXY', 'http://invalid-proxy:8080')
    monkeypatch.setattr(client, 'resolve_addresses', addresses)
    monkeypatch.setattr(client.AutoBackend, 'connect_tcp', connect)
    result = await client.request_text(client.validate_origin('https://example.com/v1', []), 'key', {}, 5)
    assert result == 'answer'
    assert calls == [('8.8.8.8', 443)] and tls == [('example.com', True)]
    assert b'Host: example.com' in written


@pytest.mark.asyncio
async def test_model_timeout_includes_request_and_does_not_retry():
    import asyncio
    client = module()
    calls = []
    async def blocked(request):
        calls.append(request)
        await asyncio.Event().wait()
    with pytest.raises(client.ModelRequestError, match='超时'):
        await client.request_text(client.validate_origin('https://example.com/v1', []), 'key', {}, .01, transport=httpx.MockTransport(blocked))
    assert len(calls) == 1
