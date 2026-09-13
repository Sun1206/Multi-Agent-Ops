import hashlib
import secrets

from pwdlib import PasswordHash


password_hash = PasswordHash.recommended()


def hash_password(raw_password: str) -> str:
    return password_hash.hash(raw_password)


def verify_password(raw_password: str, encoded_password: str) -> bool:
    return password_hash.verify(raw_password, encoded_password)


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def digest_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
