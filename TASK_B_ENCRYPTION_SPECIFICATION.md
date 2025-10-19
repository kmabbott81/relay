# TASK B: Encryption Helpers + Write Path — Complete Specification

**Sprint**: 62 / R1 Phase 1
**Task**: B (Blocker - Parallel with C)
**Duration**: 3-4 days (implementation + integration testing)
**Estimated LOC**: 120 (core) + 80 (tests) = 200 LOC
**Risk Level**: HIGH (cryptography + key rotation)
**Dependencies**: ✅ TASK A complete (schema + RLS ready)
**Blockers**: None (can run parallel with C)

---

## 🎯 Objective

Implement AES-256-GCM encryption for memory chunks:
- Deterministic HMAC-SHA256 for user_hash (tenant isolation)
- Symmetric encryption for plaintext, metadata, shadow embeddings
- Integration into indexing/write pipeline
- Round-trip validation and tamper detection
- Compensating controls: RLS + encrypted volume + shadow backup

---

## 📦 Deliverables

### 1. Security Module (`src/memory/security.py`)

#### Functions to Implement

##### `hmac_user(user_id: str) -> str`

Compute deterministic HMAC-SHA256 for tenant isolation.

```python
def hmac_user(user_id: str) -> str:
    """
    Compute HMAC-SHA256(MEMORY_TENANT_HMAC_KEY, user_id).

    Returns: 64-character hex string (deterministic per user_id)

    Usage:
        user_hash = hmac_user("user_123@company.com")
        # Set RLS context
        await set_rls_context(conn, user_id)
    """
    key = MEMORY_TENANT_HMAC_KEY.encode('utf-8')
    msg = user_id.encode('utf-8')
    return hmac.new(key, msg, hashlib.sha256).hexdigest()
```

**Tests**:
- ✅ Deterministic (same input → same output)
- ✅ Different users → different hashes
- ✅ 64-character hex string
- ✅ Consistent with `src/memory/rls.py` implementation

---

##### `seal(plaintext: bytes, aad: bytes = b"") -> bytes`

Encrypt plaintext with AES-256-GCM.

```python
def seal(plaintext: bytes, aad: bytes = b"") -> bytes:
    """
    Encrypt plaintext with AES-256-GCM.

    Args:
        plaintext: Data to encrypt (bytes)
        aad: Additional Authenticated Data (default: empty, can bind to user_hash)

    Returns:
        nonce (12 bytes) || ciphertext || tag (nonce||ct is standard)

    Format: [12-byte nonce][ciphertext][16-byte auth tag]
    Total overhead: ~28 bytes per message

    Usage:
        plaintext = "sensitive memory chunk"
        ciphertext = seal(plaintext.encode(), aad=user_hash.encode())
        # Store ciphertext in database

    Raises:
        ValueError: If encryption key not set or invalid
    """
    # Use MEMORY_ENCRYPTION_KEY (32-byte base64 decoded)
    # Generate random 12-byte nonce
    # Return: nonce || ciphertext (GCM includes auth tag)
```

**Implementation Details**:
```python
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MEMORY_ENCRYPTION_KEY = os.getenv("MEMORY_ENCRYPTION_KEY")
if not MEMORY_ENCRYPTION_KEY:
    raise ValueError("MEMORY_ENCRYPTION_KEY not set")

# Base64 decode the key (32 bytes for AES-256)
K_ENC = base64.b64decode(MEMORY_ENCRYPTION_KEY)
assert len(K_ENC) == 32, "Key must be 32 bytes (AES-256)"

def seal(plaintext: bytes, aad: bytes = b"") -> bytes:
    aesgcm = AESGCM(K_ENC)
    nonce = os.urandom(12)  # Unique per encryption
    ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
    return nonce + ciphertext  # Format: nonce||ct||tag
```

**Tests**:
- ✅ Encryption/decryption round-trip
- ✅ Ciphertext ≠ plaintext
- ✅ Nonce is random (different each time)
- ✅ AAD binding (wrong AAD → decryption fails)
- ✅ Tamper detection (1-bit corruption → failure)
- ✅ > 5k ops/sec throughput

---

##### `open_sealed(blob: bytes, aad: bytes = b"") -> bytes`

Decrypt ciphertext with AES-256-GCM.

```python
def open_sealed(blob: bytes, aad: bytes = b"") -> bytes:
    """
    Decrypt ciphertext with AES-256-GCM.

    Args:
        blob: Encrypted data (nonce||ciphertext||tag)
        aad: Additional Authenticated Data (must match seal() call)

    Returns:
        Plaintext (bytes)

    Raises:
        cryptography.exceptions.InvalidTag: If authentication fails
        ValueError: If blob format invalid, key missing, etc.

    Usage:
        ciphertext = ... # from database
        plaintext = open_sealed(ciphertext, aad=user_hash.encode())
    """
    # Extract nonce (first 12 bytes)
    # Decrypt remaining bytes (ciphertext + tag)
    # Return plaintext
```

**Implementation Details**:
```python
def open_sealed(blob: bytes, aad: bytes = b"") -> bytes:
    aesgcm = AESGCM(K_ENC)
    nonce = blob[:12]
    ciphertext = blob[12:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, aad)
    return plaintext
```

**Tests**:
- ✅ Round-trip decryption
- ✅ AAD mismatch raises exception
- ✅ Tampered ciphertext raises exception
- ✅ Invalid nonce length raises exception
- ✅ Missing key raises ValueError (fail-closed)

---

### 2. Write Path Integration

#### Update Memory Index Pipeline

Location: `src/memory/index.py` (NEW or integrate into existing endpoint in TASK D)

**Write flow**:

```python
async def index_memory_chunk(
    conn: asyncpg.Connection,
    user_id: str,
    doc_id: str,
    source: str,
    text: str,
    embedding: list[float],  # np.array of shape (1536,)
    metadata: dict = None,
    chunk_index: int = 0,
):
    """
    Index memory chunk with encryption.

    Flow:
    1. Compute user_hash = hmac_user(user_id)
    2. Set RLS context (await set_rls_context(conn, user_id))
    3. Encrypt text, metadata, embedding (shadow backup)
    4. Store plaintext embedding for ANN indexing
    5. Insert into memory_chunks with RLS enforcement
    """

    # Step 1: User isolation
    user_hash = hmac_user(user_id)

    # Step 2: Set RLS context for database enforcement
    async with set_rls_context(conn, user_id):

        # Step 3: Encrypt sensitive data
        text_bytes = text.encode('utf-8')
        text_cipher = seal(text_bytes, aad=user_hash.encode())

        meta_json = json.dumps(metadata or {})
        meta_cipher = seal(meta_json.encode(), aad=user_hash.encode())

        # Embedding: convert to bytes for shadow backup
        embedding_bytes = np.array(embedding, dtype=np.float32).tobytes()
        emb_cipher = seal(embedding_bytes, aad=user_hash.encode())

        # Step 4: Convert embedding to pgvector format
        embedding_vector = embedding  # stays plaintext for ANN

        # Step 5: Insert with RLS enforcement
        await conn.execute("""
            INSERT INTO memory_chunks (
                user_hash,
                doc_id,
                source,
                text_plain,
                text_cipher,
                meta_cipher,
                embedding,
                emb_cipher,
                chunk_index,
                created_at,
                updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7::vector, $8, $9, NOW(), NOW())
        """, (
            user_hash,
            doc_id,
            source,
            text,  # Optional: store plaintext for backward compat
            text_cipher,
            meta_cipher,
            embedding_vector,
            emb_cipher,
            chunk_index,
        ))

    logger.info(f"Indexed chunk: user_id={user_id[:8]}..., doc={doc_id}, "
                f"text_len={len(text)}, cipher_len={len(text_cipher)}")
```

**Tests**:
- ✅ Round-trip: index → decrypt → verify plaintext matches
- ✅ AAD binding: wrong user_hash fails decryption
- ✅ Plaintext embedding stays in DB for ANN
- ✅ Shadow backup encrypts embedding
- ✅ RLS enforced (user A cannot see user B's rows)
- ✅ Latency: < 100ms per chunk (seal/open overhead)

---

### 3. Unit Tests (`tests/memory/test_encryption.py`)

**Test Structure**:

```python
# tests/memory/test_encryption.py

import pytest
import asyncpg
import os
from src.memory.security import seal, open_sealed, hmac_user
from cryptography.hazmat.exceptions import InvalidTag

class TestSealRoundTrip:
    """Round-trip encryption/decryption"""

    def test_seal_open_symmetric(self):
        """Seal→Open restores original plaintext"""
        plaintext = b"sensitive memory"
        encrypted = seal(plaintext)
        decrypted = open_sealed(encrypted)
        assert decrypted == plaintext

    def test_seal_aad_binding(self):
        """AAD mismatch raises InvalidTag"""
        plaintext = b"secret"
        user_hash_a = "user_hash_aaa"
        user_hash_b = "user_hash_bbb"

        # Encrypt with user_hash_a
        encrypted = seal(plaintext, aad=user_hash_a.encode())

        # Decrypt with user_hash_b → should fail
        with pytest.raises(InvalidTag):
            open_sealed(encrypted, aad=user_hash_b.encode())

    def test_seal_tamper_detection(self):
        """Corrupting 1 bit fails authentication"""
        plaintext = b"trust me"
        encrypted = seal(plaintext)

        # Corrupt 1 byte in middle of ciphertext
        corrupted = bytearray(encrypted)
        corrupted[15] ^= 0x01  # Flip 1 bit

        with pytest.raises(InvalidTag):
            open_sealed(bytes(corrupted))

    def test_seal_nonce_uniqueness(self):
        """Each encryption uses different nonce"""
        plaintext = b"same data"
        encrypted1 = seal(plaintext)
        encrypted2 = seal(plaintext)

        # Different nonces → different ciphertexts
        assert encrypted1 != encrypted2

        # But both decrypt correctly
        assert open_sealed(encrypted1) == plaintext
        assert open_sealed(encrypted2) == plaintext

class TestEncryptionThroughput:
    """Performance: throughput and latency"""

    def test_seal_throughput(self):
        """seal() ≥ 5k ops/sec"""
        import time
        plaintext = b"x" * 1024  # 1KB chunks

        t0 = time.perf_counter()
        for _ in range(5000):
            seal(plaintext)
        elapsed = time.perf_counter() - t0

        ops_per_sec = 5000 / elapsed
        assert ops_per_sec >= 5000, f"Throughput too low: {ops_per_sec:.0f}/sec"

    def test_seal_latency_p95(self):
        """seal() p95 < 1ms"""
        import time
        plaintext = b"x" * 1024
        times = []

        for _ in range(1000):
            t0 = time.perf_counter()
            seal(plaintext)
            times.append((time.perf_counter() - t0) * 1000)  # ms

        p95 = np.percentile(times, 95)
        assert p95 < 1.0, f"Latency too high: p95={p95:.2f}ms"

class TestIntegration:
    """Integration with memory_chunks pipeline"""

    @pytest.mark.asyncio
    async def test_index_with_encryption(self, mock_conn):
        """Write path encrypts data correctly"""
        user_id = "test_user@example.com"
        text = "Memory chunk content"
        embedding = [0.1] * 1536

        # Would call: await index_memory_chunk(...)
        # Verify: text_cipher stored, emb_cipher stored, plaintext embedding stored

    @pytest.mark.asyncio
    async def test_aad_binding_prevents_cross_tenant(self, mock_conn):
        """Wrong AAD (cross-tenant) fails decryption"""
        # User A encrypts with user_hash_a
        # User B tries to decrypt with user_hash_b → fails (RLS + AAD)
```

---

## 🔐 Key Management

### Environment Variables

```bash
# Required for encryption
MEMORY_ENCRYPTION_KEY=<32-byte base64>
MEMORY_TENANT_HMAC_KEY=<32-byte base64>

# Example generation (ops/DevOps):
python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
```

### Key Rotation Strategy

| Key | Rotation | Method | Downtime |
|-----|----------|--------|----------|
| `MEMORY_ENCRYPTION_KEY` | Quarterly | Dual-write (new + old), gradual re-encrypt | None |
| `MEMORY_TENANT_HMAC_KEY` | Annually | Requires full reindex (plan in R2) | ~2h |

**Dual-write for MEMORY_ENCRYPTION_KEY**:
1. Keep old key in `MEMORY_ENCRYPTION_KEY_OLD`
2. New writes use new key
3. Reads try new key; if fail, try old key
4. Background job re-encrypts old blobs
5. Drop old key once all blobs migrated

### Compensating Controls

**Threat**: Plaintext embeddings in database for ANN indexing.

**Mitigations**:
1. **RLS Policy** (TASK A): Only user can see their rows
2. **Encrypted Volume**: Database volume encrypted at rest (TDE/dm-crypt)
3. **Shadow Backup** (emb_cipher): Embedding stored encrypted for export/compliance
4. **Audit Logging**: All access logged (Supabase or CloudWatch)
5. **R2 Roadmap**: Implement FHE or secret sharing for full homomorphic encryption

**Exception Documentation**:
> ANN query performance requires plaintext vector indexing. Compensating controls (RLS, volume encryption, shadow backup, audit logging) enforce tenant isolation and provide recovery/compliance options. Full end-to-end encryption deferred to R2 (homomorphic encryption or secret sharing).

---

## ⚠️ Failure Modes & Error Handling

### Fail-Closed Defaults

```python
# Missing key → immediate 500 error (no fallback to plaintext)
if not MEMORY_ENCRYPTION_KEY:
    raise ValueError("MEMORY_ENCRYPTION_KEY must be set")

# Decryption failure → log + re-raise (don't swallow)
try:
    plaintext = open_sealed(blob, aad)
except InvalidTag as e:
    logger.error(f"Decryption failed (possible tampering): blob_size={len(blob)}")
    raise HTTPException(status_code=500, detail="Decryption failed")
```

### Audit Log on Crypto Operations

```python
async def seal_with_audit(plaintext: bytes, user_id: str, doc_id: str):
    """Encrypt and log for compliance"""
    encrypted = seal(plaintext, aad=user_id.encode())

    # Log to audit trail
    logger.info(
        "CRYPTO_ENCRYPT",
        extra={
            "user_id": user_id,
            "doc_id": doc_id,
            "plaintext_size": len(plaintext),
            "ciphertext_size": len(encrypted),
            "timestamp": datetime.utcnow().isoformat(),
        }
    )

    return encrypted
```

---

## 📋 Acceptance Criteria (Gate Condition)

✅ **TASK B Complete when:**

- [ ] `src/memory/security.py` implemented (120 LOC)
  - [ ] `hmac_user()` deterministic and consistent
  - [ ] `seal()` produces nonce||ciphertext format
  - [ ] `open_sealed()` recovers plaintext exactly
  - [ ] AAD binding enforced (wrong AAD fails)
  - [ ] Tamper detection working (1-bit corruption fails)

- [ ] Unit tests passing (80 LOC)
  - [ ] 20+ test cases
  - [ ] Round-trip tests
  - [ ] AAD binding tests
  - [ ] Tamper detection tests
  - [ ] Throughput > 5k ops/sec
  - [ ] Latency p95 < 1ms

- [ ] Write path integrated & tested
  - [ ] `index_memory_chunk()` encrypts text/meta/embedding
  - [ ] Plaintext embedding stored for ANN
  - [ ] Shadow emb_cipher stored for compliance
  - [ ] RLS context applied automatically
  - [ ] End-to-end latency < 100ms per chunk

- [ ] Key management documented
  - [ ] Rotation strategy defined
  - [ ] Dual-write procedure for `MEMORY_ENCRYPTION_KEY`
  - [ ] Compensating controls documented
  - [ ] Fail-closed defaults implemented

- [ ] Compensating controls documented
  - [ ] Exception note: plaintext vectors for ANN performance
  - [ ] Mitigations: RLS + volume encryption + shadow backup
  - [ ] R2 roadmap: FHE or secret sharing

- [ ] repo-guardian: `security-approved` label
  - [ ] Code reviewed for crypto correctness
  - [ ] No hardcoded keys
  - [ ] Error handling fail-closed

---

## 🚀 Integration Points (Ready for TASK D)

**TASK B outputs feed into TASK D**:

```python
# TASK D will use these functions:
from src.memory.security import seal, open_sealed, hmac_user

async def index_memory(request: MemoryIndexRequest, user: User):
    """POST /api/v1/memory/index"""
    user_id = user.id
    user_hash = hmac_user(user_id)

    # Write path (uses TASK B functions)
    async with set_rls_context(conn, user_id):
        for chunk in chunks:
            text_cipher = seal(chunk.text.encode(), aad=user_hash.encode())
            # ... insert into memory_chunks
```

---

## 🔄 Dependencies & Blockers

**Blocks**: TASK D (API endpoints)
**Blocked by**: ✅ TASK A (schema complete)
**Parallel**: TASK C (GPU + CE service)

**Critical Path**:
```
TASK A (✅ done) → TASK B (START NOW) → TASK D (wait for B)
                  ↓
                TASK C (start now, parallel) → TASK E → TASK F
```

---

**Start Date**: Immediately (after TASK A commit)
**Estimated Completion**: 3-4 days (by end of sprint week 1)
**Security Review**: repo-guardian must approve before merge
