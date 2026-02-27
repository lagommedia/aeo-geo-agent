from __future__ import annotations

import hashlib
import hmac
import secrets
from base64 import urlsafe_b64decode, urlsafe_b64encode

from content_demand_agent.config import settings


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return urlsafe_b64encode(salt + digest).decode()


def verify_password(password: str, stored_hash: str) -> bool:
    raw = urlsafe_b64decode(stored_hash.encode())
    salt, expected = raw[:16], raw[16:]
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return hmac.compare_digest(digest, expected)


def encrypt_credential(value: str) -> str:
    key = hashlib.sha256(settings.app_secret_key.encode()).digest()
    data = value.encode()
    out = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return urlsafe_b64encode(out).decode()


def decrypt_credential(token: str) -> str:
    key = hashlib.sha256(settings.app_secret_key.encode()).digest()
    data = urlsafe_b64decode(token.encode())
    out = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return out.decode()
