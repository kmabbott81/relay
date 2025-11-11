"""
Tests for Envelope Encryption - Sprint 33B

Covers AES-256-GCM encryption/decryption with keyring.
"""

import pytest

from relay_ai.crypto.envelope import decrypt, encrypt
from relay_ai.crypto.keyring import active_key, get_key, rotate_key


@pytest.fixture
def temp_keyring(tmp_path, monkeypatch):
    """Setup temporary keyring."""
    keyring_path = tmp_path / "keyring.jsonl"
    monkeypatch.setenv("KEYRING_PATH", str(keyring_path))
    return keyring_path


def test_encrypt_creates_envelope(temp_keyring):
    """Test encryption creates envelope with all fields."""
    key = active_key()
    plaintext = b"secret data"

    envelope = encrypt(plaintext, key)

    assert "key_id" in envelope
    assert "nonce" in envelope
    assert "ciphertext" in envelope
    assert "tag" in envelope

    assert envelope["key_id"] == key["key_id"]


def test_decrypt_roundtrip(temp_keyring):
    """Test encrypt/decrypt roundtrip."""
    key = active_key()
    plaintext = b"secret data"

    envelope = encrypt(plaintext, key)
    decrypted = decrypt(envelope)

    assert decrypted == plaintext


def test_decrypt_with_get_key(temp_keyring):
    """Test decrypt uses get_key to retrieve key."""
    key = active_key()
    plaintext = b"test message"

    envelope = encrypt(plaintext, key)

    # Decrypt should automatically use get_key
    decrypted = decrypt(envelope, keyring_get_fn=get_key)

    assert decrypted == plaintext


def test_decrypt_wrong_key_fails(temp_keyring):
    """Test decryption fails with wrong key."""
    key = active_key()
    plaintext = b"secret"

    envelope = encrypt(plaintext, key)

    # Modify key_id to point to non-existent key
    envelope["key_id"] = "key-999"

    with pytest.raises(ValueError, match="Key not found"):
        decrypt(envelope)


def test_decrypt_tampered_ciphertext_fails(temp_keyring):
    """Test decryption fails with tampered ciphertext."""
    key = active_key()
    plaintext = b"secret"

    envelope = encrypt(plaintext, key)

    # Tamper with ciphertext
    import base64

    tampered = base64.b64encode(b"tampered").decode("utf-8")
    envelope["ciphertext"] = tampered

    with pytest.raises(ValueError, match="Decryption failed"):
        decrypt(envelope)


def test_decrypt_with_retired_key(temp_keyring):
    """Test decryption works with retired key."""
    key = active_key()
    plaintext = b"old data"

    # Encrypt with original key
    envelope = encrypt(plaintext, key)

    # Rotate key (retires original)
    rotate_key()

    # Should still decrypt with retired key
    decrypted = decrypt(envelope)
    assert decrypted == plaintext


def test_encrypt_different_nonces(temp_keyring):
    """Test encryption uses different nonces for same plaintext."""
    key = active_key()
    plaintext = b"same plaintext"

    envelope1 = encrypt(plaintext, key)
    envelope2 = encrypt(plaintext, key)

    # Nonces should be different
    assert envelope1["nonce"] != envelope2["nonce"]

    # Ciphertexts should be different (due to different nonces)
    assert envelope1["ciphertext"] != envelope2["ciphertext"]


def test_encrypt_empty_plaintext(temp_keyring):
    """Test encryption of empty plaintext."""
    key = active_key()
    plaintext = b""

    envelope = encrypt(plaintext, key)
    decrypted = decrypt(envelope)

    assert decrypted == b""


def test_encrypt_large_plaintext(temp_keyring):
    """Test encryption of large plaintext."""
    key = active_key()
    plaintext = b"x" * 1024 * 100  # 100 KB

    envelope = encrypt(plaintext, key)
    decrypted = decrypt(envelope)

    assert decrypted == plaintext


def test_envelope_base64_encoded(temp_keyring):
    """Test envelope fields are base64 encoded."""
    key = active_key()
    plaintext = b"test"

    envelope = encrypt(plaintext, key)

    import base64

    # All fields should be valid base64
    base64.b64decode(envelope["nonce"])
    base64.b64decode(envelope["ciphertext"])
    base64.b64decode(envelope["tag"])


def test_encrypt_with_rotated_key(temp_keyring):
    """Test encryption with new key after rotation."""
    # Encrypt with original key
    key1 = active_key()
    plaintext1 = b"data1"
    envelope1 = encrypt(plaintext1, key1)

    # Rotate key
    key2 = rotate_key()

    # Encrypt with new key
    plaintext2 = b"data2"
    envelope2 = encrypt(plaintext2, key2)

    # Both should decrypt correctly
    assert decrypt(envelope1) == plaintext1
    assert decrypt(envelope2) == plaintext2

    # Envelopes should use different keys
    assert envelope1["key_id"] != envelope2["key_id"]


def test_decrypt_invalid_envelope_format(temp_keyring):
    """Test decryption fails with invalid envelope."""
    envelope = {
        "key_id": "key-001",
        "nonce": "invalid",
        "ciphertext": "invalid",
        "tag": "invalid",
    }

    # Could be ValueError or binascii.Error
    with pytest.raises((ValueError, Exception)):
        decrypt(envelope)


def test_nonce_length(temp_keyring):
    """Test nonce is 96 bits (12 bytes) as recommended for GCM."""
    key = active_key()
    plaintext = b"test"

    envelope = encrypt(plaintext, key)

    import base64

    nonce = base64.b64decode(envelope["nonce"])
    assert len(nonce) == 12  # 96 bits


def test_tag_length(temp_keyring):
    """Test GCM tag is 128 bits (16 bytes)."""
    key = active_key()
    plaintext = b"test"

    envelope = encrypt(plaintext, key)

    import base64

    tag = base64.b64decode(envelope["tag"])
    assert len(tag) == 16  # 128 bits
