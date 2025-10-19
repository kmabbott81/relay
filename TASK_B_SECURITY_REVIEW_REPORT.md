# TASK B ENCRYPTION SECURITY REVIEW REPORT

**Review Date:** 2025-10-19
**Reviewer:** Security Review Agent (repo-guardian)
**Scope:** TASK B - Encryption Helpers Implementation (`src/memory/security.py`)
**Status:** PRE-IMPLEMENTATION SECURITY SPECIFICATION REVIEW

---

## EXECUTIVE SUMMARY

### Security Posture: SPECIFICATION APPROVED WITH CRITICAL REQUIREMENTS

**File Status:** `src/memory/security.py` does NOT exist yet (implementation pending)

**Decision:** SECURITY SPECIFICATION APPROVED for implementation

**Critical Blockers for Final Approval:** NONE at specification level

**Required Before Merge:**
1. Implementation must match specification exactly
2. All unit tests passing (20+ test cases)
3. AAD binding tests MUST demonstrate cross-tenant decryption prevention
4. Tamper detection tests MUST fail on 1-bit corruption
5. Performance tests MUST achieve >= 5k ops/sec throughput
6. No hardcoded keys or secrets in code
7. Fail-closed error handling implemented

---

## SPECIFICATION ANALYSIS

### THREE REQUIRED FUNCTIONS

#### 1. `hmac_user(user_id: str) -> str`

**Status:** PARTIALLY IMPLEMENTED in `src/memory/rls.py` (lines 28-48)

**Security Assessment:** APPROVED

**Findings:**
- Implementation already exists in `src/memory/rls.py`
- Uses HMAC-SHA256 with `MEMORY_TENANT_HMAC_KEY`
- Returns 64-character hex string (deterministic)
- Comprehensive tests exist in `tests/memory/test_rls_isolation.py`

**Recommendation:**
- REUSE existing `hmac_user()` from `src/memory/rls.py`
- Import in `src/memory/security.py` for consistency:
  ```python
  from src.memory.rls import hmac_user
  ```

**Security Verification:**
- Deterministic: PASS (test line 37-42)
- Different users produce different hashes: PASS (test line 44-48)
- Correct format (64-char hex): PASS (test line 50-54)
- Uses correct key: PASS (test line 56-64)

---

#### 2. `seal(plaintext: bytes, aad: bytes = b"") -> bytes`

**Status:** NOT IMPLEMENTED (to be created)

**Reference Implementation:** Existing `src/crypto/envelope.py` provides similar functionality

**Critical Security Requirements:**

1. **Algorithm:** AES-256-GCM (APPROVED)
   - Use `cryptography.hazmat.primitives.ciphers.aead.AESGCM`
   - Cryptography library version: 45.0.7 (CURRENT, SECURE)

2. **Key Management:**
   ```python
   MEMORY_ENCRYPTION_KEY = os.getenv("MEMORY_ENCRYPTION_KEY")
   if not MEMORY_ENCRYPTION_KEY:
       raise ValueError("MEMORY_ENCRYPTION_KEY must be set")

   K_ENC = base64.b64decode(MEMORY_ENCRYPTION_KEY)
   if len(K_ENC) != 32:
       raise ValueError("Key must be 32 bytes (AES-256)")
   ```
   - MUST use environment variable (no hardcoded keys)
   - MUST validate key length (32 bytes for AES-256)
   - MUST fail-closed on missing key (ValueError, not fallback)

3. **Nonce Generation:**
   ```python
   nonce = os.urandom(12)  # 96 bits (NIST recommended for GCM)
   ```
   - MUST use cryptographically secure random (os.urandom)
   - MUST be 12 bytes (96 bits) as per NIST SP 800-38D
   - MUST be unique per encryption (never reuse)

4. **AAD Binding (CRITICAL):**
   ```python
   ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
   ```
   - AAD MUST be user_hash (tenant isolation enforcement)
   - AAD mismatch MUST cause decryption failure (prevents cross-tenant attacks)
   - AAD binding is PRIMARY defense against data exfiltration

5. **Output Format:**
   ```python
   return nonce + ciphertext  # Format: nonce(12) || ct || tag(16)
   ```
   - Nonce: 12 bytes (first)
   - Ciphertext: variable length
   - Auth tag: 16 bytes (last, embedded in AESGCM output)

**Comparison with Existing `src/crypto/envelope.py`:**

| Aspect | envelope.py | TASK B seal() | Security Impact |
|--------|-------------|---------------|-----------------|
| Algorithm | AES-256-GCM | AES-256-GCM | PASS - Same |
| Nonce | 12 bytes (os.urandom) | 12 bytes (os.urandom) | PASS - Correct |
| AAD | None (hardcoded) | user_hash (required) | CRITICAL - TASK B is MORE SECURE |
| Key Management | Keyring (file-based) | Environment variable | Different approach, both valid |
| Output Format | JSON envelope | Binary blob | Different use case |
| Tag Handling | Separated | Concatenated | Both valid |

**SECURITY VERDICT:**
- `envelope.py` is secure for its use case (OAuth tokens, file encryption)
- TASK B requirements are MORE STRICT due to AAD binding (tenant isolation)
- TASK B implementation MUST NOT reuse `envelope.py` due to different AAD requirements

---

#### 3. `open_sealed(blob: bytes, aad: bytes = b"") -> bytes`

**Status:** NOT IMPLEMENTED (to be created)

**Critical Security Requirements:**

1. **Format Validation:**
   ```python
   if len(blob) < 28:  # 12 (nonce) + 0 (min plaintext) + 16 (tag)
       raise ValueError("Invalid ciphertext format")

   nonce = blob[:12]
   ciphertext = blob[12:]  # Includes embedded auth tag
   ```

2. **Decryption with AAD:**
   ```python
   try:
       plaintext = aesgcm.decrypt(nonce, ciphertext, aad)
       return plaintext
   except InvalidTag as e:
       logger.error("Decryption failed (AAD mismatch or tampering)")
       raise  # MUST NOT swallow exception
   ```

3. **Error Handling (CRITICAL):**
   - MUST raise `cryptography.exceptions.InvalidTag` on AAD mismatch
   - MUST raise `cryptography.exceptions.InvalidTag` on tampered ciphertext
   - MUST NOT return partial plaintext on failure
   - MUST NOT log plaintext or key material in errors
   - MUST fail-closed (no fallback to plaintext)

4. **AAD Verification:**
   - AAD MUST match the AAD used in `seal()`
   - Wrong user_hash MUST cause InvalidTag exception
   - This prevents User B from decrypting User A's data

---

## DEPENDENCY ANALYSIS

### Cryptography Library

**Installed Version:** `cryptography==45.0.7`

**Security Assessment:**
- Version: CURRENT (released 2024)
- Known Vulnerabilities: NONE (checked CVE database)
- Algorithm Support: AES-256-GCM (FIPS 140-2 approved)
- NIST SP 800-38D Compliant: YES

**Missing from requirements.txt:**
- `cryptography` is NOT listed in `requirements.txt`
- CRITICAL: MUST add to `requirements.txt` before merge:
  ```
  cryptography>=42.0.0  # AES-256-GCM for memory encryption
  ```

---

## ENVIRONMENT VARIABLE SECURITY

### Required Secrets

**From `.env.example`:** NO encryption keys defined yet

**Required Additions:**

```bash
# ============================================================================
# Memory Encryption (Sprint 62 - R1 Phase 1 TASK B)
# ============================================================================

# Memory encryption key (32-byte base64-encoded)
# Used for AES-256-GCM encryption of memory chunks
# Generate with: python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
MEMORY_ENCRYPTION_KEY=

# Memory tenant HMAC key (32-byte base64 or raw string)
# Used for deterministic user_hash computation (RLS isolation)
# Generate with: python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
MEMORY_TENANT_HMAC_KEY=
```

**Security Checklist:**
- [ ] Keys generated using cryptographically secure random (os.urandom)
- [ ] Keys are 32 bytes (256 bits) minimum
- [ ] Different keys for dev/staging/production
- [ ] Keys stored in secure secret manager (not committed to git)
- [ ] Keys rotated quarterly (MEMORY_ENCRYPTION_KEY)
- [ ] Keys rotated annually (MEMORY_TENANT_HMAC_KEY)
- [ ] .env.example contains NO real keys (only generation instructions)

---

## OWASP TOP 10 COMPLIANCE

### A02: Cryptographic Failures

**Specification Compliance:** PASS

**Evidence:**
- Uses industry-standard AES-256-GCM (NIST approved)
- 256-bit keys (exceeds 128-bit minimum)
- 96-bit nonces (NIST SP 800-38D recommended)
- Authenticated encryption with AAD (prevents tampering)
- Cryptographically secure random (os.urandom)
- No custom cryptography (uses cryptography library)

**Remaining Risks:**
- Plaintext embeddings in database (DOCUMENTED EXCEPTION)
- Compensating controls in place:
  1. RLS policy (tenant isolation)
  2. Encrypted database volume (TDE)
  3. Shadow backup (emb_cipher)
  4. Audit logging

---

### A01: Broken Access Control

**AAD Binding Enforcement:** CRITICAL CONTROL

**How AAD Prevents Cross-Tenant Access:**
1. User A encrypts with `seal(plaintext, aad=hash_a)`
2. Database stores ciphertext (no tenant info visible)
3. User B attempts: `open_sealed(ciphertext, aad=hash_b)`
4. AAD mismatch: `InvalidTag` exception raised
5. User B CANNOT decrypt User A's data

**Defense-in-Depth:**
- Layer 1: RLS policy (database-level isolation)
- Layer 2: AAD binding (cryptographic isolation)
- Layer 3: Audit logging (detection)

**Test Coverage Required:**
```python
def test_aad_binding_prevents_cross_tenant():
    """User B cannot decrypt User A's data"""
    user_hash_a = hmac_user("user_a@example.com")
    user_hash_b = hmac_user("user_b@example.com")

    plaintext = b"User A's sensitive memory"

    # User A encrypts
    ciphertext = seal(plaintext, aad=user_hash_a.encode())

    # User B tries to decrypt
    with pytest.raises(InvalidTag):
        open_sealed(ciphertext, aad=user_hash_b.encode())

    # CRITICAL: Must raise InvalidTag, not return plaintext
```

---

## SECURITY REVIEW CHECKLIST

### Cryptographic Implementation

- [ ] **Algorithm:** AES-256-GCM (not AES-128, DES, or 3DES)
- [ ] **Key Length:** 32 bytes (256 bits) validated
- [ ] **Nonce Generation:** os.urandom(12) - cryptographically secure
- [ ] **Nonce Uniqueness:** Different for each encryption (tested)
- [ ] **AAD Binding:** user_hash passed to encrypt/decrypt
- [ ] **Tag Verification:** GCM tag enforced (no manual comparison)
- [ ] **No Custom Crypto:** Uses cryptography library (not hand-rolled)

### Key Management

- [ ] **No Hardcoded Keys:** All keys from environment variables
- [ ] **Key Validation:** Length and format checked on load
- [ ] **Fail-Closed:** Missing key raises ValueError (no plaintext fallback)
- [ ] **Key Rotation:** Quarterly rotation strategy documented
- [ ] **Dual-Write Support:** OLD and NEW key support (for rotation)
- [ ] **No Key Logging:** Key material never logged or in exceptions

### Error Handling

- [ ] **InvalidTag Raised:** AAD mismatch raises exception (not swallowed)
- [ ] **Tamper Detection:** 1-bit corruption raises InvalidTag
- [ ] **No Plaintext Leakage:** Errors don't expose plaintext or keys
- [ ] **Fail-Closed:** All errors raise exceptions (no silent failures)
- [ ] **Audit Logging:** Decryption failures logged (without sensitive data)

### Testing Requirements

- [ ] **Round-Trip:** seal() -> open_sealed() restores plaintext
- [ ] **AAD Binding:** Wrong AAD raises InvalidTag (CRITICAL)
- [ ] **Tamper Detection:** Corrupted ciphertext raises InvalidTag
- [ ] **Nonce Uniqueness:** Same plaintext produces different ciphertexts
- [ ] **Performance:** >= 5k ops/sec (1000 iterations < 200ms)
- [ ] **Latency:** p95 < 1ms per operation
- [ ] **Edge Cases:** Empty plaintext, large plaintext (100KB+)

### Integration Security

- [ ] **RLS Context:** set_rls_context() applied before encryption
- [ ] **User Hash AAD:** user_hash used as AAD (not user_id)
- [ ] **Plaintext Embedding:** Stored separately for ANN (documented exception)
- [ ] **Shadow Backup:** emb_cipher stored for compliance
- [ ] **No Plaintext Fallback:** Missing cipher columns raise error

---

## VULNERABILITY ASSESSMENT

### CRITICAL (Must Fix Before Merge)

NONE at specification level.

**Implementation Phase Risks:**
1. **Nonce Reuse:** Using static/incremental nonces instead of random
   - Impact: CATASTROPHIC - breaks GCM security completely
   - Mitigation: MUST use os.urandom(12) for every encryption
   - Test: Verify two encryptions produce different nonces

2. **AAD Not Enforced:** Forgetting to pass user_hash as AAD
   - Impact: CRITICAL - cross-tenant decryption possible
   - Mitigation: MUST require aad parameter, raise if empty
   - Test: AAD mismatch MUST raise InvalidTag

3. **Swallowing InvalidTag:** Catching exception without re-raising
   - Impact: HIGH - tampered data accepted as valid
   - Mitigation: MUST propagate InvalidTag exceptions
   - Test: Verify exception reaches caller

4. **Hardcoded Keys:** Using dev keys in production code
   - Impact: CRITICAL - all data compromised
   - Mitigation: MUST use environment variables only
   - Test: Code review + grep for base64 strings

---

### HIGH (Must Fix Before Production)

1. **Missing cryptography in requirements.txt**
   - Impact: Deployment will fail in production
   - Mitigation: Add to requirements.txt immediately
   - Priority: BLOCKING for merge

2. **No Key Rotation Strategy**
   - Impact: Key compromise affects all historical data
   - Mitigation: Implement dual-write with OLD/NEW keys
   - Priority: Can be added in R1 Phase 2

3. **Plaintext Embeddings in Database**
   - Impact: Database admin can see vector data
   - Mitigation: Documented exception + compensating controls
   - Priority: R2 roadmap (homomorphic encryption)

---

### MEDIUM (Should Address)

1. **No Rate Limiting on Decryption**
   - Impact: Brute-force AAD guessing possible (theoretical)
   - Mitigation: Add rate limiting on decrypt failures
   - Priority: Sprint 63

2. **No Crypto Operation Audit Log**
   - Impact: Tampering attempts not monitored
   - Mitigation: Add logging with structured fields
   - Priority: Sprint 63

---

### LOW (Consider for Future)

1. **No Key Derivation Function**
   - Current: Direct use of environment variable
   - Improvement: Use PBKDF2/Argon2 for key derivation
   - Priority: R2 optimization

2. **No Hardware Security Module (HSM)**
   - Current: Keys in environment variables
   - Improvement: AWS KMS, Azure Key Vault, etc.
   - Priority: Enterprise deployment phase

---

## COMPLIANCE ASSESSMENT

### GDPR (General Data Protection Regulation)

**Article 32: Security of Processing**

Requirements:
- "Encryption of personal data" (TASK B provides this)
- "Ability to restore availability" (shadow backup: emb_cipher)
- "Regular testing of security" (unit tests + integration tests)

**Compliance Status:** PASS (when implemented)

**Evidence:**
- AES-256-GCM encryption of memory chunks
- Shadow backup for data recovery
- Comprehensive test suite
- Audit logging capability

---

### PCI-DSS (If Applicable)

**Requirement 3.4: Render PAN Unreadable**

TASK B does NOT handle payment card data directly.

If memory chunks contain PAN:
- Encryption: AES-256 (APPROVED for PCI-DSS)
- Key Management: Environment variables (need HSM for Level 1)
- Access Control: RLS + AAD binding (strong isolation)

**Recommendation:** Document that memory system should NOT store PAN.

---

### HIPAA (If Applicable)

**164.312(a)(2)(iv): Encryption and Decryption**

TASK B provides:
- Encryption at rest (memory_chunks table)
- Encryption in transit (TLS on database connection)
- Access controls (RLS + AAD binding)
- Audit logging (decryption failures)

**Compliance Status:** PASS (with TLS enforcement)

---

## PERFORMANCE SECURITY REVIEW

### Throughput Requirements

**Specification:** >= 5k ops/sec (seal operations)

**Security Implications:**
- AES-256-GCM is hardware-accelerated on modern CPUs (AES-NI)
- Expected performance: 50k-500k ops/sec (depending on hardware)
- 5k ops/sec is VERY CONSERVATIVE (easily achievable)

**Cryptography Library Benchmarks:**
- Cryptography 45.0.7 uses libcrypto (OpenSSL)
- AES-NI support: Automatic on x86_64
- Typical: 1-10 GB/sec throughput (hardware-dependent)

**Risk Assessment:** LOW (performance requirement easily met)

---

### Latency Requirements

**Specification:** p95 < 1ms per operation

**Security Implications:**
- Fast operations reduce DoS attack surface
- 1ms is achievable with AES-NI
- Without AES-NI: May need 2-5ms target

**Test Requirement:**
```python
def test_seal_latency_p95():
    """seal() p95 < 1ms"""
    import time
    plaintext = b"x" * 1024
    times = []

    for _ in range(1000):
        t0 = time.perf_counter()
        seal(plaintext, aad=b"user_hash")
        times.append((time.perf_counter() - t0) * 1000)  # ms

    p95 = np.percentile(times, 95)
    assert p95 < 1.0, f"Latency too high: p95={p95:.2f}ms"
```

**Risk Assessment:** LOW (hardware-dependent, but likely to pass)

---

## IMPLEMENTATION SECURITY GUIDANCE

### Recommended Implementation Structure

```python
"""
Memory encryption module using AES-256-GCM.

Sprint 62 / R1 Phase 1 TASK B

Provides:
- seal(plaintext, aad) -> AES-256-GCM encryption
- open_sealed(blob, aad) -> Decryption with tamper detection
- hmac_user(user_id) -> Deterministic user hash (from rls.py)

Security Properties:
- AES-256-GCM authenticated encryption
- AAD binding for tenant isolation
- Cryptographically secure nonces
- Fail-closed on missing keys
- Tamper detection via GCM auth tag
"""

import base64
import logging
import os
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

# Re-export hmac_user from rls module (DRY principle)
from src.memory.rls import hmac_user

logger = logging.getLogger(__name__)

# ============================================================================
# Key Management
# ============================================================================

def _load_encryption_key() -> bytes:
    """
    Load and validate MEMORY_ENCRYPTION_KEY from environment.

    Returns:
        32-byte encryption key

    Raises:
        ValueError: If key missing, invalid format, or wrong length
    """
    key_b64 = os.getenv("MEMORY_ENCRYPTION_KEY")

    if not key_b64:
        raise ValueError(
            "MEMORY_ENCRYPTION_KEY not set. "
            "Generate with: python -c \"import os, base64; "
            "print(base64.b64encode(os.urandom(32)).decode())\""
        )

    try:
        key = base64.b64decode(key_b64)
    except Exception as e:
        raise ValueError(f"MEMORY_ENCRYPTION_KEY invalid base64: {e}") from e

    if len(key) != 32:
        raise ValueError(
            f"MEMORY_ENCRYPTION_KEY must be 32 bytes (AES-256), got {len(key)} bytes"
        )

    return key


# Load key once at module import (fail-fast)
try:
    K_ENC = _load_encryption_key()
except ValueError as e:
    logger.critical(f"Encryption key loading failed: {e}")
    raise


# ============================================================================
# Encryption Functions
# ============================================================================

def seal(plaintext: bytes, aad: bytes = b"") -> bytes:
    """
    Encrypt plaintext with AES-256-GCM.

    Args:
        plaintext: Data to encrypt (bytes)
        aad: Additional Authenticated Data (MUST be user_hash for tenant isolation)

    Returns:
        Encrypted blob: nonce(12) || ciphertext || tag(16)

    Raises:
        ValueError: If encryption fails
        TypeError: If inputs are not bytes

    Security:
        - Uses cryptographically secure nonce (os.urandom)
        - AAD binding prevents cross-tenant decryption
        - GCM auth tag prevents tampering

    Example:
        >>> user_hash = hmac_user("user@example.com")
        >>> plaintext = b"sensitive memory chunk"
        >>> ciphertext = seal(plaintext, aad=user_hash.encode())
        >>> # Store ciphertext in database
    """
    if not isinstance(plaintext, bytes):
        raise TypeError(f"plaintext must be bytes, got {type(plaintext)}")

    if not isinstance(aad, bytes):
        raise TypeError(f"aad must be bytes, got {type(aad)}")

    # Generate cryptographically secure nonce (96 bits per NIST SP 800-38D)
    nonce = os.urandom(12)

    # Encrypt with AES-256-GCM (includes auth tag in output)
    aesgcm = AESGCM(K_ENC)
    try:
        ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        raise ValueError(f"Encryption failed: {e}") from e

    # Format: nonce || ciphertext (includes embedded 16-byte auth tag)
    blob = nonce + ciphertext

    logger.debug(
        f"Encrypted {len(plaintext)} bytes -> {len(blob)} bytes "
        f"(aad_len={len(aad)})"
    )

    return blob


def open_sealed(blob: bytes, aad: bytes = b"") -> bytes:
    """
    Decrypt ciphertext with AES-256-GCM.

    Args:
        blob: Encrypted data (nonce||ciphertext||tag from seal())
        aad: Additional Authenticated Data (MUST match seal() call)

    Returns:
        Decrypted plaintext (bytes)

    Raises:
        ValueError: If blob format invalid or key missing
        InvalidTag: If AAD mismatch, tampering detected, or wrong key
        TypeError: If inputs are not bytes

    Security:
        - AAD mismatch raises InvalidTag (cross-tenant protection)
        - Tampered ciphertext raises InvalidTag (integrity check)
        - No partial plaintext returned on failure (fail-closed)

    Example:
        >>> user_hash = hmac_user("user@example.com")
        >>> ciphertext = ...  # from database
        >>> plaintext = open_sealed(ciphertext, aad=user_hash.encode())
    """
    if not isinstance(blob, bytes):
        raise TypeError(f"blob must be bytes, got {type(blob)}")

    if not isinstance(aad, bytes):
        raise TypeError(f"aad must be bytes, got {type(aad)}")

    # Validate minimum length: 12 (nonce) + 16 (tag) = 28 bytes
    if len(blob) < 28:
        raise ValueError(
            f"Invalid ciphertext format: expected >= 28 bytes, got {len(blob)}"
        )

    # Extract nonce and ciphertext (includes auth tag)
    nonce = blob[:12]
    ciphertext = blob[12:]

    # Decrypt with AES-256-GCM (verifies auth tag automatically)
    aesgcm = AESGCM(K_ENC)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, aad)
    except InvalidTag as e:
        # AAD mismatch or tampering detected
        logger.warning(
            f"Decryption failed: AAD mismatch or tampering "
            f"(blob_size={len(blob)}, aad_len={len(aad)})"
        )
        raise  # Re-raise without modification (fail-closed)
    except Exception as e:
        logger.error(f"Decryption error: {e}")
        raise ValueError(f"Decryption failed: {e}") from e

    logger.debug(
        f"Decrypted {len(blob)} bytes -> {len(plaintext)} bytes "
        f"(aad_len={len(aad)})"
    )

    return plaintext


# ============================================================================
# Key Rotation Support (Future)
# ============================================================================

def _load_old_encryption_key() -> Optional[bytes]:
    """
    Load old encryption key for dual-write rotation support.

    Returns:
        32-byte old key, or None if not set

    Note:
        Set MEMORY_ENCRYPTION_KEY_OLD during key rotation:
        1. Set NEW key in MEMORY_ENCRYPTION_KEY
        2. Set OLD key in MEMORY_ENCRYPTION_KEY_OLD
        3. New writes use NEW key
        4. Reads try NEW key first, fall back to OLD key
        5. Background job re-encrypts with NEW key
        6. Remove OLD key once migration complete
    """
    key_b64 = os.getenv("MEMORY_ENCRYPTION_KEY_OLD")

    if not key_b64:
        return None

    try:
        key = base64.b64decode(key_b64)
        if len(key) != 32:
            logger.warning(f"MEMORY_ENCRYPTION_KEY_OLD wrong length: {len(key)}")
            return None
        return key
    except Exception as e:
        logger.warning(f"Failed to load old encryption key: {e}")
        return None


def open_sealed_with_rotation(blob: bytes, aad: bytes = b"") -> bytes:
    """
    Decrypt with support for key rotation (NEW key -> OLD key fallback).

    Args:
        blob: Encrypted data
        aad: Additional Authenticated Data

    Returns:
        Decrypted plaintext

    Raises:
        InvalidTag: If decryption fails with both NEW and OLD keys

    Note:
        This is for FUTURE use during key rotation.
        Default open_sealed() should be used unless rotating keys.
    """
    # Try NEW key first
    try:
        return open_sealed(blob, aad)
    except InvalidTag:
        pass  # Try old key

    # Try OLD key
    old_key = _load_old_encryption_key()
    if not old_key:
        raise InvalidTag("Decryption failed with current key and no old key available")

    # Decrypt with old key
    nonce = blob[:12]
    ciphertext = blob[12:]

    aesgcm = AESGCM(old_key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, aad)
        logger.info("Decrypted with OLD key (re-encryption recommended)")
        return plaintext
    except InvalidTag:
        raise InvalidTag("Decryption failed with both current and old keys")
```

---

## TESTING SECURITY REQUIREMENTS

### Minimum Test Coverage

**Required Test File:** `tests/memory/test_encryption.py`

**Minimum Test Cases (20+):**

1. **Round-Trip Tests (5)**
   - Basic seal/open with empty AAD
   - Seal/open with user_hash AAD
   - Empty plaintext
   - Large plaintext (100KB)
   - Unicode/binary plaintext

2. **AAD Binding Tests (5) - CRITICAL**
   - Correct AAD decrypts successfully
   - Wrong AAD raises InvalidTag
   - Empty AAD vs. non-empty AAD mismatch
   - Cross-tenant scenario (User A/B)
   - AAD case sensitivity

3. **Tamper Detection Tests (3)**
   - 1-bit corruption in ciphertext raises InvalidTag
   - Nonce corruption raises InvalidTag
   - Tag corruption raises InvalidTag

4. **Nonce Uniqueness Tests (2)**
   - Same plaintext produces different ciphertexts
   - Both decrypt correctly

5. **Performance Tests (2)**
   - Throughput >= 5k ops/sec
   - Latency p95 < 1ms

6. **Error Handling Tests (3)**
   - Missing MEMORY_ENCRYPTION_KEY raises ValueError
   - Invalid key format raises ValueError
   - Wrong key length raises ValueError

---

### Critical Test: AAD Binding

```python
def test_aad_binding_prevents_cross_tenant_decryption():
    """
    CRITICAL SECURITY TEST: AAD binding prevents cross-tenant access.

    Scenario:
    - User A encrypts memory chunk with their user_hash
    - User B attempts to decrypt with their user_hash
    - MUST raise InvalidTag (decryption fails)

    This test validates the PRIMARY security control for tenant isolation.
    """
    from src.memory.security import seal, open_sealed, hmac_user
    from cryptography.exceptions import InvalidTag
    import pytest

    # User A's identity
    user_a_id = "user_a@company.com"
    user_a_hash = hmac_user(user_a_id)

    # User B's identity
    user_b_id = "user_b@company.com"
    user_b_hash = hmac_user(user_b_id)

    # Verify users have different hashes
    assert user_a_hash != user_b_hash

    # User A encrypts sensitive memory
    plaintext = b"User A's confidential memory: project code names"
    ciphertext = seal(plaintext, aad=user_a_hash.encode())

    # User A can decrypt their own data
    decrypted_a = open_sealed(ciphertext, aad=user_a_hash.encode())
    assert decrypted_a == plaintext

    # User B CANNOT decrypt User A's data (AAD mismatch)
    with pytest.raises(InvalidTag):
        open_sealed(ciphertext, aad=user_b_hash.encode())

    # Even with correct ciphertext, wrong AAD prevents access
    # This is the CRYPTOGRAPHIC GUARANTEE of tenant isolation
```

---

## APPROVAL CRITERIA

### SECURITY_APPROVED: NO (Implementation Pending)

### BLOCKERS FOR APPROVAL:

1. **Implementation Phase:**
   - [ ] `src/memory/security.py` implemented (120 LOC)
   - [ ] All three functions present: seal, open_sealed, hmac_user
   - [ ] Code matches specification exactly
   - [ ] No hardcoded keys or secrets

2. **Testing Phase:**
   - [ ] `tests/memory/test_encryption.py` created (80 LOC)
   - [ ] Minimum 20 test cases passing
   - [ ] AAD binding test passes (CRITICAL)
   - [ ] Tamper detection test passes
   - [ ] Performance tests pass (>= 5k ops/sec, p95 < 1ms)

3. **Dependency Phase:**
   - [ ] `cryptography>=42.0.0` added to requirements.txt
   - [ ] All imports resolve correctly
   - [ ] No missing dependencies

4. **Environment Phase:**
   - [ ] `.env.example` updated with MEMORY_ENCRYPTION_KEY
   - [ ] `.env.example` updated with MEMORY_TENANT_HMAC_KEY
   - [ ] Key generation instructions provided
   - [ ] No real keys in .env.example

5. **Documentation Phase:**
   - [ ] Docstrings complete with security notes
   - [ ] Compensating controls documented (plaintext embeddings)
   - [ ] Key rotation strategy documented
   - [ ] Error handling documented

6. **Code Review Phase:**
   - [ ] No use of deprecated crypto functions
   - [ ] No custom cryptography implementations
   - [ ] Error handling is fail-closed
   - [ ] Logging doesn't expose secrets

---

## RECOMMENDATIONS

### IMMEDIATE (Before Implementation Starts)

1. **Add cryptography to requirements.txt:**
   ```
   cryptography>=42.0.0  # AES-256-GCM for memory encryption (TASK B)
   ```

2. **Update .env.example with encryption keys:**
   ```bash
   # Memory encryption key (32-byte base64-encoded)
   MEMORY_ENCRYPTION_KEY=
   # Memory tenant HMAC key
   MEMORY_TENANT_HMAC_KEY=
   ```

3. **Share this security review with implementation team**

---

### DURING IMPLEMENTATION

1. **Reuse hmac_user() from src/memory/rls.py:**
   - Import: `from src.memory.rls import hmac_user`
   - Don't reimplement (DRY principle)
   - Tests already exist and pass

2. **Use reference implementation structure provided above**

3. **Write AAD binding test FIRST (TDD):**
   - This is the CRITICAL security control
   - Test must fail before implementation
   - Test must pass after correct implementation

4. **Performance testing on actual hardware:**
   - 5k ops/sec is conservative
   - Should achieve 50k-500k ops/sec with AES-NI
   - If slower, check for AES-NI support

---

### BEFORE MERGE

1. **Security Code Review:**
   - [ ] No hardcoded keys (grep for base64 strings)
   - [ ] All secrets from environment variables
   - [ ] Error handling is fail-closed
   - [ ] InvalidTag exceptions propagate correctly

2. **Test Coverage Review:**
   - [ ] All 20+ tests passing
   - [ ] Code coverage >= 95% for security.py
   - [ ] AAD binding test verifies cross-tenant prevention

3. **Documentation Review:**
   - [ ] Compensating controls documented
   - [ ] Key rotation strategy clear
   - [ ] Integration guide for TASK D

---

### BEFORE PRODUCTION

1. **Key Generation:**
   ```bash
   # Generate production keys (DO NOT commit)
   python -c "import os, base64; print('MEMORY_ENCRYPTION_KEY=' + base64.b64encode(os.urandom(32)).decode())"
   python -c "import os, base64; print('MEMORY_TENANT_HMAC_KEY=' + base64.b64encode(os.urandom(32)).decode())"
   ```

2. **Secret Manager Setup:**
   - Store keys in Railway, AWS Secrets Manager, or Azure Key Vault
   - DO NOT use .env files in production
   - Rotate keys quarterly

3. **Monitoring Setup:**
   - Alert on InvalidTag exceptions (potential attacks)
   - Monitor decryption latency (performance degradation)
   - Track encryption operations (usage patterns)

---

## COMPENSATING CONTROLS DOCUMENTATION

### Exception: Plaintext Embeddings in Database

**Risk:** Embedding vectors stored in plaintext for ANN indexing

**Business Justification:**
- ANN query performance requires plaintext vector indexing
- Homomorphic encryption (FHE) has 10,000x performance penalty
- Alternative: Secret sharing (research phase, R2 roadmap)

**Compensating Controls:**

1. **Row-Level Security (RLS):**
   - PostgreSQL RLS policy enforces tenant isolation
   - Users cannot query other users' rows
   - Database-level enforcement (cannot be bypassed)

2. **AAD Binding (This TASK B):**
   - Text and metadata encrypted with AAD=user_hash
   - Cross-tenant decryption cryptographically impossible
   - Even if database compromised, ciphertext is useless

3. **Encrypted Database Volume:**
   - Full-disk encryption (TDE or dm-crypt)
   - Protects against physical theft
   - Backup encryption enforced

4. **Shadow Backup (emb_cipher):**
   - Encrypted copy of embedding stored
   - Used for compliance exports
   - Recovery capability if primary embedding lost

5. **Audit Logging:**
   - All memory_chunks access logged
   - Supabase audit logs or CloudWatch
   - Anomaly detection on access patterns

6. **Network Isolation:**
   - Database not publicly accessible
   - TLS enforced (sslmode=require)
   - VPC/private networking

**Residual Risk:** LOW (acceptable for R1 Phase 1)

**Roadmap:** R2 Phase will evaluate homomorphic encryption or secret sharing

---

## APPENDIX: CRYPTOGRAPHY LIBRARY SECURITY ANALYSIS

### Library: cryptography 45.0.7

**Security Assessment:** APPROVED

**Evidence:**

1. **Maintenance:** Active (last release 2024-11)
2. **Vulnerabilities:** None (CVE check: 2025-10-19)
3. **Standards Compliance:**
   - NIST SP 800-38D (GCM mode)
   - FIPS 140-2 (when using OpenSSL FIPS)
   - RFC 5116 (AEAD ciphers)

4. **Implementation:**
   - Wraps OpenSSL/libcrypto (battle-tested)
   - Hardware acceleration (AES-NI support)
   - Constant-time operations (timing attack resistant)

5. **Security Features:**
   - Authenticated encryption (GCM tag verification)
   - Automatic nonce handling
   - Memory-safe (Rust FFI in recent versions)

6. **Known Issues:** None affecting AES-256-GCM

**Recommendation:** APPROVED for production use

---

## APPENDIX: KEY ROTATION STRATEGY

### Quarterly Rotation (MEMORY_ENCRYPTION_KEY)

**Phase 1: Preparation (Day 0)**
1. Generate new key: `MEMORY_ENCRYPTION_KEY_NEW`
2. Keep old key: `MEMORY_ENCRYPTION_KEY` (rename to OLD)
3. Deploy updated environment variables

**Phase 2: Dual-Write (Days 1-30)**
1. New writes use `MEMORY_ENCRYPTION_KEY_NEW`
2. Reads try NEW key first, fall back to OLD key
3. Background job re-encrypts old blobs:
   ```sql
   UPDATE memory_chunks
   SET text_cipher = seal(open_sealed(text_cipher, OLD), NEW)
   WHERE updated_at < '2025-01-01'
   LIMIT 1000;  -- Batch processing
   ```

**Phase 3: Cleanup (Day 31+)**
1. Verify all blobs re-encrypted (monitor logs)
2. Remove `MEMORY_ENCRYPTION_KEY_OLD`
3. `MEMORY_ENCRYPTION_KEY_NEW` becomes primary

**Downtime:** ZERO (dual-write ensures availability)

---

### Annual Rotation (MEMORY_TENANT_HMAC_KEY)

**WARNING:** Requires full reindex (user_hash column changes)

**Phase 1: Maintenance Window (2-4 hours)**
1. Set application to read-only mode
2. Export all memory_chunks to backup
3. Update `MEMORY_TENANT_HMAC_KEY`
4. Recompute user_hash for all rows:
   ```sql
   UPDATE memory_chunks
   SET user_hash = hmac_sha256(NEW_KEY, user_id);
   ```
5. Rebuild partial indexes (HNSW/IVFFlat)
6. Resume application

**Downtime:** ~2-4 hours (plan for low-traffic window)

**Alternative:** Maintain historical HMAC keys and dual-hash rows (complex)

---

## FINAL SECURITY VERDICT

### SPECIFICATION STATUS: APPROVED

**Rationale:**
- Cryptographic design is sound (AES-256-GCM with AAD)
- Existing reference implementation (envelope.py) shows team competency
- Comprehensive test requirements specified
- Fail-closed error handling mandated
- Compensating controls documented
- Performance requirements achievable

### IMPLEMENTATION STATUS: PENDING

**Next Steps:**
1. Implementation team starts TASK B (3-4 day sprint)
2. Security review at PR submission
3. Final approval after all tests pass
4. Merge to release/r0.5-hotfix branch

### CRITICAL SUCCESS FACTORS:

1. **AAD Binding Test MUST Pass:**
   - User B cannot decrypt User A's data
   - This is the PRIMARY security guarantee

2. **No Hardcoded Keys:**
   - All keys from environment variables
   - Grep check before merge

3. **Fail-Closed Error Handling:**
   - InvalidTag exceptions propagate
   - No silent failures

4. **Performance Requirements Met:**
   - >= 5k ops/sec throughput
   - p95 < 1ms latency

---

## CONTACTS

**Security Review:** repo-guardian agent (this review)
**Implementation Lead:** [TBD - TASK B crypto team]
**Code Review:** Security Lead (before merge)
**Deployment:** Deployment Lead (Phase 3 production)

---

**DECISION: SECURITY SPECIFICATION APPROVED - PROCEED WITH IMPLEMENTATION**

**Signature:** repo-guardian security review agent
**Date:** 2025-10-19
**Review ID:** TASK_B_SECURITY_REVIEW_001
