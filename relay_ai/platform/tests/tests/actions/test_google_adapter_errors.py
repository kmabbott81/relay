"""Unit tests for GoogleAdapter structured error handling.

Sprint 54 Phase C: Verify structured error payloads for validation failures.
"""

import base64
import json
import os

import pytest

from relay_ai.actions.adapters.google import GoogleAdapter


@pytest.fixture
def adapter():
    """Create adapter instance with test configuration."""
    # Set internal-only config for tests
    os.environ["GOOGLE_INTERNAL_ONLY"] = "true"
    os.environ["GOOGLE_INTERNAL_ALLOWED_DOMAINS"] = "example.com,test.example.com"
    os.environ["GOOGLE_INTERNAL_TEST_RECIPIENTS"] = "allowed-test@external.com"
    os.environ["PROVIDER_GOOGLE_ENABLED"] = "true"

    adapter = GoogleAdapter()
    return adapter


@pytest.fixture(autouse=True)
def cleanup_env():
    """Clean up environment after each test."""
    yield
    # Restore defaults
    os.environ.pop("GOOGLE_INTERNAL_ONLY", None)
    os.environ.pop("GOOGLE_INTERNAL_ALLOWED_DOMAINS", None)
    os.environ.pop("GOOGLE_INTERNAL_TEST_RECIPIENTS", None)


def test_oversized_attachment_returns_structured_error(adapter):
    """Test that oversized attachment (26MB) returns structured error.

    Expected error_code: validation_error_attachment_too_large
    Expected retriable: False
    """
    # Create 26MB attachment (exceeds 25MB limit)
    attachment_data = b"x" * (26 * 1024 * 1024)
    encoded_data = base64.b64encode(attachment_data).decode()

    params = {
        "to": "test@example.com",
        "subject": "Test",
        "text": "Body",
        "attachments": [
            {
                "filename": "huge.bin",
                "content_type": "application/octet-stream",
                "data": encoded_data,
            }
        ],
    }

    with pytest.raises(ValueError) as exc_info:
        adapter._preview_gmail_send(params)

    # Parse structured error
    error = json.loads(str(exc_info.value))

    # Verify structure
    assert error["error_code"] == "validation_error_attachment_too_large"
    assert "correlation_id" in error
    assert error["retriable"] is False
    assert error["source"] == "gmail.adapter"
    assert "message" in error
    assert "26" in error["message"].lower() or "too large" in error["message"].lower()

    # Verify additional fields
    assert "field" in error
    assert "details" in error
    assert "remediation" in error


def test_orphan_cid_returns_structured_error(adapter):
    """Test that orphan CID (HTML references non-existent inline image) returns error.

    Expected error_code: validation_error_missing_inline_image
    Expected retriable: False
    """
    # HTML references cid:logo but only cid:banner is provided
    params = {
        "to": "test@example.com",
        "subject": "Test",
        "text": "Body",
        "html": '<html><body><img src="cid:logo" /><img src="cid:banner" /></body></html>',
        "inline": [
            {
                "cid": "banner",
                "filename": "banner.png",
                "content_type": "image/png",
                "data": base64.b64encode(b"fake-png-data").decode(),
            }
        ],
    }

    with pytest.raises(ValueError) as exc_info:
        adapter._preview_gmail_send(params)

    error = json.loads(str(exc_info.value))

    assert error["error_code"] == "validation_error_missing_inline_image"
    assert "correlation_id" in error
    assert error["retriable"] is False
    assert error["source"] == "gmail.adapter"
    assert "logo" in error["message"].lower() or "cid" in error["message"].lower()


def test_disallowed_mime_returns_structured_error(adapter):
    """Test that disallowed MIME type (.exe) returns structured error.

    Expected error_code: validation_error_blocked_mime_type
    Expected retriable: False
    """
    params = {
        "to": "test@example.com",
        "subject": "Test",
        "text": "Body",
        "attachments": [
            {
                "filename": "malware.exe",
                "content_type": "application/x-msdownload",
                "data": base64.b64encode(b"MZ fake exe").decode(),
            }
        ],
    }

    with pytest.raises(ValueError) as exc_info:
        adapter._preview_gmail_send(params)

    error = json.loads(str(exc_info.value))

    assert error["error_code"] == "validation_error_blocked_mime_type"
    assert "correlation_id" in error
    assert error["retriable"] is False
    assert error["source"] == "gmail.adapter"
    assert "exe" in error["message"].lower() or "blocked" in error["message"].lower()


def test_internal_only_blocks_external_recipient(adapter):
    """Test that internal-only mode blocks external recipients.

    Expected error_code: internal_only_recipient_blocked
    Expected retriable: False
    """
    # Send to external domain (not in GOOGLE_INTERNAL_ALLOWED_DOMAINS)
    params = {
        "to": "external@notallowed.com",
        "subject": "Test",
        "text": "Body",
    }

    with pytest.raises(ValueError) as exc_info:
        adapter._preview_gmail_send(params)

    error = json.loads(str(exc_info.value))

    assert error["error_code"] == "internal_only_recipient_blocked"
    assert "correlation_id" in error
    assert error["retriable"] is False
    assert error["source"] == "gmail.adapter"
    assert "external@notallowed.com" in error["message"]

    # Verify details include allowed domains
    assert "details" in error
    assert "allowed_domains" in error["details"]
    assert "example.com" in error["details"]["allowed_domains"]


def test_internal_only_allows_test_recipient(adapter):
    """Test that internal-only mode allows test recipients (bypass)."""
    # Send to test recipient (in GOOGLE_INTERNAL_TEST_RECIPIENTS)
    params = {
        "to": "allowed-test@external.com",
        "subject": "Test",
        "text": "Body",
    }

    # Should NOT raise error
    result = adapter._preview_gmail_send(params)

    assert result["summary"]
    assert "allowed-test@external.com" in result["summary"]


def test_recipient_count_overflow_returns_structured_error(adapter):
    """Test that recipient count > 100 returns structured error.

    Expected error_code: validation_error (wrapped by Pydantic)
    Expected retriable: False
    """
    # Create 101 total recipients (1 to + 50 cc + 50 bcc)
    params = {
        "to": "test@example.com",
        "subject": "Test",
        "text": "Body",
        "cc": [f"cc{i}@example.com" for i in range(50)],
        "bcc": [f"bcc{i}@example.com" for i in range(50)],
    }

    with pytest.raises(ValueError) as exc_info:
        adapter._preview_gmail_send(params)

    error_msg = str(exc_info.value)

    # Should mention recipient limit
    assert "101" in error_msg or "100" in error_msg
    assert "limit" in error_msg.lower() or "exceed" in error_msg.lower()


def test_sanitization_preview_returns_sanitized_html(adapter):
    """Test that preview returns sanitized_html and sanitization_summary.

    Verify that dangerous HTML is sanitized and changes are tracked.
    """
    # HTML with dangerous content
    params = {
        "to": "test@example.com",
        "subject": "Test",
        "text": "Body",
        "html": """
        <html>
        <body>
            <p onclick="alert('xss')">Safe text</p>
            <script>alert('xss')</script>
            <img src="javascript:alert('xss')" />
        </body>
        </html>
        """,
    }

    result = adapter._preview_gmail_send(params)

    # Verify sanitization_summary exists and has changes
    assert "sanitization_summary" in result
    assert result["sanitization_summary"]["sanitized"] is True
    assert "changes" in result["sanitization_summary"]

    # Verify at least one change was recorded
    changes = result["sanitization_summary"]["changes"]
    total_changes = sum(changes.values())
    assert total_changes > 0, f"Expected sanitization changes, got: {changes}"

    # Verify sanitized_html is returned
    assert "sanitized_html" in result
    sanitized = result["sanitized_html"]

    # Verify dangerous content was removed
    assert "<script>" not in sanitized
    assert "javascript:" not in sanitized
    assert "onclick" not in sanitized.lower()


def test_structured_error_has_all_required_fields(adapter):
    """Test that structured errors have all required fields.

    Verify the error schema matches spec:
    - error_code (str)
    - message (str)
    - field (str or None)
    - details (dict)
    - remediation (str)
    - retriable (bool)
    - correlation_id (str, UUID format)
    - source (str)
    """
    # Trigger any validation error
    attachment_data = b"x" * (26 * 1024 * 1024)
    encoded_data = base64.b64encode(attachment_data).decode()

    params = {
        "to": "test@example.com",
        "subject": "Test",
        "text": "Body",
        "attachments": [
            {
                "filename": "huge.bin",
                "content_type": "application/octet-stream",
                "data": encoded_data,
            }
        ],
    }

    with pytest.raises(ValueError) as exc_info:
        adapter._preview_gmail_send(params)

    error = json.loads(str(exc_info.value))

    # Verify all required fields
    assert "error_code" in error
    assert isinstance(error["error_code"], str)
    assert error["error_code"].startswith("validation_error_")

    assert "message" in error
    assert isinstance(error["message"], str)
    assert len(error["message"]) > 0

    assert "field" in error
    # field can be None or str

    assert "details" in error
    assert isinstance(error["details"], dict)

    assert "remediation" in error
    assert isinstance(error["remediation"], str)

    assert "retriable" in error
    assert isinstance(error["retriable"], bool)

    assert "correlation_id" in error
    assert isinstance(error["correlation_id"], str)
    # Verify UUID format (8-4-4-4-12 hex characters)
    import re

    uuid_pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    assert uuid_pattern.match(error["correlation_id"]), f"Invalid UUID format: {error['correlation_id']}"

    assert "source" in error
    assert isinstance(error["source"], str)
    assert error["source"] == "gmail.adapter"


def test_invalid_attachment_base64_returns_structured_error(adapter):
    """Test that invalid base64 in attachment returns structured error.

    Expected error_code: validation_error_invalid_attachment_data
    Expected retriable: False
    Sprint 54: Compliance Fix #5
    """
    params = {
        "to": "test@example.com",
        "subject": "Test",
        "text": "Body",
        "attachments": [
            {
                "filename": "test.txt",
                "content_type": "text/plain",
                "data": "NOT_VALID_BASE64!!!",
            }
        ],
    }

    with pytest.raises(ValueError) as exc_info:
        adapter._preview_gmail_send(params)

    error = json.loads(str(exc_info.value))

    # Verify error structure
    assert error["error_code"] == "validation_error_invalid_attachment_data"
    assert "correlation_id" in error
    assert error["retriable"] is False
    assert error["source"] == "gmail.adapter"
    assert "decode" in error["message"].lower() or "attachment" in error["message"].lower()
    assert "field" in error
    assert error["field"] == "attachments"
    assert "remediation" in error
    assert "valid base64" in error["remediation"].lower()


def test_invalid_inline_base64_returns_structured_error(adapter):
    """Test that invalid base64 in inline image returns structured error.

    Expected error_code: validation_error_invalid_inline_data
    Expected retriable: False
    Sprint 54: Compliance Fix #5
    """
    params = {
        "to": "test@example.com",
        "subject": "Test",
        "text": "Body",
        "html": '<p>Logo: <img src="cid:logo"></p>',
        "inline": [
            {
                "cid": "logo",
                "filename": "logo.png",
                "content_type": "image/png",
                "data": "INVALID@BASE64#DATA",
            }
        ],
    }

    with pytest.raises(ValueError) as exc_info:
        adapter._preview_gmail_send(params)

    error = json.loads(str(exc_info.value))

    # Verify error structure
    assert error["error_code"] == "validation_error_invalid_inline_data"
    assert "correlation_id" in error
    assert error["retriable"] is False
    assert error["source"] == "gmail.adapter"
    assert "decode" in error["message"].lower() or "inline" in error["message"].lower()
    assert "field" in error
    assert error["field"] == "inline"
    assert "remediation" in error
    assert "valid base64" in error["remediation"].lower()
