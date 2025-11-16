"""
Envelope encryption using AES-256-GCM.

Sprint 33B: Encrypt/decrypt with keyring support.
Sprint 62: AAD (Additional Authenticated Data) support for Task D memory APIs.
"""

import base64
import hashlib
import hmac
import logging
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .keyring import get_key

logger = logging.getLogger(__name__)

# Memory tenant HMAC key for AAD binding
# Used to compute AAD = HMAC-SHA256(MEMORY_TENANT_HMAC_KEY, user_hash)
MEMORY_TENANT_HMAC_KEY = os.getenv("MEMORY_TENANT_HMAC_KEY", "dev-hmac-key-change-in-production")


def encrypt(plaintext: bytes, keyring_key: dict) -> dict:
    """
    Encrypt data using envelope encryption with AES-256-GCM.

    Args:
        plaintext: Raw bytes to encrypt
        keyring_key: Key record from keyring (must have key_material_base64)

    Returns:
        Envelope blob with key_id, nonce, ciphertext, tag

    Example:
        >>> from relay_ai.crypto.keyring import active_key
        >>> key = active_key()
        >>> envelope = encrypt(b"secret data", key)
        >>> envelope['key_id']
        'key-001'
        >>> 'ciphertext' in envelope
        True
    """
    key_id = keyring_key["key_id"]
    key_material_b64 = keyring_key["key_material_base64"]
    key_material = base64.b64decode(key_material_b64)

    # Generate random nonce (96 bits recommended for GCM)
    import os

    nonce = os.urandom(12)

    # Encrypt with AESGCM
    aesgcm = AESGCM(key_material)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    # AESGCM returns ciphertext + tag concatenated
    # Tag is last 16 bytes
    tag = ciphertext[-16:]
    ciphertext_only = ciphertext[:-16]

    return {
        "key_id": key_id,
        "nonce": base64.b64encode(nonce).decode("utf-8"),
        "ciphertext": base64.b64encode(ciphertext_only).decode("utf-8"),
        "tag": base64.b64encode(tag).decode("utf-8"),
    }


def decrypt(envelope: dict, keyring_get_fn: Any = None) -> bytes:
    """
    Decrypt envelope-encrypted data.

    Args:
        envelope: Envelope blob with key_id, nonce, ciphertext, tag
        keyring_get_fn: Function to retrieve key by key_id (defaults to get_key)

    Returns:
        Decrypted plaintext bytes

    Raises:
        ValueError: If key not found or decryption fails

    Example:
        >>> envelope = {"key_id": "key-001", "nonce": "...", "ciphertext": "...", "tag": "..."}
        >>> plaintext = decrypt(envelope)
        >>> plaintext
        b'secret data'
    """
    if keyring_get_fn is None:
        keyring_get_fn = get_key

    key_id = envelope["key_id"]
    key_record = keyring_get_fn(key_id)

    if not key_record:
        raise ValueError(f"Key not found: {key_id}")

    key_material_b64 = key_record["key_material_base64"]
    key_material = base64.b64decode(key_material_b64)

    nonce = base64.b64decode(envelope["nonce"])
    ciphertext_only = base64.b64decode(envelope["ciphertext"])
    tag = base64.b64decode(envelope["tag"])

    # Reconstruct full ciphertext (ciphertext + tag)
    ciphertext = ciphertext_only + tag

    # Decrypt with AESGCM
    aesgcm = AESGCM(key_material)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext
    except Exception as e:
        raise ValueError(f"Decryption failed: {e}") from e


# --- AAD (Additional Authenticated Data) Support for Memory APIs ---


def _compute_aad_digest(aad: bytes) -> bytes:
    """
    Compute AAD digest using HMAC-SHA256.

    Args:
        aad: Additional authenticated data (e.g., user_hash as bytes)

    Returns:
        HMAC-SHA256 digest (32 bytes) for use as AESGCM AAD parameter
    """
    return hmac.new(MEMORY_TENANT_HMAC_KEY.encode("utf-8"), aad, hashlib.sha256).digest()


def encrypt_with_aad(plaintext: bytes, aad: bytes, keyring_key: dict) -> dict:
    """
    Encrypt data using AES-256-GCM with AAD (Additional Authenticated Data) binding.

    AAD binds the ciphertext to a specific value (e.g., user_hash).
    If the ciphertext is decrypted with a different AAD value, decryption fails (fail-closed).
    This prevents cross-user access even if ciphertext is moved between users.

    Args:
        plaintext: Raw bytes to encrypt
        aad: Additional authenticated data (e.g., user_hash). Typically 64 hex chars for HMAC-SHA256
        keyring_key: Key record from keyring (must have key_material_base64)

    Returns:
        Envelope blob with key_id, nonce, ciphertext, tag, aad_bound_to

    Raises:
        ValueError: If key material is invalid

    Example:
        >>> from relay_ai.crypto.keyring import active_key
        >>> from relay_ai.platform.security.memory.rls import hmac_user
        >>> key = active_key()
        >>> user_hash = hmac_user("user_123")
        >>> envelope = encrypt_with_aad(
        ...     b"memory chunk text",
        ...     aad=user_hash.encode(),
        ...     keyring_key=key
        ... )
        >>> # Ciphertext now bound to user_hash; can't decrypt with different user
    """
    key_id = keyring_key["key_id"]
    key_material_b64 = keyring_key["key_material_base64"]
    key_material = base64.b64decode(key_material_b64)

    # Generate random nonce (96 bits recommended for GCM)
    nonce = os.urandom(12)

    # Compute AAD digest
    aad_digest = _compute_aad_digest(aad)

    # Encrypt with AESGCM + AAD
    aesgcm = AESGCM(key_material)
    ciphertext = aesgcm.encrypt(nonce, plaintext, aad_digest)

    # AESGCM returns ciphertext + tag concatenated
    tag = ciphertext[-16:]
    ciphertext_only = ciphertext[:-16]

    return {
        "key_id": key_id,
        "nonce": base64.b64encode(nonce).decode("utf-8"),
        "ciphertext": base64.b64encode(ciphertext_only).decode("utf-8"),
        "tag": base64.b64encode(tag).decode("utf-8"),
        "aad_bound_to": aad.decode("utf-8") if isinstance(aad, bytes) else aad,  # Audit trail
    }


def decrypt_with_aad(envelope: dict, aad: bytes, keyring_get_fn: Any = None) -> bytes:
    """
    Decrypt envelope-encrypted data with AAD validation.

    Validates that the provided AAD matches the AAD used during encryption.
    If AAD doesn't match, decryption fails immediately (fail-closed, no plaintext leakage).

    Args:
        envelope: Envelope blob with key_id, nonce, ciphertext, tag, aad_bound_to
        aad: Additional authenticated data (e.g., user_hash). Must match encryption AAD
        keyring_get_fn: Function to retrieve key by key_id (defaults to get_key)

    Returns:
        Decrypted plaintext bytes

    Raises:
        ValueError: If AAD doesn't match, key not found, or decryption fails
        cryptography.hazmat.primitives.ciphers.aead.InvalidTag: If AAD validation fails

    Example:
        >>> from relay_ai.crypto.keyring import active_key
        >>> from relay_ai.platform.security.memory.rls import hmac_user
        >>> key = active_key()
        >>> user_hash = hmac_user("user_123")
        >>> envelope = encrypt_with_aad(
        ...     b"secret",
        ...     aad=user_hash.encode(),
        ...     keyring_key=key
        ... )
        >>> # Decrypt with correct AAD: success
        >>> plaintext = decrypt_with_aad(envelope, aad=user_hash.encode())
        >>> plaintext
        b'secret'
        >>> # Try to decrypt with different AAD: fails
        >>> different_hash = hmac_user("user_999")
        >>> decrypt_with_aad(envelope, aad=different_hash.encode())  # Raises ValueError
    """
    if keyring_get_fn is None:
        keyring_get_fn = get_key

    key_id = envelope["key_id"]
    key_record = keyring_get_fn(key_id)

    if not key_record:
        raise ValueError(f"Key not found: {key_id}")

    key_material_b64 = key_record["key_material_base64"]
    key_material = base64.b64decode(key_material_b64)

    nonce = base64.b64decode(envelope["nonce"])
    ciphertext_only = base64.b64decode(envelope["ciphertext"])
    tag = base64.b64decode(envelope["tag"])

    # Reconstruct full ciphertext (ciphertext + tag)
    ciphertext = ciphertext_only + tag

    # Compute AAD digest
    aad_digest = _compute_aad_digest(aad)

    # Decrypt with AESGCM + AAD validation
    aesgcm = AESGCM(key_material)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, aad_digest)
        logger.debug(f"Decryption with AAD successful (bound to: {envelope.get('aad_bound_to', 'unknown')})")
        return plaintext
    except Exception as e:
        logger.warning(f"Decryption with AAD failed: {e} (AAD validation error or corrupted data)")
        raise ValueError(f"Decryption with AAD validation failed: {e}") from e


def get_aad_from_user_hash(user_hash: str) -> bytes:
    """
    Convert user_hash string to bytes for AAD parameter.

    Args:
        user_hash: User hash string (e.g., from hmac_user())

    Returns:
        User hash as bytes (ready for encrypt_with_aad/decrypt_with_aad)

    Example:
        >>> aad = get_aad_from_user_hash("abc123def456...")
        >>> envelope = encrypt_with_aad(b"data", aad=aad, keyring_key=key)
    """
    return user_hash.encode("utf-8") if isinstance(user_hash, str) else user_hash
