# Sprint 54 Phase C: Test Matrix

**Sprint:** 54 (Phase C)
**Date:** October 8, 2025
**Status:** Test Plan
**Target Coverage:** >90% for new code

---

## Test Strategy Overview

### Test Pyramid

```
              /\
             /  \     E2E Smoke (5 tests)
            /____\
           /      \
          / Integ. \  Integration (15 tests, quarantined)
         /__________\
        /            \
       /     Unit     \ Unit Tests (80+ tests)
      /________________\
```

### Quarantine Policy

**Integration tests** (marked `@pytest.mark.integration`) are **skipped by default** and only run when:
- All required environment variables are set
- Manual execution with `-m integration` flag
- OR `RELAY_RUN_ALL=1` environment variable

**E2E tests** run in CI/CD but use mocked Gmail API responses (no live calls).

---

## Unit Tests

### Module 1: MIME Builder (`test_mime_builder.py`)

**Target:** `src/actions/adapters/google_mime.py`
**Test Count:** 25 tests

| Test ID | Test Name | Scenario | Expected Outcome |
|---------|-----------|----------|------------------|
| U-M-01 | `test_build_text_only_email` | Build plain text email | Valid MIME with `text/plain` |
| U-M-02 | `test_build_html_only_email` | Build HTML-only email | Valid MIME with `text/html` |
| U-M-03 | `test_build_multipart_alternative` | Build text + HTML email | Valid MIME with `multipart/alternative` |
| U-M-04 | `test_build_email_with_single_attachment` | Add 1 regular attachment | Valid MIME with `multipart/mixed` |
| U-M-05 | `test_build_email_with_multiple_attachments` | Add 10 attachments | Valid MIME with 10 attachments |
| U-M-06 | `test_build_email_with_inline_image` | Add inline image with CID | Valid MIME with `multipart/related` |
| U-M-07 | `test_build_email_with_multiple_inline_images` | Add 5 inline images | Valid MIME with 5 CID references |
| U-M-08 | `test_build_full_email_html_inline_attachments` | All features combined | Valid MIME with all parts |
| U-M-09 | `test_cid_reference_format` | CID in HTML vs MIME | `<img src="cid:img1">` → `Content-ID: <img1>` |
| U-M-10 | `test_base64url_encoding_no_padding` | Verify no `=` padding | Base64URL string has no trailing `=` |
| U-M-11 | `test_unicode_subject` | Subject with emoji | RFC 2047 encoded subject |
| U-M-12 | `test_unicode_body` | Body with non-ASCII chars | UTF-8 encoded body |
| U-M-13 | `test_unicode_filename` | Filename with non-ASCII | RFC 2231 encoded filename |
| U-M-14 | `test_long_subject_line` | Subject > 998 chars | Truncated or wrapped |
| U-M-15 | `test_empty_body` | Empty text/html | Valid MIME with empty body |
| U-M-16 | `test_cc_bcc_recipients` | CC and BCC headers | Headers present in MIME |
| U-M-17 | `test_boundary_generation_uniqueness` | Generate 100 boundaries | All unique |
| U-M-18 | `test_boundary_no_collision_with_content` | Content contains `---` | Boundary still unique |
| U-M-19 | `test_mime_build_time_small_payload` | 10KB email | Build time < 10ms |
| U-M-20 | `test_mime_build_time_large_payload` | 2MB email | Build time < 50ms |
| U-M-21 | `test_memory_usage_large_attachments` | 10x 2MB attachments | Memory < 100MB |
| U-M-22 | `test_mime_structure_correct_hierarchy` | Nested multipart | Correct nesting |
| U-M-23 | `test_content_disposition_inline_vs_attachment` | Inline vs attachment | Correct `Content-Disposition` |
| U-M-24 | `test_content_transfer_encoding` | Binary attachment | `Content-Transfer-Encoding: base64` |
| U-M-25 | `test_mime_version_header` | MIME-Version presence | `MIME-Version: 1.0` |

---

### Module 2: HTML Sanitization (`test_html_sanitizer.py`)

**Target:** `src/actions/validation/html_sanitizer.py`
**Test Count:** 20 tests

| Test ID | Test Name | Scenario | Expected Outcome |
|---------|-----------|----------|------------------|
| U-H-01 | `test_allow_safe_tags` | HTML with `<p>`, `<div>`, `<a>` | All tags preserved |
| U-H-02 | `test_strip_script_tags` | HTML with `<script>alert('XSS')</script>` | Script stripped |
| U-H-03 | `test_strip_iframe_tags` | HTML with `<iframe src="...">` | Iframe stripped |
| U-H-04 | `test_strip_onclick_attribute` | HTML with `onclick="alert()"` | Attribute removed |
| U-H-05 | `test_strip_onerror_attribute` | `<img src="x" onerror="...">` | Attribute removed |
| U-H-06 | `test_allow_img_src_http_https` | `<img src="https://...">` | Allowed |
| U-H-07 | `test_allow_img_src_cid` | `<img src="cid:image1">` | Allowed |
| U-H-08 | `test_strip_img_src_javascript` | `<img src="javascript:...">` | `src` removed |
| U-H-09 | `test_strip_img_src_data_uri` | `<img src="data:image/png;base64,...">` | `src` removed (unless CID) |
| U-H-10 | `test_allow_a_href_http_https` | `<a href="https://...">` | Allowed |
| U-H-11 | `test_allow_a_href_mailto` | `<a href="mailto:...">` | Allowed |
| U-H-12 | `test_strip_a_href_javascript` | `<a href="javascript:...">` | `href` removed |
| U-H-13 | `test_allow_inline_styles_safe` | `style="color: red;"` | Allowed |
| U-H-14 | `test_strip_inline_styles_unsafe` | `style="position: fixed;"` | Property removed |
| U-H-15 | `test_strip_css_expression` | `style="width: expression(...);"` | Style removed |
| U-H-16 | `test_strip_form_tags` | HTML with `<form>`, `<input>` | Tags stripped |
| U-H-17 | `test_strip_link_tags` | HTML with `<link rel="stylesheet">` | Tag stripped |
| U-H-18 | `test_strip_meta_tags` | HTML with `<meta http-equiv="refresh">` | Tag stripped |
| U-H-19 | `test_nested_dangerous_tags` | `<div><script>...</script></div>` | Script stripped |
| U-H-20 | `test_html_sanitization_performance` | 1MB HTML | Sanitize in < 100ms |

---

### Module 3: Attachment Validation (`test_attachment_validator.py`)

**Target:** `src/actions/validation/attachments.py`
**Test Count:** 15 tests

| Test ID | Test Name | Scenario | Expected Outcome |
|---------|-----------|----------|------------------|
| U-A-01 | `test_validate_attachment_size_within_limit` | 10MB attachment | Passes validation |
| U-A-02 | `test_validate_attachment_size_exceeds_limit` | 30MB attachment | Raises `validation_error_attachment_too_large` |
| U-A-03 | `test_validate_attachment_count_within_limit` | 10 attachments | Passes validation |
| U-A-04 | `test_validate_attachment_count_exceeds_limit` | 15 attachments | Raises `validation_error_attachment_count_exceeded` |
| U-A-05 | `test_validate_allowed_mime_type_pdf` | `application/pdf` | Allowed |
| U-A-06 | `test_validate_allowed_mime_type_image` | `image/png` | Allowed |
| U-A-07 | `test_validate_blocked_mime_type_exe` | `application/x-msdownload` | Raises `validation_error_blocked_mime_type` |
| U-A-08 | `test_validate_blocked_mime_type_zip` | `application/zip` | Raises `validation_error_blocked_mime_type` |
| U-A-09 | `test_validate_filename_no_path_traversal` | `../../etc/passwd` | Raises `validation_error_invalid_filename` |
| U-A-10 | `test_validate_filename_safe` | `invoice-2025-10.pdf` | Passes validation |
| U-A-11 | `test_validate_total_size_within_limit` | 10x 2MB attachments | Passes validation |
| U-A-12 | `test_validate_total_size_exceeds_limit` | 10x 6MB attachments | Raises `validation_error_total_size_exceeded` |
| U-A-13 | `test_validate_inline_image_size_within_limit` | 3MB inline image | Passes validation |
| U-A-14 | `test_validate_inline_image_size_exceeds_limit` | 7MB inline image | Raises `validation_error_inline_too_large` |
| U-A-15 | `test_validate_inline_count_exceeds_limit` | 25 inline images | Raises `validation_error_inline_count_exceeded` |

---

### Module 4: Gmail Adapter Extensions (`test_gmail_adapter_rich.py`)

**Target:** `src/actions/adapters/google.py` (extended)
**Test Count:** 20 tests

| Test ID | Test Name | Scenario | Expected Outcome |
|---------|-----------|----------|------------------|
| U-G-01 | `test_preview_html_email` | Preview with `html` param | Returns preview with HTML summary |
| U-G-02 | `test_preview_email_with_attachments` | Preview with `attachments[]` | Returns preview with attachment list |
| U-G-03 | `test_preview_email_with_inline_images` | Preview with `inline[]` | Returns preview with inline image refs |
| U-G-04 | `test_preview_feature_flag_disabled` | `RICH_EMAIL_ENABLED=false` | Returns warning in preview |
| U-G-05 | `test_execute_html_email_feature_enabled` | `RICH_EMAIL_ENABLED=true` | Sends HTML email via Gmail API |
| U-G-06 | `test_execute_html_email_feature_disabled` | `RICH_EMAIL_ENABLED=false` | Raises `feature_disabled_rich_email` |
| U-G-07 | `test_execute_with_attachments` | Execute with attachments | Gmail API call includes attachments |
| U-G-08 | `test_execute_with_inline_images` | Execute with inline images | Gmail API call includes CID refs |
| U-G-09 | `test_execute_caches_attachments_in_preview` | Preview → Execute | Attachments retrieved from cache |
| U-G-10 | `test_execute_cache_miss_attachments` | Execute without preview | Raises error |
| U-G-11 | `test_execute_cid_reference_validation` | HTML refs CID not provided | Raises `validation_error_missing_inline_image` |
| U-G-12 | `test_execute_inline_not_referenced_in_html` | Inline provided but not used | Raises `validation_error_cid_not_referenced` |
| U-G-13 | `test_metrics_mime_build_time` | Execute with attachments | Records `gmail_mime_build_seconds` |
| U-G-14 | `test_metrics_attachment_bytes` | Execute with 2MB attachment | Records `gmail_attachment_bytes_total` |
| U-G-15 | `test_metrics_inline_refs_count` | Execute with 3 inline images | Records `gmail_inline_refs_total{count=3}` |
| U-G-16 | `test_audit_log_no_raw_html` | Execute HTML email | Audit log contains SHA256, not raw HTML |
| U-G-17 | `test_audit_log_no_raw_attachments` | Execute with attachments | Audit log contains SHA256, not raw bytes |
| U-G-18 | `test_gmail_api_error_mapping_413` | Gmail returns 413 | Raises `gmail_payload_too_large` |
| U-G-19 | `test_gmail_api_error_mapping_quota` | Gmail returns quota exceeded | Raises `gmail_quota_exceeded` |
| U-G-20 | `test_html_sanitization_in_adapter` | Execute with `<script>` | HTML sanitized before sending |

---

## Integration Tests

### Module 5: OAuth + Rich Email Send (`test_gmail_send_rich_integration.py`)

**Target:** Full flow (OAuth → Send)
**Test Count:** 10 tests
**Marker:** `@pytest.mark.integration`

| Test ID | Test Name | Scenario | Expected Outcome |
|---------|-----------|----------|------------------|
| I-R-01 | `test_oauth_send_html_email` | OAuth → Send HTML email | Email sent successfully |
| I-R-02 | `test_oauth_send_email_with_attachment` | OAuth → Send with attachment | Email sent, attachment received |
| I-R-03 | `test_oauth_send_email_with_inline_image` | OAuth → Send with inline image | Email sent, image renders inline |
| I-R-04 | `test_oauth_send_full_email` | OAuth → Send HTML + inline + attachments | All features work together |
| I-R-05 | `test_oauth_token_refresh_during_send` | Token expires mid-send | Auto-refreshes, send succeeds |
| I-R-06 | `test_gmail_4xx_error_handling` | Gmail returns 400 | Error mapped correctly |
| I-R-07 | `test_gmail_5xx_error_handling` | Gmail returns 503 | Error mapped correctly |
| I-R-08 | `test_gmail_rate_limit_handling` | Gmail returns 429 | Retry-After header returned |
| I-R-09 | `test_large_attachment_send` | Send 20MB attachment | Succeeds within timeout |
| I-R-10 | `test_multiple_inline_images_send` | Send 10 inline images | All images render correctly |

**Skip Gate:**
```python
@pytest.fixture(scope="module")
def skip_if_rich_email_envs_missing():
    required_envs = [
        "PROVIDER_GOOGLE_ENABLED",
        "PROVIDER_GOOGLE_RICH_EMAIL_ENABLED",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "OAUTH_ENCRYPTION_KEY",
        "RELAY_PUBLIC_BASE_URL",
        "GMAIL_TEST_TO"
    ]
    # Skip if any missing
```

---

## Negative Tests (Error Paths)

### Module 6: Negative Scenarios (`test_gmail_rich_negative.py`)

**Target:** Error handling
**Test Count:** 10 tests

| Test ID | Test Name | Scenario | Expected Outcome |
|---------|-----------|----------|------------------|
| N-01 | `test_attachment_too_large` | 30MB attachment | Raises `validation_error_attachment_too_large` |
| N-02 | `test_too_many_attachments` | 15 attachments | Raises `validation_error_attachment_count_exceeded` |
| N-03 | `test_blocked_mime_type_exe` | Attach `.exe` file | Raises `validation_error_blocked_mime_type` |
| N-04 | `test_html_body_too_large` | 7MB HTML body | Raises `validation_error_html_too_large` |
| N-05 | `test_total_payload_too_large` | 60MB total | Raises `validation_error_total_size_exceeded` |
| N-06 | `test_inline_cid_not_referenced` | Inline image not used in HTML | Raises `validation_error_cid_not_referenced` |
| N-07 | `test_html_references_missing_cid` | HTML refs `cid:img1`, not provided | Raises `validation_error_missing_inline_image` |
| N-08 | `test_invalid_base64_attachment` | Malformed base64 data | Raises `validation_error_invalid_base64` |
| N-09 | `test_filename_path_traversal` | `../../etc/passwd` | Raises `validation_error_invalid_filename` |
| N-10 | `test_feature_flag_off_with_html` | `RICH_EMAIL_ENABLED=false` + HTML | Raises `feature_disabled_rich_email` |

---

## Performance Tests

### Module 7: Performance & Load (`test_gmail_performance.py`)

**Target:** Performance under load
**Test Count:** 5 tests

| Test ID | Test Name | Scenario | Target | Assertion |
|---------|-----------|----------|--------|-----------|
| P-01 | `test_mime_build_time_small_payload` | 10KB email | <10ms | p99 < 10ms |
| P-02 | `test_mime_build_time_large_payload` | 2MB email | <50ms | p99 < 50ms |
| P-03 | `test_send_latency_text_only` | Send text email | <500ms | p95 < 500ms |
| P-04 | `test_send_latency_html_with_attachments` | Send HTML + 2MB attachment | <2s | p99 < 2s |
| P-05 | `test_concurrent_sends` | 100 concurrent sends | <5s | All succeed, p99 < 5s |

**Load Test Environment:**
- 100 concurrent requests
- Each request: HTML + 2MB attachment
- Total: 200MB load
- Expected: All succeed, no memory exhaustion

---

## E2E Smoke Tests

### Module 8: End-to-End Smoke (`test_gmail_e2e_smoke.py`)

**Target:** Full flow (Studio → Backend → Gmail)
**Test Count:** 5 tests
**Environment:** CI/CD (mocked Gmail API)

| Test ID | Test Name | Scenario | Expected Outcome |
|---------|-----------|----------|------------------|
| E2E-01 | `test_smoke_connect_google` | OAuth flow from Studio | Tokens stored, status=connected |
| E2E-02 | `test_smoke_send_text_email` | Send plain text email | Email sent, status=200 |
| E2E-03 | `test_smoke_send_html_email` | Send HTML email | Email sent, HTML preserved |
| E2E-04 | `test_smoke_send_with_attachment` | Send with 1 attachment | Email sent, attachment included |
| E2E-05 | `test_smoke_disconnect_google` | Disconnect OAuth | Tokens deleted, status=disconnected |

**Mocking Strategy:**
- Mock Gmail API responses (200 OK, message_id)
- Mock OAuth token exchange (return fake tokens)
- Use in-memory Redis (fakeredis)
- Use SQLite database (ephemeral)

---

## Test Data & Fixtures

### Fixture 1: Sample HTML Email

```python
@pytest.fixture
def sample_html_email():
    return {
        "to": "test@example.com",
        "subject": "Test HTML Email",
        "text": "Plain text fallback",
        "html": "<p>This is a <strong>test</strong> email.</p>"
    }
```

### Fixture 2: Sample Attachment (PDF)

```python
@pytest.fixture
def sample_pdf_attachment():
    # Generate 1MB dummy PDF
    pdf_bytes = b"%PDF-1.4\n..." + b"0" * (1024 * 1024)
    return {
        "filename": "test.pdf",
        "content_type": "application/pdf",
        "data": base64.b64encode(pdf_bytes).decode()
    }
```

### Fixture 3: Sample Inline Image (PNG)

```python
@pytest.fixture
def sample_inline_image():
    # Generate 100KB dummy PNG
    png_bytes = b"\x89PNG\r\n..." + b"0" * (100 * 1024)
    return {
        "cid": "image1",
        "filename": "logo.png",
        "content_type": "image/png",
        "data": base64.b64encode(png_bytes).decode()
    }
```

---

## Test Execution Commands

### Run All Unit Tests

```bash
pytest tests/actions/test_mime_builder.py -v
pytest tests/actions/test_html_sanitizer.py -v
pytest tests/actions/test_attachment_validator.py -v
pytest tests/actions/test_gmail_adapter_rich.py -v
pytest tests/actions/test_gmail_rich_negative.py -v
pytest tests/actions/test_gmail_performance.py -v
```

**Expected:** All unit tests pass (80+ tests)

### Run Integration Tests (Quarantined)

```bash
# Set required envs first
export PROVIDER_GOOGLE_ENABLED=true
export PROVIDER_GOOGLE_RICH_EMAIL_ENABLED=true
export GOOGLE_CLIENT_ID=<client-id>
export GOOGLE_CLIENT_SECRET=<secret>
export OAUTH_ENCRYPTION_KEY=<fernet-key>
export RELAY_PUBLIC_BASE_URL=http://localhost:8000
export GMAIL_TEST_TO=test@example.com

# Run integration tests
pytest -v -m integration tests/integration/test_gmail_send_rich_integration.py
```

**Expected:** 10 integration tests pass (requires live Gmail API)

### Run E2E Smoke Tests

```bash
pytest tests/e2e/test_gmail_e2e_smoke.py -v
```

**Expected:** 5 smoke tests pass (mocked Gmail API)

---

## Coverage Targets

| Module | Target Coverage | Current Coverage |
|--------|-----------------|------------------|
| `google_mime.py` | >95% | TBD |
| `html_sanitizer.py` | >95% | TBD |
| `attachments.py` | >90% | TBD |
| `google.py` (adapter) | >90% | 92% (baseline from Sprint 53) |
| **Overall Sprint 54** | >90% | TBD |

**Coverage Command:**
```bash
pytest --cov=src/actions --cov=src/validation --cov-report=term-missing tests/
```

---

## CI/CD Integration

### GitHub Actions Workflow

```yaml
- name: Run Unit Tests
  run: |
    pytest -v -m "not integration" tests/

- name: Run E2E Smoke Tests
  run: |
    pytest -v tests/e2e/test_gmail_e2e_smoke.py

- name: Check Coverage
  run: |
    pytest --cov=src --cov-report=xml --cov-fail-under=90 tests/
```

**Integration tests** are **not run in CI** (quarantined, require live credentials).

---

## Test Maintenance

### When to Update Tests

1. **API schema changes:** Update unit tests for `gmail_adapter_rich.py`
2. **HTML sanitization rules change:** Update `test_html_sanitizer.py`
3. **Attachment limits change:** Update `test_attachment_validator.py`
4. **New MIME features:** Add tests to `test_mime_builder.py`

### Test Review Checklist

- [ ] All tests have clear, descriptive names
- [ ] All tests are deterministic (no flakiness)
- [ ] All tests clean up after themselves (no side effects)
- [ ] Integration tests properly quarantined
- [ ] Performance tests have realistic targets
- [ ] Coverage > 90% for all new code

---

**Sprint 54 Test Matrix Complete**
**Total Tests:** 105+ (80 unit, 10 integration, 10 negative, 5 E2E)
