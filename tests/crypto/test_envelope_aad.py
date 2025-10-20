"""
Unit tests for AES-256-GCM envelope encryption with AAD (Additional Authenticated Data).

Task D Phase 1: Encryption Enhancement
Tests AAD binding, validation, and fail-closed behavior for memory APIs.
"""

from unittest.mock import Mock

import pytest

from src.crypto.envelope import (
    _compute_aad_digest,
    decrypt_with_aad,
    encrypt_with_aad,
    get_aad_from_user_hash,
)


@pytest.fixture
def mock_keyring_key():
    """Mock keyring key for testing."""
    return {
        "key_id": "key-001",
        "key_material_base64": "i1jz+DY2jF8DsKV8q5L9oP3Rq7W8nM5vX2yZ3aB4cD5=",  # 32 bytes base64
    }


@pytest.fixture
def user_hash_1():
    """First user's hash."""
    return "abc123def456abc123def456abc123def456abc123def456abc123def456abc1"


@pytest.fixture
def user_hash_2():
    """Second user's hash (different)."""
    return "xyz789uvw012xyz789uvw012xyz789uvw012xyz789uvw012xyz789uvw012xyz7"


class TestAADEncryption:
    """Tests for encrypt_with_aad functionality."""

    def test_encrypt_with_aad_success(self, mock_keyring_key, user_hash_1):
        """Test successful encryption with AAD binding."""
        plaintext = b"Memory chunk content"
        aad = user_hash_1.encode()

        envelope = encrypt_with_aad(plaintext, aad, mock_keyring_key)

        # Verify envelope structure
        assert "key_id" in envelope
        assert "nonce" in envelope
        assert "ciphertext" in envelope
        assert "tag" in envelope
        assert "aad_bound_to" in envelope

        # Verify key_id matches
        assert envelope["key_id"] == "key-001"

        # Verify AAD binding captured in audit trail
        assert envelope["aad_bound_to"] == user_hash_1

    def test_encrypt_with_aad_produces_different_ciphertexts(self, mock_keyring_key, user_hash_1):
        """Test that encryption produces different ciphertexts (due to random nonce)."""
        plaintext = b"Same content"
        aad = user_hash_1.encode()

        envelope1 = encrypt_with_aad(plaintext, aad, mock_keyring_key)
        envelope2 = encrypt_with_aad(plaintext, aad, mock_keyring_key)

        # Nonces should be different (random)
        assert envelope1["nonce"] != envelope2["nonce"]

        # Ciphertexts should be different
        assert envelope1["ciphertext"] != envelope2["ciphertext"]

    def test_encrypt_with_aad_empty_plaintext(self, mock_keyring_key, user_hash_1):
        """Test encryption of empty plaintext."""
        plaintext = b""
        aad = user_hash_1.encode()

        envelope = encrypt_with_aad(plaintext, aad, mock_keyring_key)

        assert "ciphertext" in envelope
        assert "tag" in envelope

    def test_encrypt_with_aad_large_plaintext(self, mock_keyring_key, user_hash_1):
        """Test encryption of large plaintext."""
        plaintext = b"x" * 100000  # 100 KB
        aad = user_hash_1.encode()

        envelope = encrypt_with_aad(plaintext, aad, mock_keyring_key)

        assert "ciphertext" in envelope
        assert "tag" in envelope


class TestAADDecryption:
    """Tests for decrypt_with_aad functionality."""

    def test_decrypt_with_aad_matching_aad(self, mock_keyring_key, user_hash_1):
        """Test successful decryption when AAD matches."""
        plaintext = b"Secret memory chunk"
        aad = user_hash_1.encode()

        # Encrypt
        envelope = encrypt_with_aad(plaintext, aad, mock_keyring_key)

        # Decrypt with same AAD
        decrypted = decrypt_with_aad(envelope, aad, keyring_get_fn=Mock(return_value=mock_keyring_key))

        assert decrypted == plaintext

    def test_decrypt_with_aad_mismatched_aad_fails(self, mock_keyring_key, user_hash_1, user_hash_2):
        """Test that decryption fails when AAD doesn't match (fail-closed)."""
        plaintext = b"Secret memory chunk"
        aad1 = user_hash_1.encode()
        aad2 = user_hash_2.encode()

        # Encrypt with user_hash_1
        envelope = encrypt_with_aad(plaintext, aad1, mock_keyring_key)

        # Try to decrypt with user_hash_2
        with pytest.raises(ValueError, match="Decryption with AAD validation failed"):
            decrypt_with_aad(envelope, aad2, keyring_get_fn=Mock(return_value=mock_keyring_key))

    def test_decrypt_with_aad_missing_key_fails(self, mock_keyring_key, user_hash_1):
        """Test that decryption fails when key is not found."""
        plaintext = b"Secret"
        aad = user_hash_1.encode()

        envelope = encrypt_with_aad(plaintext, aad, mock_keyring_key)

        # Simulate key not found
        with pytest.raises(ValueError, match="Key not found"):
            decrypt_with_aad(envelope, aad, keyring_get_fn=Mock(return_value=None))

    def test_decrypt_with_aad_corrupted_ciphertext_fails(self, mock_keyring_key, user_hash_1):
        """Test that decryption fails on corrupted ciphertext."""
        plaintext = b"Secret"
        aad = user_hash_1.encode()

        envelope = encrypt_with_aad(plaintext, aad, mock_keyring_key)

        # Corrupt the ciphertext
        import base64

        corrupt_ciphertext = base64.b64encode(b"corrupted").decode()
        envelope["ciphertext"] = corrupt_ciphertext

        with pytest.raises(ValueError):
            decrypt_with_aad(envelope, aad, keyring_get_fn=Mock(return_value=mock_keyring_key))

    def test_decrypt_with_aad_corrupted_tag_fails(self, mock_keyring_key, user_hash_1):
        """Test that decryption fails on corrupted tag (AAD validation)."""
        plaintext = b"Secret"
        aad = user_hash_1.encode()

        envelope = encrypt_with_aad(plaintext, aad, mock_keyring_key)

        # Corrupt the tag
        import base64

        corrupt_tag = base64.b64encode(b"corrupted_tag_12").decode()
        envelope["tag"] = corrupt_tag

        with pytest.raises(ValueError):
            decrypt_with_aad(envelope, aad, keyring_get_fn=Mock(return_value=mock_keyring_key))


class TestAADDefenseInDepth:
    """Tests for AAD defense-in-depth (RLS + AAD combination)."""

    def test_cross_user_attack_prevented(self, mock_keyring_key, user_hash_1, user_hash_2):
        """
        Test that a malicious actor cannot access another user's encrypted data.

        Scenario: Attacker obtains User1's encrypted chunk and tries to decrypt it as User2.
        Expected: Decryption fails (fail-closed).
        """
        # User 1 encrypts their data
        user1_data = b"User 1's private memory"
        aad1 = user_hash_1.encode()
        user1_envelope = encrypt_with_aad(user1_data, aad1, mock_keyring_key)

        # Attacker (User 2) tries to decrypt
        aad2 = user_hash_2.encode()
        with pytest.raises(ValueError, match="Decryption with AAD validation failed"):
            decrypt_with_aad(user1_envelope, aad2, keyring_get_fn=Mock(return_value=mock_keyring_key))

    def test_aad_prevents_envelope_tampering(self, mock_keyring_key, user_hash_1):
        """Test that tampering with envelope fields is detected."""
        plaintext = b"Original data"
        aad = user_hash_1.encode()

        envelope = encrypt_with_aad(plaintext, aad, mock_keyring_key)

        # Try various tampering attacks
        import base64

        # Tampering 1: Modify the nonce
        tampered1 = envelope.copy()
        tampered1["nonce"] = base64.b64encode(b"different_nonce1").decode()
        with pytest.raises(ValueError):
            decrypt_with_aad(tampered1, aad, keyring_get_fn=Mock(return_value=mock_keyring_key))

        # Tampering 2: Modify the ciphertext
        tampered2 = envelope.copy()
        original_ct = base64.b64decode(envelope["ciphertext"])
        modified_ct = bytes([original_ct[0] ^ 0xFF] + list(original_ct[1:]))  # Flip first byte
        tampered2["ciphertext"] = base64.b64encode(modified_ct).decode()
        with pytest.raises(ValueError):
            decrypt_with_aad(tampered2, aad, keyring_get_fn=Mock(return_value=mock_keyring_key))

        # Tampering 3: Swap tag
        tampered3 = envelope.copy()
        tampered3["tag"] = base64.b64encode(b"forged_tag______").decode()
        with pytest.raises(ValueError):
            decrypt_with_aad(tampered3, aad, keyring_get_fn=Mock(return_value=mock_keyring_key))


class TestAADUtilities:
    """Tests for AAD utility functions."""

    def test_get_aad_from_user_hash_string(self, user_hash_1):
        """Test conversion of user_hash string to bytes."""
        aad = get_aad_from_user_hash(user_hash_1)
        assert isinstance(aad, bytes)
        assert aad == user_hash_1.encode()

    def test_get_aad_from_user_hash_bytes(self, user_hash_1):
        """Test conversion when already bytes."""
        user_hash_bytes = user_hash_1.encode()
        aad = get_aad_from_user_hash(user_hash_bytes)
        assert aad == user_hash_bytes

    def test_compute_aad_digest_consistency(self, user_hash_1):
        """Test that AAD digest is consistent for same input."""
        aad = user_hash_1.encode()
        digest1 = _compute_aad_digest(aad)
        digest2 = _compute_aad_digest(aad)
        assert digest1 == digest2

    def test_compute_aad_digest_different_for_different_input(self, user_hash_1, user_hash_2):
        """Test that AAD digest differs for different inputs."""
        aad1 = user_hash_1.encode()
        aad2 = user_hash_2.encode()
        digest1 = _compute_aad_digest(aad1)
        digest2 = _compute_aad_digest(aad2)
        assert digest1 != digest2


class TestAADRoundTrip:
    """Tests for full encrypt/decrypt round trips."""

    @pytest.mark.parametrize(
        "data",
        [
            b"Short text",
            b"x" * 10000,
            b"",
            b"\x00\x01\x02\x03",
            "Unicode: \u4e2d\u6587 \u0627\u0644\u0639\u0631\u0628\u064a\u0629".encode(),
        ],
    )
    def test_roundtrip_various_data(self, data, mock_keyring_key, user_hash_1):
        """Test encrypt/decrypt round trip with various data types."""
        aad = user_hash_1.encode()

        envelope = encrypt_with_aad(data, aad, mock_keyring_key)
        decrypted = decrypt_with_aad(envelope, aad, keyring_get_fn=Mock(return_value=mock_keyring_key))

        assert decrypted == data

    def test_roundtrip_multiple_users(self, mock_keyring_key, user_hash_1, user_hash_2):
        """Test that multiple users' data remains isolated through round trips."""
        plaintext1 = b"User 1 data"
        plaintext2 = b"User 2 data"
        aad1 = user_hash_1.encode()
        aad2 = user_hash_2.encode()

        envelope1 = encrypt_with_aad(plaintext1, aad1, mock_keyring_key)
        envelope2 = encrypt_with_aad(plaintext2, aad2, mock_keyring_key)

        # Each user can decrypt their own data
        assert decrypt_with_aad(envelope1, aad1, keyring_get_fn=Mock(return_value=mock_keyring_key)) == plaintext1
        assert decrypt_with_aad(envelope2, aad2, keyring_get_fn=Mock(return_value=mock_keyring_key)) == plaintext2

        # Cross-user decryption fails
        with pytest.raises(ValueError):
            decrypt_with_aad(envelope1, aad2, keyring_get_fn=Mock(return_value=mock_keyring_key))
        with pytest.raises(ValueError):
            decrypt_with_aad(envelope2, aad1, keyring_get_fn=Mock(return_value=mock_keyring_key))


class TestAADBackwardCompatibility:
    """Tests to ensure AAD functions don't break existing non-AAD encryption."""

    def test_existing_encrypt_still_works(self, mock_keyring_key):
        """Test that original encrypt() function still works."""
        from src.crypto.envelope import encrypt

        plaintext = b"Test data"
        envelope = encrypt(plaintext, mock_keyring_key)

        assert "key_id" in envelope
        assert "nonce" in envelope
        assert "ciphertext" in envelope
        assert "tag" in envelope
        # AAD functions should NOT be present in non-AAD envelope
        assert "aad_bound_to" not in envelope

    def test_existing_decrypt_still_works(self, mock_keyring_key):
        """Test that original decrypt() function still works."""
        from src.crypto.envelope import decrypt, encrypt

        plaintext = b"Test data"
        envelope = encrypt(plaintext, mock_keyring_key)
        decrypted = decrypt(envelope, keyring_get_fn=Mock(return_value=mock_keyring_key))

        assert decrypted == plaintext
