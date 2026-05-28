"""
Security utilities — encryption, JWT, and HMAC validation.
"""

import base64
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jose import JWTError, jwt

from app.config import app_settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


def get_encryption_key() -> bytes:
    """Derive 256-bit AES key from master key env variable."""
    master_key = app_settings.encryption_master_key
    key_bytes = base64.b64decode(master_key)
    if len(key_bytes) != 32:
        raise ValueError("ENCRYPTION_MASTER_KEY must be 32 bytes (base64 encoded)")
    return key_bytes


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret (API key, private key) using AES-256-GCM."""
    key = get_encryption_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    # Store as base64(nonce + ciphertext)
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt_secret(encrypted: str) -> str:
    """Decrypt an AES-256-GCM encrypted secret."""
    key = get_encryption_key()
    aesgcm = AESGCM(key)
    raw = base64.b64decode(encrypted)
    nonce = raw[:12]
    ciphertext = raw[12:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, app_settings.jwt_secret, algorithm=ALGORITHM)


def verify_access_token(token: str) -> Optional[dict]:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, app_settings.jwt_secret, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def validate_webhook_hmac(payload: bytes, signature: str, secret: str) -> bool:
    """Validate HMAC-SHA256 signature on incoming webhook payloads."""
    import hmac
    import hashlib
    expected = hmac.new(
        secret.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
