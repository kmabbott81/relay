"""Tests for PII scrubbing in error messages - Sprint 58 Slice 6.

Verifies that _safe_error_str() properly redacts credentials, tokens,
and other sensitive patterns before storing in job records.
"""


from src.ai.orchestrator import _safe_error_str


class TestPIIScrubbing:
    """Tests for PII scrubbing helper."""

    def test_scrub_api_key_patterns(self):
        """Redact api_key, apiKey, API-KEY patterns."""
        error = Exception("Failed: api_key=sk-1234567890abcdef")
        result = _safe_error_str(error)
        assert "sk-1234567890abcdef" not in result
        assert "***" in result

    def test_scrub_bearer_token(self):
        """Redact Bearer token patterns."""
        error = Exception("Auth failed: Authorization: Bearer eyJhbGc...")
        result = _safe_error_str(error)
        assert "Bearer" not in result or "eyJhbGc" not in result

    def test_scrub_jwt_token(self):
        """Redact JWT-like token patterns."""
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        error = Exception(f"Invalid token: {jwt}")
        result = _safe_error_str(error)
        assert jwt not in result
        assert "***" in result

    def test_scrub_aws_key(self):
        """Redact AWS-like access key patterns."""
        error = Exception("AWS error: AKIAIOSFODNN7EXAMPLE")
        result = _safe_error_str(error)
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "***" in result

    def test_scrub_password_patterns(self):
        """Redact password patterns."""
        error = Exception("Connection failed: password=MyP@ssw0rd123")
        result = _safe_error_str(error)
        assert "MyP@ssw0rd123" not in result
        assert "***" in result

    def test_scrub_secret_key(self):
        """Redact secret_key patterns."""
        error = Exception("Config error: secret_key=abcdef0123456789")
        result = _safe_error_str(error)
        assert "abcdef0123456789" not in result
        assert "***" in result

    def test_case_insensitive_scrubbing(self):
        """Scrubbing should be case-insensitive."""
        error = Exception("Error: API_KEY=secret123 and ApiKey=secret456")
        result = _safe_error_str(error)
        assert "secret123" not in result
        assert "secret456" not in result

    def test_length_cap(self):
        """Long error messages should be capped at max_len."""
        long_error = "x" * 1000
        result = _safe_error_str(Exception(long_error), max_len=500)
        assert len(result) == 500

    def test_uuid_in_credentials(self):
        """Redact UUID patterns in credential context."""
        uuid = "550e8400-e29b-41d4-a716-446655440000"
        error = Exception(f"Failed: token={uuid}")
        result = _safe_error_str(error)
        assert uuid not in result
        assert "***" in result

    def test_legitimate_error_preserved(self):
        """Non-sensitive error messages should be mostly preserved."""
        error = Exception("Connection timeout after 30 seconds")
        result = _safe_error_str(error)
        assert "Connection timeout" in result
        assert "30 seconds" in result

    def test_multiple_secrets_in_one_error(self):
        """Multiple secrets should all be redacted."""
        error = Exception(
            "Multiple failures: api_key=key123 AND Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiI5MjM0In0.token AND secret_key=sec789"
        )
        result = _safe_error_str(error)
        assert "key123" not in result
        assert "sec789" not in result
        # Bearer + JWT should be redacted
        assert "Bearer" not in result or "eyJ" not in result
        assert result.count("***") >= 2

    def test_base64_like_secrets(self):
        """Redact long base64-like strings in credential context."""
        b64_secret = "A" * 50  # Long base64-like string
        error = Exception(f"Failed: secret={b64_secret}")
        result = _safe_error_str(error)
        assert b64_secret not in result
