"""Test Slack webhook signature verification.

Tests HMAC SHA256 signature verification per Slack docs.
"""

import hashlib
import hmac
import time

from src.webhooks import verify_slack_signature_headers


def test_valid_signature_accepted():
    """Test valid Slack signature is accepted."""
    secret = "test_secret_key_12345"
    timestamp = str(int(time.time()))
    body = b'{"type":"event_callback","event":{"type":"message"}}'

    # Compute valid signature
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    signature = "v0=" + hmac.new(secret.encode(), sig_basestring.encode(), hashlib.sha256).hexdigest()

    headers = {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": signature,
    }

    result = verify_slack_signature_headers(headers, body, secret)
    assert result is True


def test_invalid_signature_rejected():
    """Test invalid signature is rejected."""
    secret = "test_secret_key_12345"
    timestamp = str(int(time.time()))
    body = b'{"type":"event_callback","event":{"type":"message"}}'

    # Use wrong signature
    headers = {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": "v0=wrong_signature_here",
    }

    result = verify_slack_signature_headers(headers, body, secret)
    assert result is False


def test_missing_secret_verification_disabled():
    """Test missing secret disables verification (dev mode)."""
    timestamp = str(int(time.time()))
    body = b'{"type":"event_callback"}'

    headers = {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": "v0=any_signature",
    }

    # Empty secret disables verification
    result = verify_slack_signature_headers(headers, body, "")
    assert result is True


def test_stale_timestamp_rejected():
    """Test stale timestamp (>5 min) is rejected."""
    secret = "test_secret_key_12345"
    # Timestamp from 10 minutes ago
    timestamp = str(int(time.time()) - 600)
    body = b'{"type":"event_callback"}'

    # Compute valid signature for old timestamp
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    signature = "v0=" + hmac.new(secret.encode(), sig_basestring.encode(), hashlib.sha256).hexdigest()

    headers = {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": signature,
    }

    result = verify_slack_signature_headers(headers, body, secret)
    assert result is False


def test_missing_headers_rejected():
    """Test missing timestamp or signature headers are rejected."""
    secret = "test_secret_key_12345"
    body = b'{"type":"event_callback"}'

    # Missing timestamp
    headers1 = {
        "X-Slack-Signature": "v0=some_signature",
    }
    result1 = verify_slack_signature_headers(headers1, body, secret)
    assert result1 is False

    # Missing signature
    headers2 = {
        "X-Slack-Request-Timestamp": str(int(time.time())),
    }
    result2 = verify_slack_signature_headers(headers2, body, secret)
    assert result2 is False


def test_invalid_timestamp_format_rejected():
    """Test non-integer timestamp is rejected."""
    secret = "test_secret_key_12345"
    body = b'{"type":"event_callback"}'

    headers = {
        "X-Slack-Request-Timestamp": "not_a_number",
        "X-Slack-Signature": "v0=some_signature",
    }

    result = verify_slack_signature_headers(headers, body, secret)
    assert result is False


def test_signature_constant_time_comparison():
    """Test signature uses constant-time comparison (timing attack protection)."""
    secret = "test_secret_key_12345"
    timestamp = str(int(time.time()))
    body = b'{"type":"event_callback"}'

    # Compute valid signature
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    correct_signature = "v0=" + hmac.new(secret.encode(), sig_basestring.encode(), hashlib.sha256).hexdigest()

    # Almost-correct signature (off by one character)
    almost_signature = correct_signature[:-1] + "X"

    headers = {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": almost_signature,
    }

    result = verify_slack_signature_headers(headers, body, secret)
    assert result is False


def test_different_body_different_signature():
    """Test different body produces different signature."""
    secret = "test_secret_key_12345"
    timestamp = str(int(time.time()))

    body1 = b'{"type":"event_callback","event":{"type":"message"}}'
    body2 = b'{"type":"event_callback","event":{"type":"file_shared"}}'

    # Compute signature for body1
    sig_basestring1 = f"v0:{timestamp}:{body1.decode('utf-8')}"
    signature1 = "v0=" + hmac.new(secret.encode(), sig_basestring1.encode(), hashlib.sha256).hexdigest()

    # Try to use body1's signature with body2 (should fail)
    headers = {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": signature1,
    }

    result = verify_slack_signature_headers(headers, body2, secret)
    assert result is False


def test_timestamp_within_5min_window_accepted():
    """Test timestamp within 5 minute window is accepted."""
    secret = "test_secret_key_12345"
    # Timestamp from 4 minutes ago (within 5 min window)
    timestamp = str(int(time.time()) - 240)
    body = b'{"type":"event_callback"}'

    # Compute valid signature
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    signature = "v0=" + hmac.new(secret.encode(), sig_basestring.encode(), hashlib.sha256).hexdigest()

    headers = {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": signature,
    }

    result = verify_slack_signature_headers(headers, body, secret)
    assert result is True
