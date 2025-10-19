# TASK B IMPLEMENTATION CHECKLIST

Sprint 62 / R1 Phase 1 - Encryption Helpers Security Implementation

---

## PRE-IMPLEMENTATION (Before Starting)

- [ ] Read full specification: `TASK_B_ENCRYPTION_SPECIFICATION.md`
- [ ] Read security review: `TASK_B_SECURITY_REVIEW_REPORT.md`
- [ ] Verify cryptography library installed: `pip list | grep cryptography`
- [ ] Add to requirements.txt: `cryptography>=42.0.0`
- [ ] Update .env.example with key generation instructions
- [ ] Set up test environment with MEMORY_ENCRYPTION_KEY

---

## DAY 1: CORE FUNCTIONS (4-6 hours)

### File: `src/memory/security.py`

- [ ] Create file with module docstring
- [ ] Import dependencies:
  ```python
  import base64
  import logging
  import os
  from cryptography.hazmat.primitives.ciphers.aead import AESGCM
  from cryptography.exceptions import InvalidTag
  from src.memory.rls import hmac_user
  ```

- [ ] Implement `_load_encryption_key()`:
  - [ ] Read MEMORY_ENCRYPTION_KEY from environment
  - [ ] Base64 decode
  - [ ] Validate 32 bytes (AES-256)
  - [ ] Raise ValueError if missing/invalid (fail-closed)

- [ ] Load key at module level:
  ```python
  try:
      K_ENC = _load_encryption_key()
  except ValueError as e:
      logger.critical(f"Key loading failed: {e}")
      raise
  ```

- [ ] Implement `seal(plaintext: bytes, aad: bytes = b"") -> bytes`:
  - [ ] Type check inputs (must be bytes)
  - [ ] Generate nonce: `nonce = os.urandom(12)`
  - [ ] Create AESGCM instance: `aesgcm = AESGCM(K_ENC)`
  - [ ] Encrypt: `ciphertext = aesgcm.encrypt(nonce, plaintext, aad)`
  - [ ] Return: `nonce + ciphertext`
  - [ ] Add debug logging (no secrets)

- [ ] Implement `open_sealed(blob: bytes, aad: bytes = b"") -> bytes`:
  - [ ] Type check inputs
  - [ ] Validate minimum length: `>= 28 bytes`
  - [ ] Extract nonce: `blob[:12]`
  - [ ] Extract ciphertext: `blob[12:]`
  - [ ] Decrypt: `plaintext = aesgcm.decrypt(nonce, ciphertext, aad)`
  - [ ] Handle InvalidTag: log warning, re-raise (no swallow)
  - [ ] Add debug logging

- [ ] Re-export hmac_user:
  ```python
  # Already imported above
  __all__ = ['seal', 'open_sealed', 'hmac_user']
  ```

**Checkpoint:** Run basic import test:
```bash
python -c "from src.memory.security import seal, open_sealed, hmac_user; print('OK')"
```

---

## DAY 2: UNIT TESTS (4-6 hours)

### File: `tests/memory/test_encryption.py`

### Round-Trip Tests (30 min)

- [ ] Test: `test_seal_open_roundtrip_basic()`
  - [ ] Encrypt plaintext, decrypt, assert equal

- [ ] Test: `test_seal_open_with_aad()`
  - [ ] Encrypt with user_hash AAD, decrypt with same AAD

- [ ] Test: `test_seal_open_empty_plaintext()`
  - [ ] Encrypt b"", verify round-trip

- [ ] Test: `test_seal_open_large_plaintext()`
  - [ ] Encrypt 100KB data, verify round-trip

- [ ] Test: `test_seal_open_unicode_plaintext()`
  - [ ] Encrypt UTF-8 encoded text

### AAD Binding Tests (45 min) - CRITICAL

- [ ] Test: `test_aad_binding_correct_aad_succeeds()`
  - [ ] Encrypt with AAD, decrypt with same AAD passes

- [ ] Test: `test_aad_binding_wrong_aad_fails()` **CRITICAL**
  - [ ] Encrypt with AAD_A, decrypt with AAD_B raises InvalidTag
  - [ ] `with pytest.raises(InvalidTag):`

- [ ] Test: `test_aad_binding_empty_vs_nonempty()`
  - [ ] Encrypt with b"", decrypt with b"aad" raises InvalidTag

- [ ] Test: `test_aad_binding_cross_tenant_prevention()` **CRITICAL**
  - [ ] User A encrypts with user_hash_a
  - [ ] User B tries to decrypt with user_hash_b
  - [ ] MUST raise InvalidTag

- [ ] Test: `test_aad_case_sensitive()`
  - [ ] Verify AAD is byte-exact (not case-insensitive)

### Tamper Detection Tests (30 min)

- [ ] Test: `test_tamper_ciphertext_fails()`
  - [ ] Corrupt 1 byte in ciphertext, decrypt raises InvalidTag

- [ ] Test: `test_tamper_nonce_fails()`
  - [ ] Corrupt 1 byte in nonce, decrypt raises InvalidTag

- [ ] Test: `test_tamper_tag_fails()`
  - [ ] Corrupt auth tag, decrypt raises InvalidTag

### Nonce Uniqueness Tests (15 min)

- [ ] Test: `test_nonce_uniqueness_different_ciphertexts()`
  - [ ] Encrypt same plaintext twice, verify different outputs

- [ ] Test: `test_nonce_uniqueness_both_decrypt()`
  - [ ] Verify both ciphertexts decrypt correctly

### Performance Tests (30 min)

- [ ] Test: `test_seal_throughput()`
  - [ ] 5000 seal operations
  - [ ] Assert ops/sec >= 5000

- [ ] Test: `test_seal_latency_p95()`
  - [ ] 1000 seal operations
  - [ ] Measure times, assert p95 < 1ms

### Error Handling Tests (30 min)

- [ ] Test: `test_missing_encryption_key_raises()`
  - [ ] Unset env var, import raises ValueError

- [ ] Test: `test_invalid_key_format_raises()`
  - [ ] Set invalid base64, import raises ValueError

- [ ] Test: `test_wrong_key_length_raises()`
  - [ ] Set 16-byte key (AES-128), import raises ValueError

- [ ] Test: `test_open_sealed_invalid_blob_length()`
  - [ ] Pass 10-byte blob, raises ValueError

- [ ] Test: `test_seal_non_bytes_plaintext_raises()`
  - [ ] Pass string instead of bytes, raises TypeError

### Edge Cases (30 min)

- [ ] Test: `test_seal_very_large_plaintext()`
  - [ ] 10MB plaintext (stress test)

- [ ] Test: `test_seal_binary_data()`
  - [ ] Random binary data (not UTF-8)

- [ ] Test: `test_nonce_length_is_12_bytes()`
  - [ ] Extract nonce, assert len == 12

**Checkpoint:** Run all tests:
```bash
pytest tests/memory/test_encryption.py -v
```

**Required:** All 20+ tests pass

---

## DAY 3: INTEGRATION & REVIEW (4-6 hours)

### Integration Tests

- [ ] Test with actual RLS context:
  ```python
  async def test_encrypt_with_rls_context():
      user_id = "test@example.com"
      user_hash = hmac_user(user_id)
      plaintext = b"memory chunk"

      # Encrypt
      ciphertext = seal(plaintext, aad=user_hash.encode())

      # Store in mock database
      # Retrieve and decrypt
      decrypted = open_sealed(ciphertext, aad=user_hash.encode())
      assert decrypted == plaintext
  ```

- [ ] Test cross-tenant isolation end-to-end

### Code Review Checklist

- [ ] No hardcoded keys (grep for base64 strings):
  ```bash
  grep -r "b64decode.*=.*['\"]" src/memory/security.py
  ```
  (Should find NONE except in key loading)

- [ ] All secrets from environment variables

- [ ] Error handling is fail-closed (no try/except pass)

- [ ] InvalidTag exceptions propagate correctly

- [ ] Logging doesn't expose secrets:
  - [ ] No key material logged
  - [ ] No plaintext logged
  - [ ] Only metadata (lengths, user_hash prefix)

- [ ] Type hints correct:
  ```python
  def seal(plaintext: bytes, aad: bytes = b"") -> bytes:
  ```

- [ ] Docstrings complete with security notes

### Performance Verification

- [ ] Run performance tests on target hardware:
  ```bash
  pytest tests/memory/test_encryption.py::test_seal_throughput -v -s
  pytest tests/memory/test_encryption.py::test_seal_latency_p95 -v -s
  ```

- [ ] If < 5k ops/sec, check:
  - [ ] AES-NI enabled: `lscpu | grep aes` (Linux) or `sysctl hw.optional.aes` (Mac)
  - [ ] cryptography library version
  - [ ] CPU model

### Documentation Updates

- [ ] Update `.env.example`:
  ```bash
  # Memory Encryption (Sprint 62 TASK B)
  MEMORY_ENCRYPTION_KEY=  # Generate: python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
  MEMORY_TENANT_HMAC_KEY=  # Generate: python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
  ```

- [ ] Add to requirements.txt:
  ```
  cryptography>=42.0.0  # AES-256-GCM for memory encryption (TASK B)
  ```

- [ ] Update TASK_A_COMPLETION_SUMMARY.md (link to TASK B)

---

## DAY 4: FINAL VALIDATION (2-4 hours)

### Security Code Review

- [ ] Review with security checklist from `TASK_B_SECURITY_REVIEW_REPORT.md`

- [ ] Verify all CRITICAL tests pass:
  - [ ] `test_aad_binding_wrong_aad_fails`
  - [ ] `test_aad_binding_cross_tenant_prevention`
  - [ ] `test_tamper_ciphertext_fails`

- [ ] Code coverage check:
  ```bash
  pytest tests/memory/test_encryption.py --cov=src.memory.security --cov-report=term-missing
  ```
  - [ ] Assert coverage >= 95%

### Integration with TASK A

- [ ] Verify hmac_user import works:
  ```python
  from src.memory.security import hmac_user
  from src.memory.rls import hmac_user as rls_hmac_user
  assert hmac_user == rls_hmac_user  # Same function
  ```

- [ ] Test with RLS context:
  ```python
  from src.memory.rls import set_rls_context
  from src.memory.security import seal, open_sealed, hmac_user
  # Integration test
  ```

### Pre-Merge Checklist

- [ ] All unit tests pass (20+ tests)
- [ ] Code coverage >= 95%
- [ ] No hardcoded keys
- [ ] cryptography in requirements.txt
- [ ] .env.example updated
- [ ] Performance requirements met (>= 5k ops/sec)
- [ ] Security review approved
- [ ] PR description includes:
  - [ ] Test results summary
  - [ ] Performance metrics
  - [ ] Security considerations
  - [ ] Breaking changes (none expected)

### Create PR

```bash
git checkout -b feature/task-b-encryption
git add src/memory/security.py
git add tests/memory/test_encryption.py
git add requirements.txt
git add .env.example
git commit -m "feat(memory): add AES-256-GCM encryption with AAD binding (TASK B)

Implements encryption helpers for memory chunks:
- seal() - AES-256-GCM encryption with user_hash AAD
- open_sealed() - Decryption with tamper detection
- hmac_user() - Re-exported from rls.py for convenience

Security:
- AAD binding prevents cross-tenant decryption
- Cryptographically secure nonces (os.urandom)
- Fail-closed error handling
- 20+ unit tests with 95%+ coverage
- Performance: 50k+ ops/sec (exceeds 5k requirement)

Tests:
- Round-trip encryption/decryption
- AAD binding (cross-tenant prevention)
- Tamper detection (InvalidTag on corruption)
- Performance (throughput and latency)

Refs: TASK_B_ENCRYPTION_SPECIFICATION.md
Security Review: TASK_B_SECURITY_REVIEW_REPORT.md

Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"

git push origin feature/task-b-encryption
```

- [ ] Create GitHub PR
- [ ] Request review from security lead
- [ ] Add label: `security-critical`
- [ ] Link to TASK B specification

---

## POST-MERGE (After Approval)

### Staging Deployment

- [ ] Generate staging keys:
  ```bash
  python -c "import os, base64; print('STAGING_MEMORY_ENCRYPTION_KEY=' + base64.b64encode(os.urandom(32)).decode())"
  ```

- [ ] Deploy to staging environment

- [ ] Run integration tests:
  ```bash
  pytest tests/memory/test_encryption.py --env=staging
  ```

- [ ] Verify no errors in logs

### Ready for TASK D

- [ ] TASK B complete
- [ ] Functions available for import:
  ```python
  from src.memory.security import seal, open_sealed, hmac_user
  ```

- [ ] TASK D (API endpoints) can start implementation

---

## TROUBLESHOOTING

### Import Errors

**Error:** `ModuleNotFoundError: No module named 'cryptography'`

**Fix:**
```bash
pip install cryptography>=42.0.0
```

---

### Key Loading Errors

**Error:** `ValueError: MEMORY_ENCRYPTION_KEY not set`

**Fix:**
```bash
export MEMORY_ENCRYPTION_KEY=$(python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())")
```

---

### Performance Issues

**Symptom:** `test_seal_throughput` fails (< 5k ops/sec)

**Debug:**
1. Check AES-NI support:
   ```bash
   # Linux
   lscpu | grep aes

   # Mac
   sysctl hw.optional.aes
   ```

2. Check cryptography version:
   ```bash
   pip show cryptography
   # Should be >= 42.0.0
   ```

3. Profile with smaller workload:
   ```python
   import time
   from src.memory.security import seal

   plaintext = b"x" * 1024
   t0 = time.perf_counter()
   for _ in range(100):
       seal(plaintext, aad=b"test")
   elapsed = time.perf_counter() - t0
   print(f"Ops/sec: {100/elapsed:.0f}")
   ```

---

### Test Failures

**Test:** `test_aad_binding_wrong_aad_fails` fails (no exception raised)

**Cause:** AAD not being passed to AESGCM.encrypt/decrypt

**Fix:** Ensure AAD parameter is passed:
```python
ciphertext = aesgcm.encrypt(nonce, plaintext, aad)  # ← aad parameter required
```

---

## SUCCESS CRITERIA

TASK B is COMPLETE when:

- [x] All checklist items above completed
- [x] `src/memory/security.py` implemented (120 LOC)
- [x] `tests/memory/test_encryption.py` implemented (80 LOC)
- [x] 20+ unit tests passing
- [x] Code coverage >= 95%
- [x] Performance >= 5k ops/sec (p95 < 1ms)
- [x] Security review approved
- [x] PR merged to release/r0.5-hotfix
- [x] Ready for TASK D integration

---

## CONTACTS

**Implementation Lead:** [Your Name]
**Security Reviewer:** repo-guardian (automated review)
**Code Reviewer:** [Security Lead Name]
**Integration (TASK D):** [API Team Lead]

---

**Estimated Timeline:**
- Day 1: Core functions (4-6h)
- Day 2: Unit tests (4-6h)
- Day 3: Integration & review (4-6h)
- Day 4: Final validation & PR (2-4h)

**Total:** 14-22 hours (3-4 days)

---

**START NOW:** Begin with Day 1 checklist above
