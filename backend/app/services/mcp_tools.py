import json
import re

from app.services.events import is_sensitive_key


DENY_WRITE = re.compile(r'^(create|update|delete|remove|write|patch|mutate|execute|run|apply|drop|truncate|grant|revoke)([_\-.]|$)', re.IGNORECASE)


# 可安全转换为固定失败响应的远端协议、体积或元数据校验异常。
class McpError(ValueError):
    pass


# 远端描述、schema和服务器信息仅作展示；递归脱敏并限制深度，不执行其中的指令。
def public_data(value, secrets, depth=0):
    if depth > 20:
        raise McpError('MCP返回数据嵌套过深。')
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, '***')
        return value
    if isinstance(value, dict):
        return {public_data(str(key), secrets, depth + 1): '***' if is_sensitive_key(key) else public_data(item, secrets, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [public_data(item, secrets, depth + 1) for item in value]
    return value


# 保留旧白名单和默认只读名称过滤；工具声明不能证明可执行，也不会接入聊天。
def project_tools(rows, whitelist, allow_write, secrets):
    tools, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get('name')
        if not isinstance(name, str) or not name.strip() or len(name) > 128 or any(ord(char) < 32 or ord(char) == 127 for char in name) or any(secret and secret in name for secret in secrets):
            continue
        name = name.strip()
        if name in seen or (whitelist and name not in whitelist) or (not allow_write and DENY_WRITE.search(name)):
            continue
        schema = row.get('inputSchema')
        if not isinstance(schema, dict) or schema.get('type', 'object') != 'object':
            schema = {'type': 'object', 'properties': {}}
        schema = public_data(schema, secrets)
        schema.setdefault('type', 'object')
        if 'properties' in schema and not isinstance(schema['properties'], dict):
            schema['properties'] = {}
        if len(json.dumps(schema, ensure_ascii=False).encode()) > 65536:
            raise McpError('MCP工具参数声明超过允许大小。')
        description = row.get('description')
        description = public_data(description, secrets)[:1200] if isinstance(description, str) else name
        tools.append({'name': name, 'description': description, 'inputSchema': schema})
        seen.add(name)
    return tools
