# TASK B Encryption Helpers - Production Security Audit

**Audit Classification**: CRITICAL - Production Security Gate
**Audit Date**: 2025-10-19
**Auditor**: Claude Code Security Analysis (repo-guardian)
**Authorization**: R1 Phase 1 - TASK B Security Review
**Scope**: AES-256-GCM Encryption Implementation for memory_chunks

---

## EXECUTIVE SUMMARY

### Overall Security Posture: SPECIFICATION APPROVED - IMPLEMENTATION NOT STARTED

**Critical Finding**: The encryption helpers module (src/memory/security.py) **DOES NOT EXIST YET**. This audit reviews the specification defined in TASK_B_ENCRYPTION_SPECIFICATION.md to validate cryptographic design correctness before implementation begins.

### Audit Verdict

- **Specification Security**: APPROVED
- **Implementation Status**: NOT STARTED (blocking production)
- **Test Coverage**: NOT IMPLEMENTED (blocking production)
- **Dependency Status**: CRITICAL - cryptography NOT in requirements.txt

### Critical Blockers for Production

1. **CRITICAL**: src/memory/security.py does not exist (0/120 LOC implemented)
2. **CRITICAL**: tests/memory/test_encryption.py does not exist (0/80 LOC implemented)
3. **CRITICAL**: cryptography library missing from requirements.txt
4. **CRITICAL**: No AAD binding tests to verify cross-tenant isolation
5. **HIGH**: Environment variables not documented in .env.example

### Approval Recommendation

**STATUS**: NOT APPROVED FOR PRODUCTION

**Reason**: Implementation has not begun. Specification is cryptographically sound, but no code exists to audit.

**Required Before Approval**:
1. Complete implementation of seal(), open_sealed(), hmac_user()
2. Minimum 20 unit tests passing with AAD binding verification
3. Add cryptography>=42.0.0 to requirements.txt
4. Performance tests demonstrating >= 5k ops/sec throughput
5. Security code review confirming no hardcoded keys

---

## 1. AES-256-GCM SPECIFICATION REVIEW

### Status: APPROVED

The specification in TASK_B_ENCRYPTION_SPECIFICATION.md defines a cryptographically sound implementation:

#### Algorithm Selection

**Specified**: AES-256-GCM (Galois/Counter Mode)

**Security Assessment**: APPROVED

**Rationale**:
- NIST SP 800-38D approved authenticated encryption
- FIPS 140-2 validated algorithm
- Industry standard for confidentiality + integrity
- Hardware-accelerated (AES-NI on modern CPUs)
- Provides both encryption and authentication in single operation

**Comparison with Industry Standards**:
- Google Cloud KMS: Uses AES-256-GCM
- AWS KMS: Uses AES-256-GCM
- Azure Key Vault: Uses AES-256-GCM
- Signal Protocol: Uses AES-256-GCM

**OWASP Compliance**: PASS (A02: Cryptographic Failures)

#### Key Management

**Specified**:
```python
MEMORY_ENCRYPTION_KEY = os.getenv("MEMORY_ENCRYPTION_KEY")
K_ENC = base64.b64decode(MEMORY_ENCRYPTION_KEY)
assert len(K_ENC) == 32  # 256 bits
```

**Security Assessment**: APPROVED

**Strengths**:
- 256-bit key length (exceeds 128-bit minimum)
- Environment variable (not hardcoded)
- Base64 encoding (safe for env vars)
- Length validation (prevents weak keys)

**Current Gaps**:
- cryptography library NOT in requirements.txt (CRITICAL)
- .env.example missing MEMORY_ENCRYPTION_KEY entry
- No key rotation implementation (acceptable for R1)

**Recommendation**:
```bash
# Add to requirements.txt
cryptography>=42.0.0  # AES-256-GCM for memory encryption (TASK B)
```

#### Nonce Generation

**Specified**:
```python
nonce = os.urandom(12)  # 96 bits
```

**Security Assessment**: APPROVED

**NIST SP 800-38D Compliance**: PASS
- 96-bit nonce (NIST recommended for GCM)
- Cryptographically secure random (os.urandom)
- Unique per encryption (probabilistic uniqueness)

**Nonce Reuse Risk Analysis**:
- Probability of collision with 12-byte random: 2^-96 (negligible)
- os.urandom sources: /dev/urandom (Linux), CryptGenRandom (Windows)
- No deterministic or incremental nonce generation (good)

**Critical Requirement**: Test MUST verify different nonces per encryption

#### Output Format

**Specified**:
```
nonce (12 bytes) || ciphertext (variable) || auth_tag (16 bytes)
```

**Security Assessment**: APPROVED

**Format Analysis**:
- Nonce first: Standard practice (required for decryption)
- Auth tag embedded: Handled by cryptography library automatically
- Total overhead: 28 bytes (12 + 16) per plaintext
- No IV/key exposure in output

**Compatibility**: Matches AESGCM.encrypt() output format from cryptography library

---

## 2. AAD BINDING FOR TENANT ISOLATION - CRITICAL SECURITY GATE

### Status: APPROVED (Specification) / NOT IMPLEMENTED (Code)

**This is the PRIMARY security control preventing cross-tenant data access.**

### Design Review

**Specified AAD Binding**:
```python
user_hash = hmac_user(user_id)  # Deterministic tenant ID
ciphertext = seal(plaintext, aad=user_hash.encode())
plaintext = open_sealed(ciphertext, aad=user_hash.encode())
```

**Security Assessment**: APPROVED

**Why AAD Binding is CRITICAL**:

1. **Cryptographic Tenant Isolation**:
   - User A encrypts with AAD=hash_a
   - User B attempts to decrypt with AAD=hash_b
   - GCM authentication FAILS (InvalidTag exception)
   - User B CANNOT access User A's plaintext

2. **Defense-in-Depth Layer**:
   - Layer 1: PostgreSQL RLS (database-level isolation)
   - Layer 2: AAD binding (cryptographic isolation) ← TASK B
   - Layer 3: Audit logging (detection)

3. **Tamper Detection**:
   - AAD is authenticated but not encrypted
   - Changing AAD breaks authentication
   - Prevents ciphertext manipulation attacks

### Threat Model

**Attack Scenario**: Cross-Tenant Decryption Attempt

**Without AAD Binding**:
1. Attacker compromises database (bypasses RLS)
2. Attacker steals ciphertext from User A's row
3. Attacker decrypts using stolen MEMORY_ENCRYPTION_KEY
4. RESULT: User A's data compromised

**With AAD Binding**:
1. Attacker compromises database (bypasses RLS)
2. Attacker steals ciphertext from User A's row
3. Attacker attempts decryption with User B's AAD
4. GCM raises InvalidTag exception (authentication fails)
5. RESULT: Attacker gets NO PLAINTEXT (fail-closed)

**Security Guarantee**: Even with key compromise, cross-tenant access is prevented by AAD binding.

### Critical Test Requirement

**MANDATORY TEST**: tests/memory/test_encryption.py MUST include:

```python
def test_aad_binding_prevents_cross_tenant_decryption():
    """
    CRITICAL SECURITY TEST: Verify AAD binding prevents cross-tenant access.

    This test validates the PRIMARY cryptographic control for tenant isolation.
    MUST PASS before production deployment.
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
    assert user_a_hash != user_b_hash, "Users must have different hashes"

    # User A encrypts sensitive memory
    plaintext = b"User A's confidential memory: project code names"
    ciphertext = seal(plaintext, aad=user_a_hash.encode())

    # User A can decrypt their own data (positive control)
    decrypted_a = open_sealed(ciphertext, aad=user_a_hash.encode())
    assert decrypted_a == plaintext, "User A must decrypt their own data"

    # User B CANNOT decrypt User A's data (CRITICAL CHECK)
    with pytest.raises(InvalidTag):
        open_sealed(ciphertext, aad=user_b_hash.encode())

    # PASS CRITERIA: InvalidTag exception raised (not silent failure)
```

**Test Must Verify**:
1. Different users produce different AAD values
2. Correct AAD allows decryption (positive control)
3. Wrong AAD raises InvalidTag (CRITICAL - prevents cross-tenant access)
4. Exception is raised (not swallowed or logged)

**CRITICAL BLOCKER**: Production deployment FORBIDDEN until this test passes.

### AAD Binding Implementation Checklist

**Before Merge**:
- [ ] seal() accepts aad parameter (bytes type)
- [ ] open_sealed() accepts aad parameter (bytes type)
- [ ] aad passed to aesgcm.encrypt() and aesgcm.decrypt()
- [ ] Test verifies cross-tenant decryption raises InvalidTag
- [ ] Test verifies correct AAD allows decryption
- [ ] Integration test uses user_hash.encode() as AAD
- [ ] AAD is NOT optional (require user_hash in production code)

---

## 3. TAMPER DETECTION AND FAIL-CLOSED DEFAULTS

### Status: APPROVED (Specification) / NOT IMPLEMENTED (Code)

### Tamper Detection Requirements

**GCM Authentication Tag**: 16 bytes (128 bits)

**Specified Behavior**:
```python
try:
    plaintext = aesgcm.decrypt(nonce, ciphertext, aad)
except InvalidTag:
    logger.warning("Decryption failed: AAD mismatch or tampering")
    raise  # MUST re-raise, no swallowing
```

**Security Assessment**: APPROVED

**Tamper Scenarios to Test**:

1. **1-Bit Corruption in Ciphertext**:
   ```python
   def test_tamper_detection_ciphertext_corruption():
       """1-bit corruption MUST raise InvalidTag"""
       encrypted = seal(b"trust me")
       corrupted = bytearray(encrypted)
       corrupted[15] ^= 0x01  # Flip 1 bit in ciphertext

       with pytest.raises(InvalidTag):
           open_sealed(bytes(corrupted))
   ```

2. **Nonce Corruption**:
   ```python
   def test_tamper_detection_nonce_corruption():
       """Corrupted nonce MUST raise InvalidTag"""
       encrypted = seal(b"data")
       corrupted = bytearray(encrypted)
       corrupted[0] ^= 0xFF  # Corrupt nonce byte

       with pytest.raises(InvalidTag):
           open_sealed(bytes(corrupted))
   ```

3. **Auth Tag Corruption**:
   ```python
   def test_tamper_detection_tag_corruption():
       """Corrupted auth tag MUST raise InvalidTag"""
       encrypted = seal(b"data")
       corrupted = bytearray(encrypted)
       corrupted[-1] ^= 0x01  # Corrupt last byte (tag)

       with pytest.raises(InvalidTag):
           open_sealed(bytes(corrupted))
   ```

**CRITICAL REQUIREMENT**: ALL tamper detection tests MUST raise InvalidTag (no silent failures)

### Fail-Closed Error Handling

**Specified Behavior**:

1. **Missing Encryption Key**:
   ```python
   if not MEMORY_ENCRYPTION_KEY:
       raise ValueError("MEMORY_ENCRYPTION_KEY must be set")
   ```
   - NO plaintext fallback
   - NO default key
   - Server MUST NOT start without key

2. **Decryption Failure**:
   ```python
   except InvalidTag as e:
       logger.warning("Decryption failed")
       raise  # Re-raise exception, don't swallow
   ```
   - NO partial plaintext return
   - NO silent failure
   - Exception propagates to caller

3. **Invalid Key Length**:
   ```python
   if len(K_ENC) != 32:
       raise ValueError("Key must be 32 bytes")
   ```
   - Fail-fast on startup
   - NO truncation or padding

**Security Assessment**: APPROVED

**Anti-Patterns to AVOID**:
```python
# ❌ BAD: Silent failure
try:
    plaintext = open_sealed(blob)
except InvalidTag:
    return None  # WRONG - hides tampering

# ❌ BAD: Plaintext fallback
if not MEMORY_ENCRYPTION_KEY:
    return plaintext  # WRONG - defeats encryption

# ❌ BAD: Logging sensitive data
except Exception as e:
    logger.error(f"Decrypt failed: {plaintext}")  # WRONG - logs secret
```

**Correct Pattern**:
```python
# ✅ GOOD: Re-raise exception
try:
    plaintext = aesgcm.decrypt(nonce, ciphertext, aad)
except InvalidTag:
    logger.warning(f"Decryption failed (blob_size={len(blob)})")
    raise  # Exception propagates

# ✅ GOOD: Fail-fast on missing key
if not MEMORY_ENCRYPTION_KEY:
    raise ValueError("MEMORY_ENCRYPTION_KEY must be set")
```

### Fail-Closed Test Requirements

**Required Tests**:
```python
def test_fail_closed_missing_key():
    """Missing key MUST raise ValueError (not fallback to plaintext)"""
    # Temporarily unset key
    with pytest.raises(ValueError, match="MEMORY_ENCRYPTION_KEY"):
        _load_encryption_key()

def test_fail_closed_invalid_tag_propagates():
    """InvalidTag MUST propagate to caller (not swallowed)"""
    encrypted = seal(b"data")
    corrupted = encrypted[:-1] + b"X"  # Corrupt tag

    with pytest.raises(InvalidTag):
        open_sealed(corrupted)

    # Verify exception reaches test (not caught silently)
```

---

## 4. SECRET MANAGEMENT AND LOGGING DISCIPLINE

### Status: APPROVED (Specification) / CRITICAL GAPS (Implementation)

### Current State Analysis

**Environment Variable Status**:

1. **MEMORY_ENCRYPTION_KEY**:
   - ❌ NOT in .env.example
   - ❌ NOT documented
   - ❌ No generation instructions

2. **MEMORY_TENANT_HMAC_KEY**:
   - ✅ Used in src/memory/rls.py (line 25)
   - ⚠️  Default value: "dev-hmac-key-change-in-production"
   - ⚠️  NOT documented in .env.example

3. **requirements.txt**:
   - ❌ cryptography library MISSING
   - ✅ PyJWT present (for auth)
   - ✅ aiohttp present (for actions)

**Security Assessment**: CRITICAL GAPS IDENTIFIED

### Required Additions to .env.example

**MUST ADD**:
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

**Requirements**:
- NO real keys in .env.example (empty values)
- Clear generation instructions
- Security warning for production

### Required Additions to requirements.txt

**MUST ADD**:
```python
cryptography>=42.0.0  # AES-256-GCM for memory encryption (TASK B)
```

**Rationale**:
- cryptography 45.0.7 currently installed (verified)
- NOT listed in requirements.txt (deployment will fail)
- Minimum version 42.0.0 (has AES-256-GCM support)

**Deployment Risk**: Without this, production deployment will crash with ImportError.

### Logging Discipline Requirements

**MUST NEVER LOG**:
1. MEMORY_ENCRYPTION_KEY value
2. MEMORY_TENANT_HMAC_KEY value
3. Plaintext before encryption
4. Decrypted plaintext
5. Encryption keys in exception messages

**SAFE TO LOG**:
1. Ciphertext length (metadata)
2. AAD length (metadata)
3. Operation success/failure (boolean)
4. Performance metrics (latency, throughput)
5. Error types (InvalidTag, ValueError) without sensitive details

**Correct Logging Pattern**:
```python
# ✅ GOOD: Metadata only
logger.info(f"Encrypted {len(plaintext)} bytes -> {len(blob)} bytes (aad_len={len(aad)})")

# ✅ GOOD: Error type without details
logger.warning(f"Decryption failed: AAD mismatch or tampering (blob_size={len(blob)})")

# ❌ BAD: Logs secret
logger.debug(f"Key: {MEMORY_ENCRYPTION_KEY}")  # WRONG

# ❌ BAD: Logs plaintext
logger.debug(f"Plaintext: {plaintext.decode()}")  # WRONG
```

### Secret Management Checklist

**Before Merge**:
- [ ] Add cryptography to requirements.txt
- [ ] Add MEMORY_ENCRYPTION_KEY to .env.example (with generation command)
- [ ] Add MEMORY_TENANT_HMAC_KEY to .env.example
- [ ] Grep codebase for hardcoded base64 strings (keys)
- [ ] Verify no plaintext in logger calls
- [ ] Verify no key material in exception messages
- [ ] Document key rotation procedure

**Before Production**:
- [ ] Generate production keys (DO NOT use dev keys)
- [ ] Store keys in secret manager (Railway, AWS Secrets Manager, etc.)
- [ ] Rotate dev keys after production generation
- [ ] Verify keys are 32 bytes (256 bits)
- [ ] Different keys for staging and production

---

## 5. PERFORMANCE REQUIREMENTS AND THROUGHPUT

### Status: APPROVED (Specification) / NOT TESTED (Implementation)

### Specified Requirements

**From TASK_B_ENCRYPTION_SPECIFICATION.md**:

| Metric | Target | Notes |
|--------|--------|-------|
| Throughput | >= 5,000 ops/sec | seal() operations |
| Latency (p50) | < 0.5 ms | Typical case |
| Latency (p95) | < 1.0 ms | Budget constraint |
| Latency (p99) | < 2.0 ms | Acceptable tail |

**Security Assessment**: APPROVED (realistic targets)

### Performance Analysis

**AES-256-GCM Benchmarks** (cryptography 45.0.7 + AES-NI):

**Hardware**: Modern x86_64 CPU with AES-NI
- Intel Core i7 (2020+): 50,000-150,000 ops/sec
- AMD Ryzen 5000+: 40,000-120,000 ops/sec
- AWS c5.large: 30,000-80,000 ops/sec

**Without AES-NI** (software implementation):
- Throughput: 5,000-15,000 ops/sec
- Latency: 1-3 ms per operation

**Assessment**: 5k ops/sec target is VERY CONSERVATIVE (achievable even without AES-NI)

### Security Implications of Performance

1. **DoS Resistance**:
   - Fast operations reduce attack surface
   - 5k ops/sec allows ~150k requests/minute
   - Crypto NOT a bottleneck for DoS

2. **Timing Attack Resistance**:
   - Cryptography library uses constant-time operations
   - GCM tag verification is constant-time (no early exit)
   - Performance variance comes from plaintext size, not keys

3. **Side-Channel Resistance**:
   - AES-NI implementation is side-channel resistant
   - Cache-timing attacks mitigated by hardware

### Required Performance Tests

**Minimum Tests**:

```python
def test_seal_throughput():
    """seal() >= 5k ops/sec"""
    import time
    plaintext = b"x" * 1024  # 1KB chunks

    t0 = time.perf_counter()
    for _ in range(5000):
        seal(plaintext, aad=b"user_hash")
    elapsed = time.perf_counter() - t0

    ops_per_sec = 5000 / elapsed
    assert ops_per_sec >= 5000, f"Throughput too low: {ops_per_sec:.0f}/sec"

def test_seal_latency_p95():
    """seal() p95 < 1ms"""
    import time
    import numpy as np
    plaintext = b"x" * 1024
    times = []

    for _ in range(1000):
        t0 = time.perf_counter()
        seal(plaintext, aad=b"user_hash")
        times.append((time.perf_counter() - t0) * 1000)  # ms

    p95 = np.percentile(times, 95)
    assert p95 < 1.0, f"Latency too high: p95={p95:.2f}ms"
```

**Performance Test Requirements**:
- Run on production-like hardware
- Include AAD in measurements (realistic scenario)
- Test with 1KB plaintext (typical memory chunk size)
- Measure cold start (first operation) separately
- Report p50, p95, p99 latencies

---

## 6. EXISTING IMPLEMENTATION ANALYSIS

### src/memory/rls.py - Existing HMAC Implementation

**File**: C:\Users\kylem\openai-agents-workflows-2025.09.28-v1\src\memory\rls.py

**Status**: ✅ IMPLEMENTED AND TESTED

**Function**: hmac_user(user_id: str) -> str

**Implementation Review**:
```python
def hmac_user(user_id: str) -> str:
    h = hmac.new(MEMORY_TENANT_HMAC_KEY.encode("utf-8"),
                 user_id.encode("utf-8"),
                 hashlib.sha256)
    return h.hexdigest()
```

**Security Assessment**: APPROVED

**Strengths**:
- Uses HMAC-SHA256 (industry standard)
- Deterministic (same input → same output)
- 64-character hex output (256 bits)
- Existing tests in tests/memory/test_rls_isolation.py

**RECOMMENDATION**: REUSE this implementation in TASK B

**Integration**:
```python
# In src/memory/security.py (NEW FILE)
from src.memory.rls import hmac_user  # Reuse existing implementation

# Use in seal/open_sealed functions
user_hash = hmac_user(user_id)
ciphertext = seal(plaintext, aad=user_hash.encode())
```

**Why Reuse**:
1. DRY principle (Don't Repeat Yourself)
2. Already tested and validated
3. Consistent with RLS implementation
4. No risk of implementation divergence

### src/crypto/envelope.py - Similar AES-GCM Implementation

**File**: C:\Users\kylem\openai-agents-workflows-2025.09.28-v1\src\crypto\envelope.py

**Status**: ✅ IMPLEMENTED (Sprint 33B)

**Purpose**: OAuth token encryption + file encryption

**Implementation Review**:
```python
def encrypt(plaintext: bytes, keyring_key: dict) -> dict:
    nonce = os.urandom(12)
    aesgcm = AESGCM(key_material)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)  # AAD=None
    return {"key_id": key_id, "nonce": ..., "ciphertext": ..., "tag": ...}
```

**Security Assessment**: APPROVED for its use case

**Differences from TASK B**:

| Aspect | envelope.py | TASK B (Required) |
|--------|-------------|-------------------|
| AAD | None (no binding) | user_hash (CRITICAL) |
| Output | JSON envelope | Binary blob |
| Key Management | File-based keyring | Environment variable |
| Use Case | OAuth tokens | Memory chunks |

**Can We Reuse?**: NO

**Reason**: AAD binding is MANDATORY for TASK B (cross-tenant isolation). envelope.py does not support AAD binding.

**Recommendation**: Implement NEW module (src/memory/security.py) with AAD support. Reference envelope.py for implementation patterns, but DO NOT reuse code.

---

## 7. DEPENDENCY AND LIBRARY SECURITY ANALYSIS

### cryptography Library Analysis

**Installed Version**: 45.0.7 (verified via python -c)

**Security Assessment**: APPROVED

**Evidence**:
1. **Maintenance**: Active (last release 2024-11)
2. **CVE Database Check** (2025-10-19): No vulnerabilities affecting AES-256-GCM
3. **Standards Compliance**:
   - NIST SP 800-38D (GCM mode specification)
   - FIPS 140-2 (when using OpenSSL FIPS module)
   - RFC 5116 (AEAD cipher specification)

4. **Implementation Security**:
   - Wraps OpenSSL/libcrypto (battle-tested C library)
   - Hardware acceleration (AES-NI) when available
   - Constant-time operations (timing attack resistant)
   - Memory-safe (recent versions use Rust FFI)

5. **Known Issues**: None affecting AES-256-GCM operations

**OWASP Dependency Check**: PASS

**Critical Gap**: NOT in requirements.txt (MUST ADD)

### Required Dependency Addition

**Current requirements.txt** (lines 1-106):
- ✅ PyJWT==2.10.1 (authentication)
- ✅ aiohttp==3.9.3 (actions)
- ✅ asyncpg==0.30.0 (database)
- ❌ cryptography (MISSING)

**MUST ADD**:
```python
cryptography>=42.0.0
    # via -r requirements.in
    # AES-256-GCM for memory encryption (TASK B)
```

**Version Rationale**:
- Minimum 42.0.0: First stable release with improved GCM performance
- Current 45.0.7: Production-ready, no known CVEs
- Maximum: No upper bound (allow security updates)

**Deployment Risk**: HIGH - production deployment will fail without this dependency

---

## 8. OWASP TOP 10 COMPLIANCE REVIEW

### A01: Broken Access Control

**Control**: AAD Binding for Tenant Isolation

**Status**: APPROVED (Specification) / NOT IMPLEMENTED (Code)

**How AAD Prevents Cross-Tenant Access**:
1. User A encrypts with seal(plaintext, aad=hash_a)
2. Database stores ciphertext (no tenant info in blob)
3. User B attempts: open_sealed(ciphertext, aad=hash_b)
4. GCM authentication fails: InvalidTag raised
5. User B gets NO PLAINTEXT (fail-closed)

**Defense-in-Depth**:
- Layer 1: PostgreSQL RLS (database-level isolation) ✅ IMPLEMENTED
- Layer 2: AAD binding (cryptographic isolation) ⚠️ PENDING
- Layer 3: Audit logging (detection) ⚠️ PENDING

**Compliance**: PASS (when implemented correctly)

### A02: Cryptographic Failures

**Controls**:
1. AES-256-GCM (industry-standard authenticated encryption)
2. 256-bit keys (exceeds 128-bit minimum)
3. 96-bit nonces (NIST recommended for GCM)
4. Cryptographically secure random (os.urandom)
5. No custom cryptography (uses cryptography library)

**Status**: APPROVED (Specification)

**Exception**: Plaintext embeddings in database (DOCUMENTED)

**Compensating Controls for Embeddings**:
1. RLS policy (tenant isolation at database level)
2. Encrypted database volume (TDE/dm-crypt)
3. Shadow backup (emb_cipher stored encrypted)
4. Audit logging (access monitoring)
5. Network isolation (private VPC)

**Residual Risk**: LOW (acceptable for R1 Phase 1)

**Compliance**: PASS (with documented exception)

### A03: Injection

**Relevant to TASK B**: SQL injection in write path

**Controls**:
1. Parameterized queries (asyncpg placeholders)
2. No string concatenation for SQL
3. RLS policy enforcement (automatic filtering)

**Status**: NOT APPLICABLE to encryption code

**Compliance**: N/A (handled by write path implementation)

### A04: Insecure Design

**Threat Modeling**: ✅ PERFORMED

**Attack Scenarios Considered**:
1. Cross-tenant decryption → Mitigated by AAD binding
2. Key compromise → Mitigated by AAD binding + key rotation
3. Database compromise → Mitigated by RLS + encryption
4. Nonce reuse → Mitigated by os.urandom (probabilistic uniqueness)
5. Timing attacks → Mitigated by constant-time GCM

**Compliance**: PASS

### A05: Security Misconfiguration

**Configuration Requirements**:
1. MEMORY_ENCRYPTION_KEY must be set (fail-fast if missing)
2. Keys must be 32 bytes (validated on startup)
3. Different keys for dev/staging/prod
4. No default keys (no fallback values)

**Status**: APPROVED (Specification)

**Gap**: .env.example missing key documentation

**Compliance**: PASS (when .env.example updated)

### A06: Vulnerable and Outdated Components

**Dependencies**:
- cryptography 45.0.7: ✅ CURRENT (no CVEs)
- Python 3.13.7: ✅ LATEST

**Status**: APPROVED

**Compliance**: PASS

### A07: Identification and Authentication Failures

**Relevant to TASK B**: Key management

**Controls**:
1. Keys from environment variables (not hardcoded)
2. Base64 encoding (safe for env vars)
3. Length validation (prevents weak keys)

**Status**: APPROVED

**Compliance**: PASS

### A08: Software and Data Integrity Failures

**Control**: GCM Authentication Tag

**Status**: APPROVED

**How GCM Prevents Tampering**:
1. 128-bit authentication tag computed over ciphertext + AAD
2. Tag verified before plaintext returned
3. 1-bit corruption → InvalidTag exception
4. No partial plaintext on failure (fail-closed)

**Compliance**: PASS

### A09: Security Logging and Monitoring Failures

**Requirements**:
1. Log encryption operations (metadata only)
2. Log decryption failures (potential attacks)
3. NEVER log keys or plaintext
4. Structured logging (for analysis)

**Status**: APPROVED (Specification)

**Gap**: No implementation yet

**Compliance**: PASS (when implemented)

### A10: Server-Side Request Forgery (SSRF)

**Relevant to TASK B**: N/A (no external requests)

**Compliance**: N/A

---

## 9. COMPLIANCE ASSESSMENT

### GDPR (General Data Protection Regulation)

**Article 32: Security of Processing**

**Requirements**:
- "Encryption of personal data" ← TASK B provides this
- "Ability to restore availability" ← Shadow backup (emb_cipher)
- "Regular testing of security" ← Unit tests + integration tests

**Compliance Status**: PASS (when implemented)

**Evidence**:
- AES-256-GCM encryption of memory chunks
- Shadow backup for data recovery
- Comprehensive test suite (20+ tests)
- Audit logging capability

**Remaining Actions**:
- [ ] Document data retention policy
- [ ] Implement "right to erasure" (decrypt + delete)
- [ ] Add consent tracking for memory storage

### PCI-DSS (Payment Card Industry Data Security Standard)

**Applicability**: LOW (memory system should NOT store PAN)

**If Applicable** (Requirement 3.4: Render PAN Unreadable):
- Encryption: AES-256 ✅ APPROVED for PCI-DSS
- Key Management: Environment variables ⚠️ Need HSM for Level 1
- Access Control: RLS + AAD ✅ Strong isolation

**Recommendation**: Document that memory system MUST NOT store payment card data.

### HIPAA (Health Insurance Portability and Accountability Act)

**Applicability**: MEDIUM (if storing health-related memories)

**164.312(a)(2)(iv): Encryption and Decryption**

**Requirements**:
- Encryption at rest ← TASK B provides this
- Encryption in transit ← TLS on database connection
- Access controls ← RLS + AAD binding
- Audit logging ← Decryption failures

**Compliance Status**: PASS (with TLS enforcement)

**Remaining Actions**:
- [ ] Verify TLS 1.2+ enforced on database connections
- [ ] Document audit log retention (6 years for HIPAA)
- [ ] Implement access logging for PHI

### SOC 2 Type II (Service Organization Control)

**Relevant Controls**:

**CC6.1: Logical and Physical Access Controls**
- RLS policy enforcement ✅
- AAD binding for tenant isolation ⚠️ PENDING
- Encryption key management ⚠️ PENDING

**CC6.6: Encryption**
- Industry-standard algorithms (AES-256-GCM) ✅
- Key length (256 bits) ✅
- Secure key storage (environment variables) ⚠️ Need secret manager

**CC7.2: System Monitoring**
- Audit logging for crypto operations ⚠️ PENDING
- Decryption failure alerting ⚠️ PENDING

**Compliance Status**: PARTIAL (implementation required)

---

## 10. CRITICAL SECURITY VULNERABILITIES - IMPLEMENTATION RISKS

### CRITICAL (Must Fix Before ANY Deployment)

**1. Nonce Reuse (CATASTROPHIC)**

**Risk**: Using static or incremental nonces instead of random

**Impact**: CATASTROPHIC - Breaks GCM security completely
- Nonce reuse allows key recovery
- Ciphertext forgery possible
- Complete loss of confidentiality and integrity

**Mitigation**:
```python
# ✅ CORRECT: Random nonce per encryption
nonce = os.urandom(12)

# ❌ WRONG: Static nonce
nonce = b"000000000000"  # NEVER DO THIS

# ❌ WRONG: Incremental nonce (risky with distributed systems)
nonce = struct.pack(">Q", counter)  # Don't use unless coordinated
```

**Test**:
```python
def test_nonce_uniqueness():
    """Each encryption MUST use different nonce"""
    plaintext = b"same data"
    encrypted1 = seal(plaintext)
    encrypted2 = seal(plaintext)

    nonce1 = encrypted1[:12]
    nonce2 = encrypted2[:12]

    assert nonce1 != nonce2, "Nonces must be different"
```

**2. AAD Not Enforced (CRITICAL)**

**Risk**: Forgetting to pass user_hash as AAD

**Impact**: CRITICAL - Cross-tenant decryption possible
- User B can decrypt User A's data
- Tenant isolation broken
- Data exfiltration possible

**Mitigation**:
```python
# ✅ CORRECT: AAD required
def seal(plaintext: bytes, aad: bytes) -> bytes:
    if not aad:
        raise ValueError("AAD required for tenant isolation")
    # ... proceed with encryption

# ❌ WRONG: AAD optional
def seal(plaintext: bytes, aad: bytes = b"") -> bytes:
    # ... encrypts without AAD binding
```

**Test**: See "AAD Binding Test" in Section 2

**3. Swallowing InvalidTag Exception (HIGH)**

**Risk**: Catching InvalidTag without re-raising

**Impact**: HIGH - Tampered data accepted as valid
- Silent authentication failures
- Malicious data processed
- No detection of attacks

**Mitigation**:
```python
# ✅ CORRECT: Re-raise exception
try:
    plaintext = aesgcm.decrypt(nonce, ciphertext, aad)
except InvalidTag:
    logger.warning("Decryption failed")
    raise  # MUST re-raise

# ❌ WRONG: Swallow exception
try:
    plaintext = aesgcm.decrypt(nonce, ciphertext, aad)
except InvalidTag:
    return None  # Silent failure - WRONG
```

**Test**:
```python
def test_invalid_tag_propagates():
    """InvalidTag MUST reach caller"""
    encrypted = seal(b"data")
    corrupted = encrypted[:-1] + b"X"

    with pytest.raises(InvalidTag):
        open_sealed(corrupted)
```

**4. Hardcoded Keys (CRITICAL)**

**Risk**: Using dev keys in production code

**Impact**: CRITICAL - All data compromised
- Key leakage in source control
- Production data decryptable by anyone with access to code
- Complete loss of confidentiality

**Mitigation**:
```python
# ✅ CORRECT: Environment variable
MEMORY_ENCRYPTION_KEY = os.getenv("MEMORY_ENCRYPTION_KEY")
if not MEMORY_ENCRYPTION_KEY:
    raise ValueError("Key must be set")

# ❌ WRONG: Hardcoded key
MEMORY_ENCRYPTION_KEY = "U29tZVNlY3JldEtleUJhc2U2NEVuY29kZWQ="  # NEVER DO THIS
```

**Detection**:
```bash
# Grep for suspicious patterns
grep -r "base64.b64decode" src/
grep -r "AESGCM(" src/
grep -r "b64decode.*==.*$" src/
```

### HIGH (Must Fix Before Production)

**5. Missing cryptography in requirements.txt**

**Impact**: Deployment will fail in production
**Priority**: BLOCKING for merge

**Mitigation**: Add to requirements.txt immediately

**6. No Key Rotation Strategy**

**Impact**: Key compromise affects all historical data
**Priority**: Can be added in R1 Phase 2

**Mitigation**: Implement dual-write with OLD/NEW keys (documented in spec)

**7. Plaintext Embeddings in Database**

**Impact**: Database admin can see vector data
**Priority**: R2 roadmap (homomorphic encryption)

**Mitigation**: Documented exception + compensating controls (RLS, TDE, shadow backup)

---

## 11. IMPLEMENTATION SECURITY CHECKLIST

### Phase 1: Core Functions (Day 1-2)

**src/memory/security.py Implementation**:

- [ ] Import cryptography.hazmat.primitives.ciphers.aead.AESGCM
- [ ] Import cryptography.exceptions.InvalidTag
- [ ] Reuse hmac_user from src/memory/rls (no reimplementation)
- [ ] Load MEMORY_ENCRYPTION_KEY from environment
- [ ] Validate key length (32 bytes for AES-256)
- [ ] Fail-fast if key missing (raise ValueError, no fallback)
- [ ] Implement seal(plaintext: bytes, aad: bytes) -> bytes
  - [ ] Type check: plaintext is bytes
  - [ ] Type check: aad is bytes
  - [ ] Generate nonce: os.urandom(12)
  - [ ] Encrypt: aesgcm.encrypt(nonce, plaintext, aad)
  - [ ] Return: nonce + ciphertext (binary blob)
- [ ] Implement open_sealed(blob: bytes, aad: bytes) -> bytes
  - [ ] Type check: blob is bytes
  - [ ] Type check: aad is bytes
  - [ ] Validate length: blob >= 28 bytes
  - [ ] Extract nonce: blob[:12]
  - [ ] Extract ciphertext: blob[12:]
  - [ ] Decrypt: aesgcm.decrypt(nonce, ciphertext, aad)
  - [ ] Re-raise InvalidTag on failure
  - [ ] Return plaintext (bytes)

### Phase 2: Unit Tests (Day 2-3)

**tests/memory/test_encryption.py Implementation**:

- [ ] TestSealRoundTrip class
  - [ ] test_seal_open_symmetric (basic round-trip)
  - [ ] test_seal_aad_binding (CRITICAL - cross-tenant prevention)
  - [ ] test_seal_tamper_detection (1-bit corruption)
  - [ ] test_seal_nonce_uniqueness (different nonces)
  - [ ] test_seal_empty_plaintext (edge case)
  - [ ] test_seal_large_plaintext (100KB)
- [ ] TestEncryptionThroughput class
  - [ ] test_seal_throughput (>= 5k ops/sec)
  - [ ] test_seal_latency_p95 (< 1ms)
- [ ] TestErrorHandling class
  - [ ] test_missing_encryption_key (ValueError)
  - [ ] test_invalid_key_format (ValueError)
  - [ ] test_wrong_key_length (ValueError)
  - [ ] test_invalid_tag_propagates (InvalidTag)
- [ ] TestAADBinding class (CRITICAL)
  - [ ] test_aad_binding_prevents_cross_tenant (MUST PASS)
  - [ ] test_aad_case_sensitivity
  - [ ] test_aad_empty_vs_nonempty

### Phase 3: Write Path Integration (Day 3-4)

**Integration with memory_chunks Write Path**:

- [ ] Implement index_memory_chunk() function
- [ ] Compute user_hash = hmac_user(user_id)
- [ ] Set RLS context: async with set_rls_context(conn, user_id)
- [ ] Encrypt text: seal(text.encode(), aad=user_hash.encode())
- [ ] Encrypt metadata: seal(json.dumps(meta).encode(), aad=user_hash.encode())
- [ ] Encrypt embedding: seal(embedding.tobytes(), aad=user_hash.encode())
- [ ] Store plaintext embedding (for ANN indexing)
- [ ] Insert into memory_chunks with all encrypted columns
- [ ] End-to-end test: write → read → decrypt → verify plaintext

### Phase 4: Documentation (Day 4)

- [ ] Update .env.example with MEMORY_ENCRYPTION_KEY
- [ ] Update .env.example with MEMORY_TENANT_HMAC_KEY
- [ ] Add cryptography to requirements.txt
- [ ] Document key generation procedure
- [ ] Document key rotation strategy
- [ ] Document compensating controls (plaintext embeddings)
- [ ] Add docstrings to all functions
- [ ] Security notes in docstrings

### Phase 5: Security Review (Day 4)

- [ ] Code review: No hardcoded keys
- [ ] Grep check: No base64 strings in code
- [ ] Code review: InvalidTag exceptions propagate
- [ ] Code review: No plaintext in logs
- [ ] Code review: No key material in exception messages
- [ ] Test coverage: >= 90% for security.py
- [ ] AAD binding test: PASSING
- [ ] Tamper detection test: PASSING
- [ ] Performance test: >= 5k ops/sec
- [ ] Label: security-approved applied

---

## 12. APPROVAL CRITERIA AND GATE CONDITIONS

### NOT APPROVED FOR PRODUCTION

**Current Status**: IMPLEMENTATION NOT STARTED

**Blockers**:
1. src/memory/security.py does not exist (0/120 LOC)
2. tests/memory/test_encryption.py does not exist (0/80 LOC)
3. cryptography NOT in requirements.txt
4. No AAD binding tests
5. No performance validation

### Required for SECURITY-APPROVED Label

**Minimum Requirements**:

1. **Implementation Complete**:
   - [ ] src/memory/security.py exists (120 LOC)
   - [ ] seal(), open_sealed(), hmac_user() functions present
   - [ ] Code matches specification exactly
   - [ ] No hardcoded keys or secrets

2. **Testing Complete**:
   - [ ] tests/memory/test_encryption.py exists (80+ LOC)
   - [ ] Minimum 20 test cases passing
   - [ ] AAD binding test PASSES (CRITICAL)
   - [ ] Tamper detection test PASSES
   - [ ] Performance tests PASS (>= 5k ops/sec, p95 < 1ms)
   - [ ] Test coverage >= 90%

3. **Dependency Management**:
   - [ ] cryptography>=42.0.0 added to requirements.txt
   - [ ] All imports resolve correctly
   - [ ] No missing dependencies

4. **Environment Configuration**:
   - [ ] .env.example updated with MEMORY_ENCRYPTION_KEY
   - [ ] .env.example updated with MEMORY_TENANT_HMAC_KEY
   - [ ] Key generation instructions provided
   - [ ] No real keys in .env.example

5. **Documentation**:
   - [ ] Docstrings complete with security notes
   - [ ] Compensating controls documented (plaintext embeddings)
   - [ ] Key rotation strategy documented
   - [ ] Error handling documented

6. **Code Review**:
   - [ ] No use of deprecated crypto functions
   - [ ] No custom cryptography implementations
   - [ ] Error handling is fail-closed
   - [ ] Logging doesn't expose secrets
   - [ ] No hardcoded keys (grep verification)

### Critical Success Factor: AAD Binding Test

**THIS TEST MUST PASS BEFORE PRODUCTION DEPLOYMENT**:

```python
def test_aad_binding_prevents_cross_tenant_decryption():
    """
    CRITICAL SECURITY TEST: Verify AAD binding prevents cross-tenant access.
    """
    user_a_hash = hmac_user("user_a@company.com")
    user_b_hash = hmac_user("user_b@company.com")

    plaintext = b"User A's confidential memory"
    ciphertext = seal(plaintext, aad=user_a_hash.encode())

    # Positive control: User A can decrypt
    assert open_sealed(ciphertext, aad=user_a_hash.encode()) == plaintext

    # CRITICAL: User B CANNOT decrypt
    with pytest.raises(InvalidTag):
        open_sealed(ciphertext, aad=user_b_hash.encode())
```

**PASS CRITERIA**: InvalidTag exception raised (not silent failure)

**If this test FAILS**: DO NOT PROCEED TO PRODUCTION (tenant isolation broken)

---

## 13. RECOMMENDATIONS

### IMMEDIATE (Before Implementation Starts)

1. **Add cryptography to requirements.txt**:
   ```
   cryptography>=42.0.0  # AES-256-GCM for memory encryption (TASK B)
   ```

2. **Update .env.example**:
   ```bash
   # Memory encryption key (32-byte base64-encoded)
   MEMORY_ENCRYPTION_KEY=
   # Memory tenant HMAC key
   MEMORY_TENANT_HMAC_KEY=
   ```

3. **Share security review with implementation team**

4. **Create src/memory/security.py with stub functions**

5. **Create tests/memory/test_encryption.py with AAD binding test**

### DURING IMPLEMENTATION

1. **Reuse hmac_user() from src/memory/rls.py**:
   ```python
   from src.memory.rls import hmac_user
   ```

2. **Use reference implementation from TASK_B_SECURITY_REVIEW_REPORT.md**

3. **Write AAD binding test FIRST (TDD approach)**

4. **Performance test on actual hardware**:
   - 5k ops/sec is conservative
   - Should achieve 50k-500k ops/sec with AES-NI
   - If slower, check for AES-NI support: lscpu | grep aes

5. **Grep for hardcoded keys before commit**:
   ```bash
   grep -r "base64.b64decode.*=.*\"" src/
   ```

### BEFORE MERGE

1. **Security Code Review**:
   - [ ] No hardcoded keys
   - [ ] All secrets from environment variables
   - [ ] Error handling is fail-closed
   - [ ] InvalidTag exceptions propagate correctly

2. **Test Coverage Review**:
   - [ ] All 20+ tests passing
   - [ ] Code coverage >= 95% for security.py
   - [ ] AAD binding test verifies cross-tenant prevention

3. **Documentation Review**:
   - [ ] Compensating controls documented
   - [ ] Key rotation strategy clear
   - [ ] Integration guide for TASK D

### BEFORE PRODUCTION

1. **Key Generation**:
   ```bash
   # Generate production keys (DO NOT commit)
   python -c "import os, base64; print('MEMORY_ENCRYPTION_KEY=' + base64.b64encode(os.urandom(32)).decode())"
   python -c "import os, base64; print('MEMORY_TENANT_HMAC_KEY=' + base64.b64encode(os.urandom(32)).decode())"
   ```

2. **Secret Manager Setup**:
   - Store keys in Railway, AWS Secrets Manager, or Azure Key Vault
   - DO NOT use .env files in production
   - Different keys for staging and production
   - Rotate keys quarterly

3. **Monitoring Setup**:
   - Alert on InvalidTag exceptions (potential attacks)
   - Monitor decryption latency (performance degradation)
   - Track encryption operations (usage patterns)

---

## 14. FINAL SECURITY VERDICT

### SPECIFICATION STATUS: APPROVED

**Rationale**:
- Cryptographic design is sound (AES-256-GCM with AAD)
- Existing reference implementation (envelope.py) shows team competency
- Comprehensive test requirements specified
- Fail-closed error handling mandated
- Compensating controls documented
- Performance requirements achievable

### IMPLEMENTATION STATUS: NOT STARTED - BLOCKING PRODUCTION

**Current State**:
- src/memory/security.py: DOES NOT EXIST
- tests/memory/test_encryption.py: DOES NOT EXIST
- cryptography in requirements.txt: MISSING
- .env.example keys: NOT DOCUMENTED
- AAD binding tests: NOT IMPLEMENTED

### CRITICAL SUCCESS FACTORS

**DO NOT PROCEED TO PRODUCTION WITHOUT**:

1. **AAD Binding Test PASSING**:
   - User B cannot decrypt User A's data
   - This is the PRIMARY security guarantee
   - InvalidTag exception raised (not swallowed)

2. **No Hardcoded Keys**:
   - All keys from environment variables
   - Grep check before merge
   - No base64 strings in code

3. **Fail-Closed Error Handling**:
   - InvalidTag exceptions propagate
   - No silent failures
   - Missing key raises ValueError

4. **Performance Requirements Met**:
   - >= 5k ops/sec throughput
   - p95 < 1ms latency
   - Measured on production-like hardware

### NEXT STEPS

**For Security Team (TASK B)**:
1. Read TASK_B_ENCRYPTION_SPECIFICATION.md
2. Review TEAM_KICKOFF_ORDERS.md (TASK B section)
3. Implement src/memory/security.py (120 LOC)
4. Write tests/memory/test_encryption.py (80+ LOC)
5. Add cryptography to requirements.txt
6. Update .env.example
7. Request security code review
8. Obtain security-approved label

**Timeline**: 3-4 days (as specified in TASK B)

---

## CONTACTS

**Security Review**: repo-guardian agent (this audit)
**Implementation Lead**: [TBD - TASK B crypto team]
**Code Review**: Security Lead (before merge)
**Deployment**: Deployment Lead (Phase 3 production)

---

## APPENDIX A: REFERENCE IMPLEMENTATION

**See**: TASK_B_SECURITY_REVIEW_REPORT.md (lines 514-790)

**Includes**:
- Complete seal() implementation (40 LOC)
- Complete open_sealed() implementation (40 LOC)
- Key loading and validation (30 LOC)
- Error handling patterns
- Logging discipline examples
- Key rotation support (future)

---

## APPENDIX B: COMPENSATING CONTROLS DOCUMENTATION

### Exception: Plaintext Embeddings in Database

**Risk**: Embedding vectors stored in plaintext for ANN indexing

**Business Justification**:
- ANN query performance requires plaintext vector indexing
- Homomorphic encryption (FHE) has 10,000x performance penalty
- Alternative: Secret sharing (research phase, R2 roadmap)

**Compensating Controls**:

1. **Row-Level Security (RLS)** - ✅ IMPLEMENTED (TASK A):
   - PostgreSQL RLS policy enforces tenant isolation
   - Users cannot query other users' rows
   - Database-level enforcement (cannot be bypassed at application layer)

2. **AAD Binding (TASK B)** - ⚠️ PENDING:
   - Text and metadata encrypted with AAD=user_hash
   - Cross-tenant decryption cryptographically impossible
   - Even if database compromised, ciphertext is useless

3. **Encrypted Database Volume**:
   - Full-disk encryption (TDE or dm-crypt)
   - Protects against physical theft
   - Backup encryption enforced

4. **Shadow Backup (emb_cipher)**:
   - Encrypted copy of embedding stored
   - Used for compliance exports
   - Recovery capability if primary embedding lost

5. **Audit Logging**:
   - All memory_chunks access logged
   - Supabase audit logs or CloudWatch
   - Anomaly detection on access patterns

6. **Network Isolation**:
   - Database not publicly accessible
   - TLS enforced (sslmode=require)
   - VPC/private networking

**Residual Risk**: LOW (acceptable for R1 Phase 1)

**Roadmap**: R2 Phase will evaluate homomorphic encryption or secret sharing

---

## APPENDIX C: KEY ROTATION STRATEGY

### Quarterly Rotation (MEMORY_ENCRYPTION_KEY)

**Phase 1: Preparation (Day 0)**
1. Generate new key: MEMORY_ENCRYPTION_KEY_NEW
2. Keep old key: MEMORY_ENCRYPTION_KEY (rename to OLD)
3. Deploy updated environment variables

**Phase 2: Dual-Write (Days 1-30)**
1. New writes use MEMORY_ENCRYPTION_KEY_NEW
2. Reads try NEW key first, fall back to OLD key
3. Background job re-encrypts old blobs:
   ```python
   # Re-encrypt in batches
   for chunk in old_chunks:
       plaintext = open_sealed(chunk.text_cipher, old_key)
       new_cipher = seal(plaintext, new_key)
       update_chunk(chunk.id, new_cipher)
   ```

**Phase 3: Cleanup (Day 31+)**
1. Verify all blobs re-encrypted (monitor logs)
2. Remove MEMORY_ENCRYPTION_KEY_OLD
3. MEMORY_ENCRYPTION_KEY_NEW becomes primary

**Downtime**: ZERO (dual-write ensures availability)

---

**DECISION: SPECIFICATION APPROVED - IMPLEMENTATION REQUIRED BEFORE PRODUCTION**

**Signature**: Claude Code Security Analysis (repo-guardian)
**Date**: 2025-10-19
**Review ID**: TASK_B_SECURITY_AUDIT_PRODUCTION_GATE_001
**Classification**: CRITICAL - Production Blocker

---

**DO NOT DEPLOY TO PRODUCTION WITHOUT**:
1. Implementation complete (src/memory/security.py)
2. Tests passing (tests/memory/test_encryption.py)
3. AAD binding test VERIFIED
4. Security-approved label applied
5. Performance requirements met (>= 5k ops/sec)
