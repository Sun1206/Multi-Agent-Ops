# 对配置凭据加密、脱敏，并安全恢复同路径的页面掩码。

import os
from copy import deepcopy

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from dotenv import dotenv_values

from aidevops.exceptions import BusinessError
from aidevops.sanitization import is_sensitive_key


ENVELOPE = '__aiops_secret_v1__'


def config_cipher() -> Fernet:
    key = os.environ.get('AIOPS_CONFIG_ENCRYPTION_KEY', dotenv_values('.env').get('AIOPS_CONFIG_ENCRYPTION_KEY') or '')
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=503, detail='配置加密密钥未设置或无效，请检查服务端环境。') from error


def encrypt_secret(raw: str) -> str:
    return config_cipher().encrypt(raw.encode()).decode() if raw else ''


def usable_secret(encrypted: str) -> bool:
    if not encrypted:
        return False
    try:
        return bool(config_cipher().decrypt(encrypted.encode()))
    except (HTTPException, InvalidToken, ValueError):
        return False


def transform_auth(value, old=None, *, masked=False, sensitive=False, depth=0):
    if depth > 20:
        raise BusinessError('鉴权配置嵌套过深。')
    if isinstance(value, dict):
        if ENVELOPE in value:
            if masked:
                return '***'
            raise BusinessError('客户端不能提交凭据密文封装。')
        if sensitive:
            raise BusinessError('鉴权敏感字段必须是字符串。')
        output = {}
        for key, item in value.items():
            previous = old.get(key) if isinstance(old, dict) else None
            if key in {'headers', 'env'}:
                if not isinstance(item, dict):
                    raise BusinessError('headers/env 必须是对象。')
                output[key] = {child: transform_auth(leaf, previous.get(child) if isinstance(previous, dict) else None, masked=masked, sensitive=True, depth=depth + 1) for child, leaf in item.items()}
            else:
                output[key] = transform_auth(item, previous, masked=masked, sensitive=is_sensitive_key(key), depth=depth + 1)
        return output
    if isinstance(value, list):
        if sensitive:
            raise BusinessError('鉴权敏感字段必须是字符串。')
        return [transform_auth(item, old[index] if isinstance(old, list) and index < len(old) else None, masked=masked, depth=depth + 1) for index, item in enumerate(value)]
    if sensitive:
        if not isinstance(value, str):
            raise BusinessError('鉴权敏感字段必须是字符串。')
        if masked:
            return '***' if value else ''
        if value == '***':
            if old is None or old == '':
                raise BusinessError('新凭据路径不能使用掩码。')
            return deepcopy(old) if isinstance(old, dict) else {ENVELOPE: encrypt_secret(old)}
        return {ENVELOPE: encrypt_secret(value)} if value else ''
    return value
