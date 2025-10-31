# R2 Phase 2 - Fix Implementation Checklist

**Target:** 6-8 development hours
**Blocking:** All 5 gate criteria must pass
**Status:** Awaiting implementation

---

## Task 1: Implement Missing Metrics Methods (2-3 hours)

Location: `/src/memory/metrics.py`

### Subtask 1a: Add record_api_error Method
- [ ] Add method signature: `def record_api_error(self, error_type: str, user_id: Optional[str] = None) -> None`
- [ ] Create MemoryMetricEvent with metric_name "api_errors_total"
- [ ] Set labels: error_type, user_id (truncated)
- [ ] Append to _metric_buffer with lock
- [ ] Verify: Callable as `metrics.record_api_error("missing_jwt")`
- [ ] Used in api.py at lines: 58, 67, 132, 295, 378, 432, 491

### Subtask 1b: Add record_file_upload Method
- [ ] Add method signature: `def record_file_upload(self, status: str, source: str, mime_type: Optional[str] = None)`
- [ ] Create metric with name "knowledge_file_upload_total"
- [ ] Set labels: status, source, mime_type
- [ ] Append to buffer
- [ ] Verify: Callable as `metrics.record_file_upload("success", source, file.content_type)`
- [ ] Used in api.py at line: 200

### Subtask 1c: Add record_file_upload_error Method
- [ ] Add method: `def record_file_upload_error(self, error_type: str)`
- [ ] Create metric with name "knowledge_file_upload_errors_total"
- [ ] Set labels: error_type
- [ ] Append to buffer
- [ ] Verify: Callable as `metrics.record_file_upload_error("file_too_large")`
- [ ] Used in api.py at lines: 154, 175, 213

### Subtask 1d: Add record_embedding_operation Method
- [ ] Add method: `def record_embedding_operation(self, model: str, status: str)`
- [ ] Create metric with name "knowledge_embedding_operations_total"
- [ ] Set labels: model, status
- [ ] Append to buffer
- [ ] Verify: Callable as `metrics.record_embedding_operation(body.embedding_model, "success")`
- [ ] Used in api.py at line: 279

### Subtask 1e: Add record_vector_search Method
- [ ] Add method: `def record_vector_search(self, status: str)`
- [ ] Create metric with name "knowledge_vector_search_total"
- [ ] Set labels: status
- [ ] Append to buffer
- [ ] Verify: Callable as `metrics.record_vector_search("success")`
- [ ] Used in api.py at line: 364

### Subtask 1f: Add record_file_list_operation Method
- [ ] Add method: `def record_file_list_operation(self, status: str)`
- [ ] Create metric with name "knowledge_file_list_total"
- [ ] Set labels: status
- [ ] Append to buffer
- [ ] Verify: Callable as `metrics.record_file_list_operation("success")`
- [ ] Used in api.py at line: 419

### Subtask 1g: Add record_file_deletion Method
- [ ] Add method: `def record_file_deletion(self, status: str)`
- [ ] Create metric with name "knowledge_file_deletion_total"
- [ ] Set labels: status
- [ ] Append to buffer
- [ ] Verify: Callable as `metrics.record_file_deletion("success")`
- [ ] Used in api.py at line: 481

### Subtask 1h: Add record_rls_violation Method
- [ ] Add method: `def record_rls_violation(self, operation: str)`
- [ ] Use record_security_event internally with RLS_POLICY_VIOLATION type
- [ ] Set details: operation
- [ ] Verify: Callable as `metrics.record_rls_violation("delete")`
- [ ] Used in api.py at line: 468 (currently commented)

### Verification
- [ ] Run: `python -m pytest tests/knowledge/test_knowledge_metrics.py -v`
- [ ] Verify no AttributeError exceptions
- [ ] Test each method callable from API

---

## Task 2: Implement Error Response Transformer (2-3 hours)

Location: Main FastAPI app file (probably `/src/main.py` or similar)

### Subtask 2a: Create Error Code to Suggestion Mapping
- [ ] Create dict mapping status_code → (error_code, suggestion)
- [ ] 401: ("INVALID_JWT", "Refresh your authentication token and try again")
- [ ] 400: ("INVALID_FILE_FORMAT", "Ensure file format is one of: PDF, DOCX, XLSX, TXT, MD, PNG, JPG, WEBP")
- [ ] 413: ("FILE_TOO_LARGE", "File exceeds 50MB limit. Compress or split into smaller pieces (max 50MB each)")
- [ ] 429: ("RATE_LIMIT_EXCEEDED", "Wait 60 seconds before retrying. Upgrade to Pro tier for higher limits")
- [ ] 403: ("RLS_VIOLATION", "You don't have permission to access this resource")
- [ ] 404: ("FILE_NOT_FOUND", "The requested resource doesn't exist or has been deleted")
- [ ] 500: ("INTERNAL_ERROR", "Unexpected error. Contact support with your request ID")
- [ ] 503: ("SERVICE_UNAVAILABLE", "Service temporarily unavailable. Try again in a few moments")

### Subtask 2b: Create Custom HTTPException Handler
- [ ] Import: `from fastapi import FastAPI, HTTPException, Request`
- [ ] Import: `from fastapi.responses import JSONResponse`
- [ ] Create handler: `@app.exception_handler(HTTPException)`
- [ ] Handler extracts: status_code, detail from exception
- [ ] Looks up: error_code, suggestion from mapping
- [ ] Gets: request_id from request.scope (or generates uuid)
- [ ] Creates: ErrorResponse with all 4 fields
- [ ] Returns: JSONResponse with status_code and ErrorResponse body
- [ ] Handler sanitizes detail using: sanitize_error_detail(detail)

### Subtask 2c: Verify Exception Handler
- [ ] Test 401 error returns full ErrorResponse with suggestion
- [ ] Test 429 error returns suggestion about rate limits
- [ ] Test 413 error returns suggestion about file size
- [ ] Test error_code field matches enum values
- [ ] Test request_id field is UUID
- [ ] Test suggestion field is populated

---

## Task 3: Add X-Request-ID Header to All Response Paths (1-2 hours)

Location: `/src/knowledge/api.py`

### Subtask 3a: Update upload_file Endpoint
- [ ] Line 199 (before return): Add `response.headers["X-Request-ID"] = str(request_id)`
- [ ] Line 214 (error path): Ensure header set before HTTPException raised
- [ ] Verify response includes header in all code paths

### Subtask 3b: Update index_file Endpoint
- [ ] Line 278 (before return): Add `response.headers["X-Request-ID"] = str(request_id)`
- [ ] Line 296 (error path): Ensure header set
- [ ] Verify: Header present in 200 and error responses

### Subtask 3c: Update search_knowledge Endpoint
- [ ] Line 326 (rate limit error): Add `response.headers["X-Request-ID"] = str(request_id)`
- [ ] Line 363 (success): Add `response.headers["X-Request-ID"] = str(request_id)`
- [ ] Line 379 (error): Ensure header set
- [ ] Verify: Header in all 3 code paths

### Subtask 3d: Update list_files Endpoint
- [ ] Line 418 (before return): Add `response.headers["X-Request-ID"] = str(request_id)`
- [ ] Line 433 (error): Ensure header set
- [ ] Verify: Header in success and error paths

### Subtask 3e: Update delete_file Endpoint
- [ ] Line 480 (before return): Add `response.headers["X-Request-ID"] = str(request_id)`
- [ ] Line 492 (error): Ensure header set
- [ ] Verify: Header in all code paths

### Subtask 3f: Verify Header Format
- [ ] All headers are UUID format (36 characters)
- [ ] Header name is exactly "X-Request-ID" (case-sensitive)
- [ ] Header value is string representation of UUID

---

## Task 4: Register RequestID Middleware (30 minutes)

Location: Main FastAPI app file

### Subtask 4a: Verify Middleware Function
- [ ] Check `/src/knowledge/api.py` lines 512-518
- [ ] Confirm function exists: `async def add_request_id_middleware(request: Request, call_next)`
- [ ] Confirm function sets: `request.scope["request_id"]`
- [ ] Confirm function sets: `response.headers["X-Request-ID"]`

### Subtask 4b: Import Middleware into Main App
- [ ] Add import: `from src.knowledge.api import add_request_id_middleware`
- [ ] Alternative: Copy function into main app directly

### Subtask 4c: Register Middleware on FastAPI App
Option 1 (via add_middleware):
- [ ] Add line: `app.add_middleware(add_request_id_middleware)`
- [ ] Ensure added BEFORE including routers

Option 2 (via decorator):
- [ ] Create middleware function in main app
- [ ] Use: `@app.middleware("http")`
- [ ] Decorator-style registration

### Subtask 4d: Verify Middleware Execution
- [ ] Test: middleware runs on every request
- [ ] Test: request.scope["request_id"] set
- [ ] Test: response.headers["X-Request-ID"] present in response

---

## Task 5: Apply Error Sanitization (1 hour)

Location: Error response transformer (Task 2)

### Subtask 5a: Call Sanitization in Exception Handler
- [ ] In exception handler, add: `safe_detail = sanitize_error_detail(exc.detail)`
- [ ] Use safe_detail in ErrorResponse: `detail=safe_detail`
- [ ] Don't use exc.detail directly

### Subtask 5b: Verify Sanitization Works
- [ ] Test: S3 URLs removed ("s3://" replaced with generic message)
- [ ] Test: File paths removed ("/var/", "/home/")
- [ ] Test: Stack traces removed ("stack", "traceback", ".py:")
- [ ] Test: Normal error messages pass through unchanged
- [ ] Test: Sensitive patterns case-insensitive

---

## Integration Testing (1-2 hours)

Location: `/tests/knowledge/test_knowledge_phase2_integration.py`

### Subtask A: Uncomment Test Fixtures
- [ ] Line 18-37: Uncomment mock_jwt_token, mock_user_principal, mock_user_hash
- [ ] Line 40-49: Uncomment sample files
- [ ] Verify fixtures execute without error

### Subtask B: Uncomment and Run Upload Tests
- [ ] Line 60-70: Uncomment test_upload_missing_jwt_returns_401
- [ ] Line 74-82: Uncomment test_upload_invalid_jwt_returns_401
- [ ] Line 85-103: Uncomment test_upload_valid_jwt_stores_with_rls
- [ ] Line 106-117: Uncomment test_upload_file_too_large_returns_413
- [ ] Line 120-131: Uncomment test_upload_invalid_mime_type_returns_400
- [ ] Line 134-146: Uncomment test_upload_response_includes_rate_limit_headers
- [ ] Line 149-160: Uncomment test_upload_includes_request_id_for_tracing
- [ ] Run: `pytest tests/knowledge/test_knowledge_phase2_integration.py::TestFileUploadSecurity -v`
- [ ] Verify: All 6 tests pass

### Subtask C: Test Error Response Format
- [ ] Create new test: test_error_response_includes_error_code
- [ ] Create new test: test_error_response_includes_suggestion
- [ ] Create new test: test_error_response_includes_request_id
- [ ] Create new test: test_error_messages_sanitized
- [ ] Verify: All new tests pass

### Subtask D: Test Rate Limit Headers
- [ ] Verify: All responses include X-RateLimit-Limit
- [ ] Verify: All responses include X-RateLimit-Remaining
- [ ] Verify: All responses include X-RateLimit-Reset

### Subtask E: Test Request ID Headers
- [ ] Verify: All responses include X-Request-ID
- [ ] Verify: X-Request-ID format is UUID
- [ ] Verify: Same request_id in body and header (where applicable)

### Subtask F: Test Metrics Calls
- [ ] Verify: No AttributeError on upload
- [ ] Verify: No AttributeError on search
- [ ] Verify: No AttributeError on delete
- [ ] Verify: Metrics events recorded to buffer

---

## Final Validation (Checklist)

### Before Requesting Gate Re-Validation:

- [ ] All 8 metrics methods implemented and tested
- [ ] Error response transformer implemented
- [ ] Error code → suggestion mapping complete (8+ codes)
- [ ] X-Request-ID header set on all 6 endpoints
- [ ] Middleware registered on FastAPI app
- [ ] Sanitization applied in exception handler
- [ ] 15 integration tests uncommented and passing
- [ ] No AttributeError at runtime
- [ ] All error paths tested
- [ ] Rate limit headers present on all responses
- [ ] Request ID headers present on all responses
- [ ] Error suggestions populated for common errors
- [ ] Request-id middleware executes
- [ ] Sensitive patterns sanitized
- [ ] Code review completed
- [ ] Performance impact assessed (< 1% overhead)

### Test Coverage:
- [ ] 44 existing R1 tests still pass (no regression)
- [ ] 15 new R2 tests added
- [ ] 5+ new integration tests for error handling
- [ ] Total: 64+ tests passing

### Approval Criteria Met:
- [ ] Criterion 1: X-RateLimit-* headers ✓
- [ ] Criterion 2: X-Request-ID header ✓
- [ ] Criterion 3: Error suggestion field ✓
- [ ] Criterion 4: User-facing sanitization ✓
- [ ] Criterion 5: Metrics recorded ✓

---

## Time Breakdown

| Task | Estimated | Actual | Status |
|------|-----------|--------|--------|
| 1. Metrics Methods | 2-3h | | |
| 2. Error Transformer | 2-3h | | |
| 3. X-Request-ID Headers | 1-2h | | |
| 4. Middleware Registration | 30m | | |
| 5. Error Sanitization | 1h | | |
| Testing & Validation | 1-2h | | |
| **TOTAL** | **8-11h** | | |

---

## Sign-Off

**Implementation Started:** [Date]
**Target Completion:** [Date]
**Assigned To:** [Developer]

**Checklist Status:** Ready for implementation
**Blocking Gate:** Yes - All items must complete before gate re-validation
**Next Step:** Begin with Task 1 (Metrics Methods)

---
