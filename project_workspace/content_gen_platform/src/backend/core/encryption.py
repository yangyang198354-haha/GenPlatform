"""AES-256-GCM encryption utility for secure credential storage."""
import os
import base64
import json
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings


def _get_key() -> bytes:
    """Derive a 32-byte key from settings.ENCRYPTION_KEY."""
    raw = settings.ENCRYPTION_KEY
    if isinstance(raw, str):
        raw = raw.encode()
    # Pad or truncate to exactly 32 bytes
    return raw[:32].ljust(32, b"\x00")


def encrypt(data: dict | str) -> bytes:
    """Encrypt a dict or string to AES-256-GCM ciphertext.

    Returns: nonce (12 bytes) + ciphertext, base64-encoded.
    """
    if isinstance(data, dict):
        plaintext = json.dumps(data).encode()
    else:
        plaintext = str(data).encode()

    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return base64.b64encode(nonce + ciphertext)


def decrypt(token: bytes) -> dict | str:
    """Decrypt AES-256-GCM token produced by encrypt().

    Returns the original dict if JSON-parseable, otherwise a string.
    """
    raw = base64.b64decode(token)
    nonce, ciphertext = raw[:12], raw[12:]
    key = _get_key()
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    try:
        return json.loads(plaintext)
    except json.JSONDecodeError:
        return plaintext.decode()
