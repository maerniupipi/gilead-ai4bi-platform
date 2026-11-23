"""
AES-256-GCM password encryption utility.

Stores passwords encrypted at rest in the DB.  Encrypted values are
prefixed with ``ENC:`` so the code can distinguish new ciphertext from
legacy plaintext passwords (backward compatible).

Key is loaded from the ``PASSWORD_ENCRYPTION_KEY`` environment variable
(64-char hex = 32 bytes).  The check is lazy — it only runs the first
time encrypt_password / decrypt_password is called, so the module can
be imported before ``load_app_environment()`` has executed (e.g. via ``database``).
"""

import os
import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_LENGTH = 12
_PREFIX = "ENC:"
logger = logging.getLogger(__name__)
_DEV_DEFAULT_KEY = hashlib.sha256(b"chatbi-local-development-password-key").digest()


@lru_cache(maxsize=1)
def _get_key() -> bytes:
    """Load & validate the encryption key (cached after first call)."""
    from .env_loader import load_app_environment

    load_app_environment()

    key_hex = os.getenv("PASSWORD_ENCRYPTION_KEY", "").strip()
    if not key_hex:
        app_env = os.getenv("APP_ENV", "dev").strip().lower()
        if app_env != "prod":
            logger.warning(
                "PASSWORD_ENCRYPTION_KEY 未配置，当前 APP_ENV=%s，使用开发环境默认密钥。"
                "请勿在生产环境依赖该默认值。",
                app_env,
            )
            return _DEV_DEFAULT_KEY
        raise RuntimeError(
            "PASSWORD_ENCRYPTION_KEY environment variable is required. "
            "Generate one with: python3 -c \"import os; print(os.urandom(32).hex())\""
        )
    try:
        key = bytes.fromhex(key_hex)
    except ValueError as exc:
        raise RuntimeError("PASSWORD_ENCRYPTION_KEY must be a 64-char hex string") from exc
    if len(key) != 32:
        raise RuntimeError("PASSWORD_ENCRYPTION_KEY must be 32 bytes (64 hex chars)")
    return key


def encrypt_password(plaintext: str) -> str:
    """Encrypt a plaintext password.

    Returns a base64-encoded string prefixed with ``ENC:``.
    The encoded payload is ``nonce(12) || ciphertext``.
    """
    aesgcm = AESGCM(_get_key())
    nonce = os.urandom(_NONCE_LENGTH)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    payload = base64.b64encode(nonce + ciphertext).decode("ascii")
    return f"{_PREFIX}{payload}"


def decrypt_password(encrypted: str) -> str:
    """Decrypt an encrypted password.

    Supports both ``ENC:``-prefixed ciphertext (new) and bare plaintext
    (legacy pre-encryption values).  Plaintext is returned as-is.
    """
    if not encrypted.startswith(_PREFIX):
        # Legacy plaintext password — still works
        return encrypted

    payload = encrypted[len(_PREFIX):]
    raw = base64.b64decode(payload)
    nonce = raw[:_NONCE_LENGTH]
    ciphertext = raw[_NONCE_LENGTH:]
    key = _get_key()
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None).decode("utf-8")
    except InvalidTag:
        app_env = os.getenv("APP_ENV", "dev").strip().lower()
        if app_env != "prod" and key != _DEV_DEFAULT_KEY:
            logger.warning(
                "密码使用当前 PASSWORD_ENCRYPTION_KEY 解密失败，当前 APP_ENV=%s，"
                "尝试兼容开发默认密钥。",
                app_env,
            )
            return AESGCM(_DEV_DEFAULT_KEY).decrypt(nonce, ciphertext, None).decode("utf-8")
        raise
