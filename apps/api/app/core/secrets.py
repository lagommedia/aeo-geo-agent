import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_fernet() -> Fernet | None:
    key = getattr(settings, "source_encryption_key", None)
    if not key:
        return None
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    f = _build_fernet()
    if not f:
        logger.warning("SOURCE_ENCRYPTION_KEY missing; storing source secrets as plain text for local dev")
        return value
    return f.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    f = _build_fernet()
    if not f:
        return value
    try:
        return f.decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # Fallback for previously unencrypted values
        return value
