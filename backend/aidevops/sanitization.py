from collections.abc import Mapping
from typing import Any


SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
    "accesskey",
    "privatekey",
    "certificate",
    "certcontent",
    "keycontent",
    "apikey",
    "sshcredential",
    "kubeconfig",
}


def normalize_key(key: object) -> str:
    return str(key).lower().replace("-", "").replace("_", "")


def is_sensitive_key(key: object) -> bool:
    normalized = normalize_key(key)
    return any(item in normalized for item in SENSITIVE_KEYS)


def sanitize_metadata(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: "***" if is_sensitive_key(key) else sanitize_metadata(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_metadata(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_metadata(item) for item in value]
    return value
