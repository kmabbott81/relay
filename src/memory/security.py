"""Encryption helpers for memory_chunks data protection

TASK B: Encryption Helpers for Cross-Tenant Security

Provides:
- seal(plaintext, aad) → AES-256-GCM encrypted blob
- open_sealed(blob, aad) → decrypted plaintext
- hmac_user() → tenant key derivation (imported from rls.py)

AAD (Additional Authenticated Data) binding prevents cross-tenant decryption:
- User A encrypts with seal(data, aad=user_hash_a)
- User B cannot decrypt: open_sealed(blob, aad=user_hash_b) raises InvalidTag
- This is CRITICAL for multi-tenant security
"""

import base64
import logging
import os
import secrets

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Import hmac_user from rls.py (already implemented)

logger = logging.getLogger(__name__)

# MEMORY_ENCRYPTION_KEY: 32-byte base64-encoded key for AES-256-GCM
# Generate: python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
# Default: 44-character base64 string (32 bytes) for dev/testing
MEMORY_ENCRYPTION_KEY = os.getenv(
    "MEMORY_ENCRYPTION_KEY", "ZGV2LWVuY3J5cHRpb24ta2V5LTMyYnl0ZXMxMjM0NTY="  # Valid 44-char base64 (32 bytes)
)


# Custom exception for AAD binding failures
class InvalidTag(Exception):
    """Raised when AES-256-GCM authentication tag verification fails.

    Typically indicates:
    - Wrong AAD (cross-tenant decryption attempt)
    - Data tampering/corruption
    - Key mismatch

    This is FAIL-CLOSED: no plaintext fallback.
    """

    pass


def _decode_key() -> bytes:
    """Decode MEMORY_ENCRYPTION_KEY from base64 or hex format.

    Supports:
    - Base64-encoded (standard): base64.b64encode(os.urandom(32))
    - Hex-encoded (fallback): urandom(32).hex()
    - Raw string (dev only): 32-character string

    Returns:
        32-byte key for AES-256-GCM

    Raises:
        ValueError: If key cannot be decoded to 32 bytes
    """
    key_str = MEMORY_ENCRYPTION_KEY.strip()

    # Try base64 decode first (standard format)
    if len(key_str) == 44 and key_str.endswith("="):  # Base64 usually has padding
        try:
            decoded = base64.b64decode(key_str)
            if len(decoded) == 32:
                return decoded
        except Exception:
            pass

    # Try hex decode
    if len(key_str) == 64:  # Hex is 2 chars per byte
        try:
            decoded = bytes.fromhex(key_str)
            if len(decoded) == 32:
                return decoded
        except Exception:
            pass

    # Try raw bytes (dev only)
    if len(key_str) == 32:
        return key_str.encode("utf-8")

    # Failed
    raise ValueError(
        f"MEMORY_ENCRYPTION_KEY invalid. Expected 32 bytes (base64: 44 chars, hex: 64 chars), "
        f'got {len(key_str)}. Generate with: python -c "import os, base64; '
        f'print(base64.b64encode(os.urandom(32)).decode())"'
    )


def seal(plaintext: bytes, aad: bytes = b"") -> bytes:
    """Encrypt plaintext with AES-256-GCM using AAD binding.

    Format: nonce (12 bytes) || ciphertext || auth_tag (16 bytes)

    AAD (Additional Authenticated Data) is typically the user_hash:
    - Prevents cross-tenant decryption (if AAD mismatches, InvalidTag raised)
    - Authenticated but not encrypted (added to auth tag computation)

    Args:
        plaintext: Data to encrypt (bytes)
        aad: Additional Authenticated Data, typically user_hash (bytes)
             Default: b"" (no AAD)

    Returns:
        Encrypted blob: nonce (12) || ciphertext || tag (16)

    Example:
        >>> user_hash = b"user_a_hash"
        >>> ciphertext = seal(b"sensitive data", aad=user_hash)
        >>> plaintext = open_sealed(ciphertext, aad=user_hash)
        >>> plaintext == b"sensitive data"
        True

        >>> # Cross-tenant access prevented:
        >>> wrong_hash = b"user_b_hash"
        >>> open_sealed(ciphertext, aad=wrong_hash)  # Raises InvalidTag
    """
    try:
        key = _decode_key()
    except ValueError as e:
        logger.error(f"Invalid encryption key: {e}")
        raise

    # Generate random 12-byte nonce (IV)
    # AES-256-GCM uses 96-bit (12-byte) nonces for performance
    nonce = secrets.token_bytes(12)

    # Create cipher
    cipher = AESGCM(key)

    # Encrypt with AAD
    # Returns: ciphertext || auth_tag (combined)
    ciphertext_and_tag = cipher.encrypt(nonce, plaintext, aad)

    # Format: nonce || ciphertext_and_tag
    # Total length: 12 + len(plaintext) + 16 (auth tag is appended by encrypt)
    blob = nonce + ciphertext_and_tag

    logger.debug(
        f"Encrypted {len(plaintext)} bytes with {len(aad)} bytes AAD, "
        f"result: {len(blob)} bytes (nonce: 12, tag: 16, data: {len(plaintext)})"
    )

    return blob


def open_sealed(blob: bytes, aad: bytes = b"") -> bytes:
    """Decrypt AES-256-GCM blob with AAD verification.

    Format: nonce (12 bytes) || ciphertext || auth_tag (16 bytes)

    AAD must match what was used during encryption:
    - If AAD mismatches: auth tag verification fails → InvalidTag raised
    - This is FAIL-CLOSED: no plaintext fallback

    Args:
        blob: Encrypted data from seal()
        aad: Additional Authenticated Data (must match seal() AAD)
             Default: b"" (must match if seal was called with b"")

    Returns:
        Decrypted plaintext (bytes)

    Raises:
        InvalidTag: If AAD mismatches, tag is invalid, or data corrupted
        ValueError: If blob is too short (< 28 bytes minimum)

    Example:
        >>> user_hash = b"user_a_hash"
        >>> blob = seal(b"secret", aad=user_hash)
        >>> open_sealed(blob, aad=user_hash)
        b"secret"

        >>> # Wrong AAD raises InvalidTag
        >>> open_sealed(blob, aad=b"wrong_hash")
        Traceback (most recent call last):
        InvalidTag: ...
    """
    # Validate minimum blob size
    # Minimum: 12 (nonce) + 1 (min ciphertext) + 16 (tag) = 29 bytes
    if len(blob) < 28:
        raise ValueError(f"Blob too short: {len(blob)} bytes (minimum 28: 12 nonce + 1 data + 16 tag)")

    try:
        key = _decode_key()
    except ValueError as e:
        logger.error(f"Invalid encryption key: {e}")
        raise

    # Extract nonce (first 12 bytes)
    nonce = blob[:12]

    # Extract ciphertext_and_tag (remaining bytes)
    ciphertext_and_tag = blob[12:]

    # Create cipher
    cipher = AESGCM(key)

    try:
        # Decrypt with AAD verification
        # If AAD mismatches or tag invalid: raises InvalidTag
        plaintext = cipher.decrypt(nonce, ciphertext_and_tag, aad)

        logger.debug(f"Decrypted {len(plaintext)} bytes with {len(aad)} bytes AAD validation")

        return plaintext

    except Exception as e:
        # cryptography raises InvalidTag or cryptography.exceptions.InvalidTag
        # Wrap in our custom InvalidTag exception
        error_msg = str(e)
        if "tag" in error_msg.lower() or "authentication" in error_msg.lower():
            raise InvalidTag(
                f"AAD binding verification failed: {error_msg}. "
                "This typically indicates cross-tenant access attempt or data corruption."
            ) from e
        else:
            # Other crypto errors
            raise InvalidTag(f"Decryption failed: {error_msg}") from e


def compute_payload_hash(plaintext: bytes) -> str:
    """Compute SHA-256 hash of plaintext for integrity tracking.

    Used to detect plaintext modifications without re-decryption.
    This is NOT the encryption key or AAD - it's for logging/audit.

    Args:
        plaintext: Data to hash

    Returns:
        Hex-encoded SHA-256 hash (64 characters)
    """
    digest = hashes.Hash(hashes.SHA256())
    digest.update(plaintext)
    return digest.finalize().hex()
