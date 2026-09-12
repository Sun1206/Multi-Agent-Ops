import hashlib
import secrets

from pwdlib import PasswordHash


password_hash = PasswordHash.recommended()


def hash_password(raw_password: str) -> str:
    """使用 Argon2id 哈希原始密码，调用方不得记录原始值。"""
    return password_hash.hash(raw_password)


def verify_password(raw_password: str, encoded_password: str) -> bool:
    """校验原始密码与 Argon2id 哈希是否匹配，不泄露失败原因。"""
    return password_hash.verify(raw_password, encoded_password)


def generate_token() -> str:
    """生成一次性返回给客户端的高熵不透明登录令牌。"""
    return secrets.token_urlsafe(32)


def digest_token(raw_token: str) -> str:
    """计算令牌 SHA-256 摘要，数据库只保存该摘要。"""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
