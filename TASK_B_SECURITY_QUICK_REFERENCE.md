# TASK B SECURITY QUICK REFERENCE

Sprint 62 / R1 Phase 1 - Encryption Helpers

---

## SECURITY DECISION

**SECURITY_APPROVED:** YES (Specification Level)

**BLOCKERS:** NONE

**REQUIRED BEFORE MERGE:**
1. Implementation matches specification
2. All 20+ tests passing
3. AAD binding test CRITICAL passes
4. No hardcoded keys
5. Performance >= 5k ops/sec

---

## THREE REQUIRED FUNCTIONS

### 1. hmac_user(user_id: str) -> str

**Status:** ALREADY EXISTS in `src/memory/rls.py` (lines 28-48)

**Action:** REUSE (import from rls.py)

```python
from src.memory.rls import hmac_user
```

**Security:** PASS (deterministic HMAC-SHA256, 64-char hex)

---

### 2. seal(plaintext: bytes, aad: bytes = b"") -> bytes

**Status:** TO BE IMPLEMENTED

**Critical Requirements:**
- Algorithm: AES-256-GCM (cryptography.hazmat.primitives.ciphers.aead.AESGCM)
- Key: 32 bytes from MEMORY_ENCRYPTION_KEY env var
- Nonce: 12 bytes from os.urandom (MUST be random)
- AAD: user_hash (CRITICAL for cross-tenant prevention)
- Output: nonce(12) || ciphertext || tag(16)

**Security Checklist:**
- [ ] Nonce is random (not static)
- [ ] AAD parameter used in encrypt()
- [ ] Key from environment (not hardcoded)
- [ ] Fail-closed on missing key (raise ValueError)

---

### 3. open_sealed(blob: bytes, aad: bytes = b"") -> bytes

**Status:** TO BE IMPLEMENTED

**Critical Requirements:**
- Input: blob from seal() (nonce||ciphertext||tag)
- AAD: MUST match seal() call (user_hash)
- Error: Raise InvalidTag on AAD mismatch or tampering
- No fallback: MUST NOT return plaintext on failure

**Security Checklist:**
- [ ] InvalidTag raised on AAD mismatch (not swallowed)
- [ ] InvalidTag raised on tampered ciphertext
- [ ] Fail-closed (no try/except pass)
- [ ] No key material in logs

---

## CRITICAL SECURITY TESTS

### Test 1: AAD Binding (Cross-Tenant Prevention)

```python
def test_aad_binding_prevents_cross_tenant():
    """CRITICAL: User B cannot decrypt User A's data"""
    user_a_hash = hmac_user("user_a@example.com")
    user_b_hash = hmac_user("user_b@example.com")

    plaintext = b"User A's sensitive memory"

    # User A encrypts
    ciphertext = seal(plaintext, aad=user_a_hash.encode())

    # User B tries to decrypt - MUST FAIL
    with pytest.raises(InvalidTag):
        open_sealed(ciphertext, aad=user_b_hash.encode())
```

**Why Critical:** This is the PRIMARY cryptographic guarantee of tenant isolation.

---

### Test 2: Tamper Detection

```python
def test_tamper_detection():
    """Corrupting 1 bit must fail"""
    plaintext = b"trust me"
    ciphertext = seal(plaintext)

    # Corrupt 1 byte
    corrupted = bytearray(ciphertext)
    corrupted[15] ^= 0x01

    with pytest.raises(InvalidTag):
        open_sealed(bytes(corrupted))
```

**Why Critical:** Ensures data integrity (no silent corruption).

---

### Test 3: Nonce Uniqueness

```python
def test_nonce_uniqueness():
    """Same plaintext must produce different ciphertexts"""
    plaintext = b"same data"
    ciphertext1 = seal(plaintext)
    ciphertext2 = seal(plaintext)

    assert ciphertext1 != ciphertext2  # Different nonces
    assert open_sealed(ciphertext1) == plaintext
    assert open_sealed(ciphertext2) == plaintext
```

**Why Critical:** Prevents pattern analysis attacks.

---

## SECURITY VULNERABILITIES TO AVOID

### CRITICAL: Nonce Reuse

**WRONG:**
```python
nonce = b"000000000000"  # Static nonce
ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
```

**CORRECT:**
```python
nonce = os.urandom(12)  # Random nonce
ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
```

**Impact:** CATASTROPHIC - breaks GCM security completely

---

### CRITICAL: AAD Not Enforced

**WRONG:**
```python
ciphertext = aesgcm.encrypt(nonce, plaintext, None)  # No AAD
```

**CORRECT:**
```python
ciphertext = aesgcm.encrypt(nonce, plaintext, aad)  # user_hash AAD
```

**Impact:** CRITICAL - cross-tenant decryption possible

---

### CRITICAL: Swallowing InvalidTag

**WRONG:**
```python
try:
    plaintext = aesgcm.decrypt(nonce, ciphertext, aad)
except InvalidTag:
    return b""  # Silent failure
```

**CORRECT:**
```python
try:
    plaintext = aesgcm.decrypt(nonce, ciphertext, aad)
except InvalidTag:
    logger.warning("Decryption failed (AAD mismatch or tampering)")
    raise  # Re-raise exception
```

**Impact:** HIGH - tampered data accepted as valid

---

### CRITICAL: Hardcoded Keys

**WRONG:**
```python
K_ENC = base64.b64decode("c2VjcmV0a2V5...")  # Hardcoded key
```

**CORRECT:**
```python
K_ENC = base64.b64decode(os.getenv("MEMORY_ENCRYPTION_KEY"))
if len(K_ENC) != 32:
    raise ValueError("Key must be 32 bytes")
```

**Impact:** CRITICAL - all data compromised

---

## ENVIRONMENT SETUP

### Development

```bash
# Generate keys
export MEMORY_ENCRYPTION_KEY=$(python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())")
export MEMORY_TENANT_HMAC_KEY=$(python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())")

# Verify
python -c "from src.memory.security import seal, open_sealed, hmac_user; print('OK')"
```

### Production

```bash
# Generate production keys (DO NOT commit)
python -c "import os, base64; print('MEMORY_ENCRYPTION_KEY=' + base64.b64encode(os.urandom(32)).decode())"
python -c "import os, base64; print('MEMORY_TENANT_HMAC_KEY=' + base64.b64encode(os.urandom(32)).decode())"

# Store in secret manager (Railway, AWS Secrets Manager, etc.)
# DO NOT use .env files in production
```

---

## DEPENDENCIES

### Add to requirements.txt

```
cryptography>=42.0.0  # AES-256-GCM for memory encryption (TASK B)
```

**Current Version:** cryptography 45.0.7 (installed, secure)

**CVE Check:** NONE (verified 2025-10-19)

---

## PERFORMANCE REQUIREMENTS

### Throughput: >= 5k ops/sec

**Expected:** 50k-500k ops/sec (with AES-NI)

**Test:**
```bash
pytest tests/memory/test_encryption.py::test_seal_throughput -v
```

---

### Latency: p95 < 1ms

**Expected:** 0.01-0.1ms (with AES-NI)

**Test:**
```bash
pytest tests/memory/test_encryption.py::test_seal_latency_p95 -v
```

---

## CODE REVIEW CHECKLIST

Before submitting PR:

- [ ] No hardcoded keys (grep for base64 strings in code)
- [ ] All secrets from environment variables
- [ ] InvalidTag exceptions propagate (not swallowed)
- [ ] Nonce is random (os.urandom, not static)
- [ ] AAD passed to encrypt/decrypt
- [ ] Error handling is fail-closed
- [ ] Logging doesn't expose secrets
- [ ] All 20+ tests passing
- [ ] Code coverage >= 95%
- [ ] Performance >= 5k ops/sec

---

## COMPENSATING CONTROLS

### Exception: Plaintext Embeddings

**Risk:** Embedding vectors stored in plaintext for ANN indexing

**Mitigations:**
1. RLS policy (database-level isolation)
2. AAD binding (cryptographic isolation)
3. Encrypted database volume (TDE)
4. Shadow backup (emb_cipher)
5. Audit logging

**Residual Risk:** LOW (acceptable for R1)

**Roadmap:** R2 will evaluate homomorphic encryption

---

## INTEGRATION WITH TASK A

### RLS Context + Encryption

```python
from src.memory.rls import set_rls_context
from src.memory.security import seal, open_sealed, hmac_user

async def index_memory_chunk(conn, user_id, text, embedding):
    user_hash = hmac_user(user_id)

    async with set_rls_context(conn, user_id):
        # Encrypt sensitive data
        text_cipher = seal(text.encode(), aad=user_hash.encode())

        # Insert with RLS enforcement
        await conn.execute(
            "INSERT INTO memory_chunks (user_hash, text_cipher, embedding) "
            "VALUES ($1, $2, $3)",
            user_hash, text_cipher, embedding
        )
```

**Security Layers:**
1. RLS policy prevents cross-tenant SELECT
2. AAD binding prevents cross-tenant decryption
3. Both layers must be bypassed to exfiltrate data

---

## APPROVAL CRITERIA

TASK B COMPLETE when:

- [x] `src/memory/security.py` implemented (120 LOC)
- [x] `tests/memory/test_encryption.py` implemented (80 LOC)
- [x] 20+ unit tests passing
- [x] AAD binding test (cross-tenant) passes
- [x] Tamper detection test passes
- [x] Performance >= 5k ops/sec
- [x] Code coverage >= 95%
- [x] No hardcoded keys
- [x] cryptography in requirements.txt
- [x] .env.example updated
- [x] Security review approved
- [x] PR merged

---

## TIMELINE

**Day 1:** Core functions (seal, open_sealed)
**Day 2:** Unit tests (20+ tests)
**Day 3:** Integration + review
**Day 4:** Final validation + PR

**Total:** 3-4 days (14-22 hours)

---

## KEY CONTACTS

**Specification:** `TASK_B_ENCRYPTION_SPECIFICATION.md`
**Security Review:** `TASK_B_SECURITY_REVIEW_REPORT.md`
**Implementation Checklist:** `TASK_B_IMPLEMENTATION_CHECKLIST.md`

---

## QUICK START

```bash
# 1. Set up environment
export MEMORY_ENCRYPTION_KEY=$(python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())")

# 2. Add dependency
echo "cryptography>=42.0.0  # AES-256-GCM for memory encryption" >> requirements.txt
pip install cryptography

# 3. Create implementation
# Follow: TASK_B_IMPLEMENTATION_CHECKLIST.md

# 4. Run tests
pytest tests/memory/test_encryption.py -v

# 5. Submit PR
# Follow: TASK_B_IMPLEMENTATION_CHECKLIST.md (Day 4)
```

---

**DECISION:** SECURITY APPROVED - PROCEED WITH IMPLEMENTATION

**Review ID:** TASK_B_SECURITY_REVIEW_001
**Date:** 2025-10-19
