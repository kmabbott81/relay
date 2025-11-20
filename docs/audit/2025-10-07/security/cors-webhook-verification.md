# CORS & Webhook Signing Verification - 2025-10-07

## CORS Configuration

**Source:** `src/webapi.py`

### Allowed Origins
```python
origins = [
    "https://relay-studio-one.vercel.app",  # Production
    "http://localhost:3000",  # Local development
]
```

### Allowed Methods
- GET
- POST
- PUT
- DELETE
- OPTIONS

### Allowed Headers
- `Content-Type`
- `Authorization`
- `X-API-Key`
- `Idempotency-Key`
- `X-Signature`
- `X-Request-ID`

### Exposed Headers
- `X-Request-ID`
- `X-Trace-Link`
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`
- `Retry-After`

### Credentials
- `allow_credentials=True`

**Status:** ✅ CORS properly configured

---

## Webhook Signing

**Source:** `src/actions/adapters/independent.py`

### Signing Method
- Algorithm: HMAC-SHA256
- Header: `X-Signature: sha256=<hex_digest>`
- Secret: `ACTIONS_SIGNING_SECRET` environment variable

### Enforcement
- **Enabled when:** `ACTIONS_SIGNING_SECRET` is set
- **Implementation:** Sprint 50 (already deployed)
- **Documentation:** `docs/security/WEBHOOK_SIGNING.md` (Sprint 51 Phase 2)

### Unit Tests
- **File:** `tests/test_actions_signing.py` (Sprint 50)
- **Coverage:** Signature generation, HMAC computation, header format

### Receiver Verification
- **Constant-time comparison:** Required (`hmac.compare_digest`)
- **Raw body:** Must use exact bytes received (before JSON parsing)
- **Examples provided:** Node.js, Python (Flask/FastAPI)

**Status:** ✅ Webhook signing enforced with comprehensive docs

---

## Security Gaps Identified

### 1. OPTIONS Response Verification
**Status:** Not tested in audit
**Risk:** Low
**Action:** Add smoke test to verify OPTIONS preflight responses

### 2. Rate Limit Headers on Non-200 Responses
**Status:** Headers may not be present on 401/403
**Risk:** Low
**Action:** Verify headers are added to all authenticated responses

### 3. Webhook Signing Test Coverage
**Status:** Unit tests exist, but no end-to-end test
**Risk:** Medium
**Action:** Add E2E test with actual webhook receiver

---

## Recommendations

1. **P2:** Add OPTIONS smoke test to CI/CD pipeline
2. **P3:** Verify rate limit headers on error responses
3. **P1:** Add E2E webhook signing test with real receiver
4. **P2:** Document CORS error debugging (Studio connection issues)
5. **P3:** Consider adding CORS origin wildcard for preview deploys

---

Generated: 2025-10-07
