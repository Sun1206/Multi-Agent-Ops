import json

from app.services.model_client import ModelAdmissionError, ModelRequestError, text_content


TOOL_NAME = 'aiops_connection_probe'
TEXT_ERROR = '未能验证候选模型，请检查模型名称和服务配置。'
CATALOG_ERROR = '模型目录读取失败或未返回可用模型。'


# 模型标识仅允许短字符串；拒绝控制字符和凭据回显，保留原有合法ID。
def safe_model_id(value, key):
    return isinstance(value, str) and 0 < len(value) <= 128 and value == value.strip() and not any(ord(char) < 32 or ord(char) == 127 for char in value) and key not in value


# 按配置/目录顺序去重并截断模型ID列表；不把目录数量当作验证成功数量。
def model_ids(values, key, limit=200):
    result = []
    for value in values:
        if safe_model_id(value, key) and value not in result:
            result.append(value)
            if len(result) == limit:
                break
    return result


# 测试提示词不包含用户业务数据，且限制输出长度；工具仅为无副作用的声明。
def probe_payload(model, tools=False):
    payload = {'model': model, 'temperature': 0, 'max_tokens': 32, 'stream': False, 'messages': [{'role': 'user', 'content': '请只回复：连接成功'}]}
    if tools:
        payload['messages'] = [{'role': 'user', 'content': '请调用连接测试函数，参数ok设为true。'}]
        payload['tools'] = [{'type': 'function', 'function': {'name': TOOL_NAME, 'description': '只验证工具声明格式，不执行任何操作。', 'parameters': {'type': 'object', 'properties': {'ok': {'type': 'boolean', 'enum': [True]}}, 'required': ['ok'], 'additionalProperties': False}}}]
        payload['tool_choice'] = {'type': 'function', 'function': {'name': TOOL_NAME}}
    return payload


# 只接受安全的供应商模型标识；未返回可用标识时以请求模型说明本次探测。
def resolved_model(result, requested, key):
    value = result.get('model') if isinstance(result, dict) else None
    return value if safe_model_id(value, key) else requested


# 验证返回的函数名与参数结构；只判断声明支持，不把任何调用交给执行器。
def supports_tool_calling(result):
    try:
        message = result['choices'][0]['message']
        calls = message['tool_calls']
        if not isinstance(calls, list) or len(calls) != 1:
            return False
        call = calls[0]
        function = call['function']
        arguments = json.loads(function['arguments'])
        return call.get('type') == 'function' and isinstance(call.get('id'), str) and bool(call['id']) and function['name'] == TOOL_NAME and isinstance(arguments, dict) and set(arguments) == {'ok'} and arguments['ok'] is True
    except (KeyError, IndexError, TypeError, ValueError, RecursionError):
        return False


# 目录失败只能回退到配置中的模型，不能回退网络准入错误或宣称已验证。
async def discover_models(call, config, key, probe):
    catalog_error, fallback = '', False
    try:
        result = await call('GET', '/models', None)
        rows = result.get('data') if isinstance(result, dict) else None
        ids = model_ids([row.get('id') for row in rows if isinstance(row, dict)], key) if isinstance(rows, list) else []
        if not ids:
            raise ModelRequestError(CATALOG_ERROR)
    except ModelAdmissionError:
        raise
    except ModelRequestError:
        ids = model_ids([config['default_model'], config['backup_model']], key)
        catalog_error, fallback = CATALOG_ERROR, True
        if not ids:
            raise ModelRequestError('模型目录不可用，且未配置可用的回退模型。') from None
    candidates = model_ids([config['default_model'], config['backup_model']] + ids, key, 2) if probe else []
    recommendation = None
    if probe:
        for candidate in candidates:
            try:
                result = await call('POST', '/chat/completions', probe_payload(candidate))
                text_content(result)
            except ModelAdmissionError:
                raise
            except ModelRequestError:
                continue
            model = resolved_model(result, candidate, key)
            tools = False
            try:
                tool_result = await call('POST', '/chat/completions', probe_payload(candidate, True))
                tools = supports_tool_calling(tool_result) and resolved_model(tool_result, candidate, key) == model
            except ModelAdmissionError:
                raise
            except ModelRequestError:
                pass
            suggestion = {'model': model, 'requested_model': candidate, 'verified': True, 'supports_tool_calling': tools, 'message': '模型文本及工具声明已验证。' if tools else '模型文本已验证，工具调用能力尚未验证。'}
            if recommendation is None or tools:
                recommendation = suggestion
            if tools:
                break
    return {'models': [{'id': value} for value in ids], 'count': len(ids), 'recommendation': recommendation, 'probe_candidates': candidates, 'probe_error': TEXT_ERROR if probe and recommendation is None else '', 'catalog_error': catalog_error, 'fallback_used': fallback}
