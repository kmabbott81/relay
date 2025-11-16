"""
Cryptographic primitives for envelope encryption.

Sprint 33B: Envelope encryption with key rotation.
"""

from .envelope import decrypt, encrypt
from .keyring import active_key, get_key, list_keys, rotate_key

__all__ = [
    "active_key",
    "rotate_key",
    "get_key",
    "list_keys",
    "encrypt",
    "decrypt",
]
