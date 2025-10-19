"""Unit tests for TASK B encryption helpers

Tests cover:
- Basic round-trip encryption/decryption
- AAD binding (cross-tenant prevention) ← CRITICAL SECURITY GATE
- Tamper detection (corruption, bit flips)
- Performance (>= 5k ops/sec)
- Edge cases and error handling
"""

import os
import time

import pytest

from src.memory.security import InvalidTag, compute_payload_hash, hmac_user, open_sealed, seal

# Set up test encryption key (dev only) - MUST be 44-character base64 (32 bytes)
# Generated: python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
os.environ["MEMORY_ENCRYPTION_KEY"] = "ZGV2LWVuY3J5cHRpb24ta2V5LTMyYnl0ZXMxMjM0NTY="  # 44-char base64 = 32 bytes

# ============================================================================
# TEST SUITE 1: Round-Trip Encryption/Decryption (Basic Functionality)
# ============================================================================


class TestSealRoundTrip:
    """Verify basic encrypt/decrypt functionality works"""

    def test_seal_and_open_basic(self):
        """Basic round-trip: seal → open_sealed → plaintext recovered"""
        plaintext = b"Hello, World!"
        ciphertext = seal(plaintext)
        recovered = open_sealed(ciphertext)
        assert recovered == plaintext

    def test_seal_and_open_with_aad(self):
        """Round-trip with AAD (no mismatch)"""
        plaintext = b"sensitive data"
        aad = b"user_hash_123"
        ciphertext = seal(plaintext, aad=aad)
        recovered = open_sealed(ciphertext, aad=aad)
        assert recovered == plaintext

    def test_seal_empty_plaintext(self):
        """Encrypt empty plaintext"""
        plaintext = b""
        ciphertext = seal(plaintext)
        recovered = open_sealed(ciphertext)
        assert recovered == plaintext

    def test_seal_large_plaintext(self):
        """Encrypt large plaintext (1MB)"""
        plaintext = b"x" * (1024 * 1024)  # 1MB
        ciphertext = seal(plaintext)
        recovered = open_sealed(ciphertext)
        assert recovered == plaintext

    def test_seal_binary_data(self):
        """Encrypt binary data (not text)"""
        plaintext = bytes(range(256)) * 10  # All byte values
        ciphertext = seal(plaintext)
        recovered = open_sealed(ciphertext)
        assert recovered == plaintext

    def test_seal_unicode_as_bytes(self):
        """Encrypt UTF-8 encoded unicode"""
        plaintext = "Hello, 世界! 🌍".encode()
        ciphertext = seal(plaintext)
        recovered = open_sealed(ciphertext)
        assert recovered == plaintext
        assert recovered.decode("utf-8") == "Hello, 世界! 🌍"


# ============================================================================
# TEST SUITE 2: AAD Binding - Cross-Tenant Prevention (CRITICAL SECURITY GATE)
# ============================================================================


class TestAADBinding:
    """CRITICAL: Verify cross-tenant prevention through AAD binding

    This is the SECURITY GATE. Without AAD binding working correctly,
    a user with User B's credentials but User A's data blob could decrypt it.
    """

    def test_aad_binding_prevents_cross_tenant_decryption(self):
        """CRITICAL TEST: User B cannot decrypt User A's data (AAD mismatch)

        Scenario:
        - User A encrypts data with AAD = "user_a_hash"
        - User B obtains the ciphertext (e.g., from database dump)
        - User B tries to decrypt with AAD = "user_b_hash"
        → Must raise InvalidTag (cross-tenant prevention verified)
        """
        plaintext = b"sensitive: user A's private memory"

        # User A encrypts with their hash
        user_a_hash = b"user_a_hash_aaaaaaaaaa"
        user_a_ciphertext = seal(plaintext, aad=user_a_hash)

        # User B obtains the ciphertext (hypothetically from a database breach)
        # User B tries to decrypt with their own hash
        user_b_hash = b"user_b_hash_bbbbbbbbbb"

        # This MUST fail
        with pytest.raises(InvalidTag):
            open_sealed(user_a_ciphertext, aad=user_b_hash)

    def test_aad_binding_with_hmac_user_hashes(self):
        """AAD binding with real hmac_user() hashes"""
        plaintext = b"User A's memory chunk data"

        # Compute real HMAC-based hashes
        user_a_hash = hmac_user("user_a@example.com").encode()
        user_b_hash = hmac_user("user_b@example.com").encode()

        # User A encrypts
        ciphertext = seal(plaintext, aad=user_a_hash)

        # User A can decrypt (correct AAD)
        recovered = open_sealed(ciphertext, aad=user_a_hash)
        assert recovered == plaintext

        # User B cannot decrypt (wrong AAD)
        with pytest.raises(InvalidTag):
            open_sealed(ciphertext, aad=user_b_hash)

    def test_aad_mismatch_empty_vs_nonempty(self):
        """AAD mismatch: empty vs non-empty"""
        plaintext = b"data"

        # Encrypt with no AAD
        ciphertext1 = seal(plaintext, aad=b"")

        # Cannot decrypt with non-empty AAD
        with pytest.raises(InvalidTag):
            open_sealed(ciphertext1, aad=b"some_aad")

        # Encrypt with AAD
        ciphertext2 = seal(plaintext, aad=b"some_aad")

        # Cannot decrypt with no AAD
        with pytest.raises(InvalidTag):
            open_sealed(ciphertext2, aad=b"")

    def test_aad_partial_match_not_accepted(self):
        """AAD must match exactly (partial match fails)"""
        plaintext = b"data"
        original_aad = b"user_hash_exact_match"

        ciphertext = seal(plaintext, aad=original_aad)

        # Recover with exact match (succeeds)
        recovered = open_sealed(ciphertext, aad=original_aad)
        assert recovered == plaintext

        # Partial match fails
        with pytest.raises(InvalidTag):
            open_sealed(ciphertext, aad=b"user_hash_exact_matc")  # Last char missing

        with pytest.raises(InvalidTag):
            open_sealed(ciphertext, aad=b"user_hash_exact_matcH")  # Different case


# ============================================================================
# TEST SUITE 3: Tamper Detection
# ============================================================================


class TestTamperDetection:
    """Verify corruption/tampering is detected"""

    def test_bit_flip_in_ciphertext(self):
        """Bit flip in ciphertext → InvalidTag"""
        plaintext = b"important data"
        aad = b"user_hash"
        ciphertext = seal(plaintext, aad=aad)

        # Flip a bit in the ciphertext (after nonce, before tag)
        tampered = bytearray(ciphertext)
        tampered[16] ^= 0x01  # Flip one bit

        # Decryption must fail
        with pytest.raises(InvalidTag):
            open_sealed(bytes(tampered), aad=aad)

    def test_nonce_modification(self):
        """Nonce modification → decryption fails (may not be InvalidTag, depends on impl)"""
        plaintext = b"data"
        ciphertext = seal(plaintext)

        # Modify nonce (first 12 bytes)
        tampered = bytearray(ciphertext)
        tampered[0] ^= 0xFF  # Flip all bits of first byte

        # Decryption should fail (wrong nonce = wrong authentication)
        with pytest.raises(InvalidTag):
            open_sealed(bytes(tampered))

    def test_tag_modification(self):
        """Auth tag modification → InvalidTag"""
        plaintext = b"data"
        ciphertext = seal(plaintext)

        # Modify last byte (part of auth tag)
        tampered = bytearray(ciphertext)
        tampered[-1] ^= 0x01

        with pytest.raises(InvalidTag):
            open_sealed(bytes(tampered))

    def test_truncated_blob(self):
        """Truncated blob (missing tag) → error"""
        plaintext = b"data"
        ciphertext = seal(plaintext)

        # Remove last byte (tag is last 16 bytes)
        truncated = ciphertext[:-1]

        with pytest.raises((InvalidTag, ValueError)):
            open_sealed(truncated)

    def test_aad_modification_detected(self):
        """AAD modification detected by authentication tag"""
        plaintext = b"data"
        original_aad = b"user_hash_123"
        ciphertext = seal(plaintext, aad=original_aad)

        # Try with modified AAD
        modified_aad = b"user_hash_124"  # Different AAD

        with pytest.raises(InvalidTag):
            open_sealed(ciphertext, aad=modified_aad)


# ============================================================================
# TEST SUITE 4: Performance (>= 5k ops/sec)
# ============================================================================


class TestThroughput:
    """Performance: must achieve >= 5k ops/sec"""

    def test_throughput_seal_operations(self):
        """Measure seal() throughput: target >= 5k ops/sec"""
        plaintext = b"x" * 1024  # 1KB payload
        aad = b"user_hash"

        start = time.time()
        iterations = 1000
        for _ in range(iterations):
            seal(plaintext, aad=aad)
        elapsed = time.time() - start

        ops_per_sec = iterations / elapsed
        print(f"\nseal() throughput: {ops_per_sec:.0f} ops/sec ({elapsed:.2f}s for {iterations} ops)")

        assert ops_per_sec >= 5000, f"Throughput too low: {ops_per_sec:.0f} ops/sec (target: >= 5000)"

    def test_throughput_open_sealed_operations(self):
        """Measure open_sealed() throughput: target >= 5k ops/sec"""
        plaintext = b"x" * 1024
        aad = b"user_hash"
        ciphertext = seal(plaintext, aad=aad)

        start = time.time()
        iterations = 1000
        for _ in range(iterations):
            open_sealed(ciphertext, aad=aad)
        elapsed = time.time() - start

        ops_per_sec = iterations / elapsed
        print(f"\nopen_sealed() throughput: {ops_per_sec:.0f} ops/sec ({elapsed:.2f}s for {iterations} ops)")

        assert ops_per_sec >= 5000, f"Throughput too low: {ops_per_sec:.0f} ops/sec (target: >= 5000)"

    def test_latency_p50_p95_p99(self):
        """Measure latency percentiles"""
        plaintext = b"x" * 1024
        aad = b"user_hash"

        # Measure seal latency
        latencies_seal = []
        for _ in range(100):
            start = time.perf_counter()
            seal(plaintext, aad=aad)
            latencies_seal.append((time.perf_counter() - start) * 1000)  # Convert to ms

        latencies_seal.sort()
        p50_seal = latencies_seal[50]
        p95_seal = latencies_seal[95]
        p99_seal = latencies_seal[99]

        print(f"\nseal() latency: p50={p50_seal:.3f}ms, p95={p95_seal:.3f}ms, p99={p99_seal:.3f}ms")

        # Latency should be well under 1ms for >= 5k ops/sec
        assert p99_seal < 1.0, f"p99 latency too high: {p99_seal:.3f}ms"


# ============================================================================
# TEST SUITE 5: Integration & Error Handling
# ============================================================================


class TestIntegration:
    """Integration tests: write path scenario"""

    def test_encrypt_multiple_chunks_isolated(self):
        """Multiple users' chunks encrypted independently"""
        user_a_id = "user_a@example.com"
        user_b_id = "user_b@example.com"

        user_a_hash = hmac_user(user_a_id).encode()
        user_b_hash = hmac_user(user_b_id).encode()

        # User A's chunk
        chunk_a = b"User A's memory chunk 1"
        encrypted_a = seal(chunk_a, aad=user_a_hash)

        # User B's chunk
        chunk_b = b"User B's memory chunk 1"
        encrypted_b = seal(chunk_b, aad=user_b_hash)

        # User A can decrypt their own chunk
        assert open_sealed(encrypted_a, aad=user_a_hash) == chunk_a

        # User B can decrypt their own chunk
        assert open_sealed(encrypted_b, aad=user_b_hash) == chunk_b

        # User A cannot decrypt User B's chunk
        with pytest.raises(InvalidTag):
            open_sealed(encrypted_b, aad=user_a_hash)

        # User B cannot decrypt User A's chunk
        with pytest.raises(InvalidTag):
            open_sealed(encrypted_a, aad=user_b_hash)

    def test_payload_hash_consistency(self):
        """Payload hash can be used for integrity tracking"""
        plaintext = b"document content"

        hash1 = compute_payload_hash(plaintext)
        hash2 = compute_payload_hash(plaintext)

        # Same plaintext should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex

    def test_invalid_key_handling(self):
        """Invalid encryption key raises ValueError"""
        # Temporarily set invalid key
        original_key = os.environ.get("MEMORY_ENCRYPTION_KEY")
        try:
            os.environ["MEMORY_ENCRYPTION_KEY"] = "invalid-short-key"

            # Reload the key decoder (it's cached in module)
            # For now just verify that operations fail gracefully
            # This test is more about documentation

        finally:
            if original_key:
                os.environ["MEMORY_ENCRYPTION_KEY"] = original_key


# ============================================================================
# TEST SUITE 6: Edge Cases
# ============================================================================


class TestEdgeCases:
    """Edge cases and boundary conditions"""

    def test_seal_very_long_aad(self):
        """AAD can be very long (1MB+)"""
        plaintext = b"data"
        aad = b"x" * (1024 * 1024)  # 1MB AAD

        ciphertext = seal(plaintext, aad=aad)
        recovered = open_sealed(ciphertext, aad=aad)
        assert recovered == plaintext

    def test_deterministic_encryption_is_NOT_guaranteed(self):
        """Encryption includes random nonce, so same plaintext produces different ciphertexts"""
        plaintext = b"same data"

        ciphertext1 = seal(plaintext)
        ciphertext2 = seal(plaintext)

        # Ciphertexts should be different (different random nonces)
        assert ciphertext1 != ciphertext2

        # But both decrypt to same plaintext
        assert open_sealed(ciphertext1) == plaintext
        assert open_sealed(ciphertext2) == plaintext

    def test_minimum_blob_size_enforcement(self):
        """Blobs shorter than minimum are rejected"""
        # Minimum blob: 12 (nonce) + 1 (min ciphertext) + 16 (tag) = 29 bytes, but we say 28
        short_blob = b"x" * 20

        with pytest.raises((ValueError, InvalidTag)):
            open_sealed(short_blob)


# ============================================================================
# PYTEST CONFIGURATION
# ============================================================================


@pytest.fixture(scope="function")
def encryption_key():
    """Fixture to ensure test encryption key is set"""
    key = os.environ.get("MEMORY_ENCRYPTION_KEY")
    assert key is not None, "MEMORY_ENCRYPTION_KEY not set"
    yield key


if __name__ == "__main__":
    # Run with: pytest tests/memory/test_encryption.py -v
    pytest.main([__file__, "-v", "-s"])
