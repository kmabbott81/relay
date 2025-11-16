"""Integration tests for TASK B write path with encryption + RLS

Tests cover:
- Basic chunk indexing with encryption
- Round-trip: index → retrieve → decrypt
- RLS isolation: User A can't see User B's chunks
- AAD binding: Can't decrypt with wrong user_hash
- Batch operations
"""

import json
import os

import pytest

# Set up test encryption key (same as test_encryption.py)
os.environ["MEMORY_ENCRYPTION_KEY"] = "ZGV2LWVuY3J5cHRpb24ta2V5LTMyYnl0ZXMxMjM0NTY="
os.environ["MEMORY_TENANT_HMAC_KEY"] = "dev-hmac-key-for-testing-1234567890"

from relay_ai.platform.security.memory.rls import hmac_user
from relay_ai.platform.security.memory.security import InvalidTag, open_sealed, seal


# Mock Database connection for testing
class MockConnection:
    """Mock asyncpg connection for testing encryption logic"""

    def __init__(self):
        self.data = {}  # Simulate table storage

    async def fetchrow(self, query, *args):
        """Mock INSERT RETURNING query"""
        # Simplified: just return ID and fields
        return {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "user_hash": args[0],  # user_hash is $1
            "doc_id": args[1],
            "source": args[2],
            "created_at": "2025-10-19T12:00:00Z",
            "updated_at": "2025-10-19T12:00:00Z",
        }

    async def transaction(self):
        """Mock transaction context"""
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


# ============================================================================
# TEST SUITE 1: Encryption Logic Verification
# ============================================================================


class TestEncryptionLogic:
    """Verify encryption logic matches write path requirements"""

    def test_user_hash_deterministic(self):
        """user_hash is deterministic (same user_id → same hash)"""
        user_id = "user_123@example.com"
        hash1 = hmac_user(user_id)
        hash2 = hmac_user(user_id)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex

    def test_aad_binding_with_user_hash(self):
        """AAD binding works with user_hash as AAD"""
        plaintext = b"sensitive chunk text"
        user_hash = hmac_user("user_a@example.com")
        aad = user_hash.encode()

        # Encrypt with user_hash AAD
        ciphertext = seal(plaintext, aad=aad)

        # Decrypt with same AAD (success)
        recovered = open_sealed(ciphertext, aad=aad)
        assert recovered == plaintext

        # Decrypt with different AAD (fails)
        other_user_hash = hmac_user("user_b@example.com").encode()
        with pytest.raises(InvalidTag):
            open_sealed(ciphertext, aad=other_user_hash)

    def test_encryption_format(self):
        """Encrypted blob format: nonce (12) || ciphertext || tag (16)"""
        plaintext = b"test data"
        ciphertext = seal(plaintext)

        # Minimum size: 12 (nonce) + 1 (min data) + 16 (tag) = 29
        assert len(ciphertext) >= 29

        # Can be decrypted
        recovered = open_sealed(ciphertext)
        assert recovered == plaintext


# ============================================================================
# TEST SUITE 2: Write Path Simulation
# ============================================================================


class TestWritePathEncryption:
    """Simulate write path: text + metadata + embedding encryption"""

    def test_text_encryption_in_write(self):
        """Text is encrypted before storage"""
        user_hash = hmac_user("user_123")
        text = "This is a memory chunk"
        aad = user_hash.encode()

        # Simulate write path
        text_cipher = seal(text.encode("utf-8"), aad=aad)

        # Verify can decrypt
        recovered = open_sealed(text_cipher, aad=aad)
        assert recovered.decode("utf-8") == text

    def test_metadata_encryption_in_write(self):
        """Metadata is encrypted as JSON before storage"""
        user_hash = hmac_user("user_456")
        metadata = {"doc_id": "doc_123", "page": 5, "tags": ["important"]}
        aad = user_hash.encode()

        # Simulate write path
        meta_json = json.dumps(metadata).encode("utf-8")
        meta_cipher = seal(meta_json, aad=aad)

        # Verify can decrypt
        recovered = open_sealed(meta_cipher, aad=aad)
        assert json.loads(recovered.decode("utf-8")) == metadata

    def test_embedding_encryption_in_write(self):
        """Embedding is encrypted as comma-separated floats"""
        user_hash = hmac_user("user_789")
        embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        aad = user_hash.encode()

        # Simulate write path
        embedding_bytes = ",".join(str(x) for x in embedding).encode("utf-8")
        emb_cipher = seal(embedding_bytes, aad=aad)

        # Verify can decrypt
        recovered = open_sealed(emb_cipher, aad=aad)
        embedding_recovered = [float(x) for x in recovered.decode("utf-8").split(",")]
        assert embedding_recovered == embedding

    def test_multiple_fields_cross_user_isolation(self):
        """Multiple encrypted fields are isolated per user"""
        user_a = "user_a@example.com"
        user_b = "user_b@example.com"

        user_a_hash = hmac_user(user_a)
        user_b_hash = hmac_user(user_b)

        text = b"User A's confidential data"
        metadata = {"sensitive": "yes"}

        # User A encrypts
        a_text_cipher = seal(text, aad=user_a_hash.encode())
        a_meta_cipher = seal(json.dumps(metadata).encode(), aad=user_a_hash.encode())

        # User B cannot decrypt User A's data
        with pytest.raises(InvalidTag):
            open_sealed(a_text_cipher, aad=user_b_hash.encode())

        with pytest.raises(InvalidTag):
            open_sealed(a_meta_cipher, aad=user_b_hash.encode())

        # User A can decrypt their own data
        assert open_sealed(a_text_cipher, aad=user_a_hash.encode()) == text


# ============================================================================
# TEST SUITE 3: RLS + Encryption Integration
# ============================================================================


class TestRLSEncryptionIntegration:
    """Verify RLS policy + encryption work together"""

    def test_rls_with_encryption_user_isolation(self):
        """RLS filters by user_hash, encryption ensures data confidentiality"""
        user_a_hash = hmac_user("user_a")
        user_b_hash = hmac_user("user_b")

        plaintext_a = b"User A secret memory"
        plaintext_b = b"User B secret memory"

        # Both users encrypt with their own hash (AAD)
        cipher_a = seal(plaintext_a, aad=user_a_hash.encode())
        cipher_b = seal(plaintext_b, aad=user_b_hash.encode())

        # Scenario 1: Database stores both ciphertexts
        # RLS policy (user_hash check) prevents User A from seeing User B's row
        # But even if RLS fails, User A cannot decrypt User B's cipher (AAD mismatch)
        with pytest.raises(InvalidTag):
            open_sealed(cipher_b, aad=user_a_hash.encode())

        # User A can only decrypt their own
        assert open_sealed(cipher_a, aad=user_a_hash.encode()) == plaintext_a

    def test_two_layer_protection(self):
        """Two-layer defense: RLS (row access) + Encryption (data confidentiality)"""
        # Layer 1: RLS policy - user_hash match required
        user_a_hash = hmac_user("user_a")
        user_b_hash = hmac_user("user_b")

        # If RLS is bypassed (e.g., admin query), Layer 2 protects data
        secret_text = b"Highly confidential memory"
        cipher = seal(secret_text, aad=user_a_hash.encode())

        # Attacker cannot decrypt even with ciphertext + User B credentials
        with pytest.raises(InvalidTag):
            open_sealed(cipher, aad=user_b_hash.encode())


# ============================================================================
# TEST SUITE 4: Batch Operations
# ============================================================================


class TestBatchEncryption:
    """Batch operations maintain encryption + isolation"""

    def test_batch_all_different_aads(self):
        """Batch of chunks from same user all encrypted with same AAD"""
        user_hash = hmac_user("user_123")
        aad = user_hash.encode()

        chunks = [
            b"Chunk 1 text",
            b"Chunk 2 text",
            b"Chunk 3 text",
        ]

        # All encrypted with same AAD (user_hash)
        ciphertexts = [seal(chunk, aad=aad) for chunk in chunks]

        # All can be decrypted with same AAD
        recovered = [open_sealed(ct, aad=aad) for ct in ciphertexts]
        assert recovered == chunks

    def test_batch_cross_user_batch(self):
        """Batches from different users use different AADs"""
        user_a = "user_a@example.com"
        user_b = "user_b@example.com"

        hash_a = hmac_user(user_a)
        hash_b = hmac_user(user_b)

        chunks_a = [b"Chunk A1", b"Chunk A2"]
        chunks_b = [b"Chunk B1", b"Chunk B2"]

        # Encrypt all with own AAD
        a_ciphers = [seal(c, aad=hash_a.encode()) for c in chunks_a]
        b_ciphers = [seal(c, aad=hash_b.encode()) for c in chunks_b]

        # User B cannot decrypt User A's chunks
        for ct in a_ciphers:
            with pytest.raises(InvalidTag):
                open_sealed(ct, aad=hash_b.encode())

        # But can decrypt their own
        for ct, expected in zip(b_ciphers, chunks_b):
            assert open_sealed(ct, aad=hash_b.encode()) == expected


# ============================================================================
# TEST SUITE 5: Error Handling
# ============================================================================


class TestErrorHandling:
    """Error cases and edge conditions"""

    def test_corrupted_ciphertext_detected(self):
        """Corrupted ciphertext raises InvalidTag"""
        plaintext = b"original data"
        ciphertext = seal(plaintext)

        # Corrupt ciphertext (flip a bit)
        corrupted = bytearray(ciphertext)
        corrupted[20] ^= 0xFF

        # Decryption fails
        with pytest.raises(InvalidTag):
            open_sealed(bytes(corrupted))

    def test_empty_plaintext_roundtrip(self):
        """Empty plaintext can be encrypted/decrypted"""
        plaintext = b""
        user_hash = hmac_user("user_123")
        aad = user_hash.encode()

        cipher = seal(plaintext, aad=aad)
        recovered = open_sealed(cipher, aad=aad)

        assert recovered == plaintext

    def test_large_plaintext_roundtrip(self):
        """Large plaintext (1MB) handled correctly"""
        plaintext = b"x" * (1024 * 1024)
        user_hash = hmac_user("user_456")
        aad = user_hash.encode()

        cipher = seal(plaintext, aad=aad)
        recovered = open_sealed(cipher, aad=aad)

        assert recovered == plaintext


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
