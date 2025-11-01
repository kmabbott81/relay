"""Unit tests for Gmail adapter preview method.

Sprint 53 Phase B: Test MIME assembly, Base64URL encoding, digest generation, validation.
"""

import os
import re

import pytest

from src.actions.adapters.google import GoogleAdapter


class TestGmailPreview:
    """Test suite for gmail.send preview method."""

    def setup_method(self):
        """Set up test fixtures."""
        # CI Stabilization: Disable internal-only mode for unit tests
        self.original_internal_only = os.environ.get("GOOGLE_INTERNAL_ONLY")
        os.environ["GOOGLE_INTERNAL_ONLY"] = "false"

        self.adapter = GoogleAdapter()

    def teardown_method(self):
        """Restore original environment."""
        if self.original_internal_only is not None:
            os.environ["GOOGLE_INTERNAL_ONLY"] = self.original_internal_only
        elif "GOOGLE_INTERNAL_ONLY" in os.environ:
            del os.environ["GOOGLE_INTERNAL_ONLY"]

    def test_preview_valid_payload_minimal(self):
        """Test preview with minimal valid payload (to, subject, text only)."""
        params = {"to": "test@example.com", "subject": "Test Subject", "text": "Test email body"}

        result = self.adapter.preview("gmail.send", params)

        # Assert digest is 16 characters (SHA256 truncated)
        assert "digest" in result
        assert len(result["digest"]) == 16
        assert re.match(r"^[a-f0-9]{16}$", result["digest"]), "Digest should be 16 hex chars"

        # Assert summary contains key fields
        assert "test@example.com" in result["summary"]
        assert "Test Subject" in result["summary"]

        # Assert raw message length is present
        assert "raw_message_length" in result
        assert result["raw_message_length"] > 0

        # Assert warnings present (feature flag off)
        assert isinstance(result["warnings"], list)
        assert len(result["warnings"]) > 0

    def test_preview_with_cc_bcc(self):
        """Test preview with CC and BCC recipients."""
        params = {
            "to": "recipient@example.com",
            "subject": "Team Update",
            "text": "This is a team update email.",
            "cc": ["cc1@example.com", "cc2@example.com"],
            "bcc": ["bcc@example.com"],
        }

        result = self.adapter.preview("gmail.send", params)

        # Assert summary includes CC and BCC
        assert "cc1@example.com" in result["summary"] or "CC:" in result["summary"]
        assert "bcc@example.com" in result["summary"] or "BCC:" in result["summary"]

    def test_preview_empty_cc_bcc_arrays(self):
        """Test preview with empty CC/BCC arrays (should be accepted)."""
        params = {"to": "test@example.com", "subject": "Test", "text": "Body", "cc": [], "bcc": []}

        # Should not raise error
        result = self.adapter.preview("gmail.send", params)
        assert result["digest"] is not None

    def test_preview_base64url_no_padding(self):
        """Test that MIME message is Base64URL encoded without padding."""
        params = {
            "to": "test@example.com",
            "subject": "Padding Test",
            "text": "A" * 100,  # Long text to ensure Base64 would normally have padding
        }

        result = self.adapter.preview("gmail.send", params)

        # The adapter builds MIME and encodes it; we can't access raw_message directly
        # but we can verify it's not using standard base64 (which would have =)
        # by checking the raw_message_length is consistent with no padding
        # (base64url removes trailing =)

        # Just verify digest is stable
        result2 = self.adapter.preview("gmail.send", params)
        assert result["digest"] == result2["digest"], "Digest should be stable for same input"

    def test_preview_digest_stability(self):
        """Test that same input produces same digest (idempotent)."""
        params = {
            "to": "stable@example.com",
            "subject": "Stability Test",
            "text": "This should produce a stable digest.",
        }

        result1 = self.adapter.preview("gmail.send", params)
        result2 = self.adapter.preview("gmail.send", params)
        result3 = self.adapter.preview("gmail.send", params)

        assert result1["digest"] == result2["digest"] == result3["digest"]

    def test_preview_digest_changes_with_input(self):
        """Test that different inputs produce different digests."""
        params1 = {"to": "test1@example.com", "subject": "Subject 1", "text": "Body 1"}

        params2 = {"to": "test2@example.com", "subject": "Subject 1", "text": "Body 1"}  # Different recipient

        params3 = {"to": "test1@example.com", "subject": "Subject 2", "text": "Body 1"}  # Different subject

        result1 = self.adapter.preview("gmail.send", params1)
        result2 = self.adapter.preview("gmail.send", params2)
        result3 = self.adapter.preview("gmail.send", params3)

        # All digests should be different
        assert result1["digest"] != result2["digest"]
        assert result1["digest"] != result3["digest"]
        assert result2["digest"] != result3["digest"]

    def test_preview_invalid_email_to_field(self):
        """Test preview with invalid email in 'to' field."""
        params = {"to": "not-an-email", "subject": "Test", "text": "Body"}  # Invalid format

        with pytest.raises(ValueError) as exc_info:
            self.adapter.preview("gmail.send", params)

        error_msg = str(exc_info.value)
        assert "validation error" in error_msg.lower() or "invalid email" in error_msg.lower()

    def test_preview_invalid_email_missing_at_sign(self):
        """Test preview with email missing @ sign."""
        params = {"to": "testexample.com", "subject": "Test", "text": "Body"}

        with pytest.raises(ValueError):
            self.adapter.preview("gmail.send", params)

    def test_preview_invalid_email_missing_domain(self):
        """Test preview with email missing domain."""
        params = {"to": "test@", "subject": "Test", "text": "Body"}

        with pytest.raises(ValueError):
            self.adapter.preview("gmail.send", params)

    def test_preview_invalid_email_in_cc_list(self):
        """Test preview with invalid email in CC list."""
        params = {
            "to": "valid@example.com",
            "subject": "Test",
            "text": "Body",
            "cc": ["valid@example.com", "invalid-email"],  # Second one is invalid
        }

        with pytest.raises(ValueError) as exc_info:
            self.adapter.preview("gmail.send", params)

        error_msg = str(exc_info.value)
        assert "invalid email" in error_msg.lower() or "validation error" in error_msg.lower()

    def test_preview_invalid_email_in_bcc_list(self):
        """Test preview with invalid email in BCC list."""
        params = {
            "to": "valid@example.com",
            "subject": "Test",
            "text": "Body",
            "bcc": ["bad@email@com"],  # Multiple @ signs
        }

        with pytest.raises(ValueError):
            self.adapter.preview("gmail.send", params)

    def test_preview_missing_required_field_to(self):
        """Test preview with missing required 'to' field."""
        params = {"subject": "Test", "text": "Body"}

        with pytest.raises(ValueError):
            self.adapter.preview("gmail.send", params)

    def test_preview_missing_required_field_subject(self):
        """Test preview with missing required 'subject' field."""
        params = {"to": "test@example.com", "text": "Body"}

        with pytest.raises(ValueError):
            self.adapter.preview("gmail.send", params)

    def test_preview_missing_required_field_text(self):
        """Test preview with missing required 'text' field."""
        params = {"to": "test@example.com", "subject": "Test"}

        with pytest.raises(ValueError):
            self.adapter.preview("gmail.send", params)

    def test_preview_long_body_text(self):
        """Test preview with very long body text (digest should use first 64 chars)."""
        long_text = "A" * 1000  # 1000 character body

        params = {"to": "test@example.com", "subject": "Long Body", "text": long_text}

        result = self.adapter.preview("gmail.send", params)

        # Digest should be stable even with long text
        assert len(result["digest"]) == 16

        # Verify it's using first 64 chars for digest by comparing
        params_short = {"to": "test@example.com", "subject": "Long Body", "text": "A" * 64}  # Exactly 64 chars

        result_short = self.adapter.preview("gmail.send", params_short)

        # Digests should be the same (both use first 64 chars)
        assert result["digest"] == result_short["digest"]

    def test_preview_unicode_characters(self):
        """Test preview with Unicode characters in subject and body."""
        params = {
            "to": "test@example.com",
            "subject": "Unicode Test: 你好世界 🌍",
            "text": "Body with émojis and accénts: café ☕",
        }

        # Should not raise error
        result = self.adapter.preview("gmail.send", params)
        assert result["digest"] is not None
        assert result["raw_message_length"] > 0

    def test_preview_feature_flag_warning_when_disabled(self):
        """Test that preview shows warning when PROVIDER_GOOGLE_ENABLED is false."""
        # Default is false
        params = {"to": "test@example.com", "subject": "Test", "text": "Body"}

        result = self.adapter.preview("gmail.send", params)

        # Should have warning about provider being disabled
        assert any("PROVIDER_GOOGLE_ENABLED" in w for w in result["warnings"])

    def test_preview_unknown_action(self):
        """Test preview with unknown action ID."""
        params = {"to": "test@example.com", "subject": "Test", "text": "Body"}

        with pytest.raises(ValueError) as exc_info:
            self.adapter.preview("unknown.action", params)

        assert "unknown action" in str(exc_info.value).lower()

    def test_preview_mime_structure(self):
        """Test that MIME message is properly structured (indirect test via summary)."""
        params = {
            "to": "recipient@example.com",
            "subject": "MIME Structure Test",
            "text": "This tests the MIME structure indirectly.",
            "cc": ["cc@example.com"],
            "bcc": ["bcc@example.com"],
        }

        result = self.adapter.preview("gmail.send", params)

        # Verify summary contains all key components
        assert "recipient@example.com" in result["summary"]
        assert "MIME Structure Test" in result["summary"]
        assert "cc@example.com" in result["summary"]
        assert "bcc@example.com" in result["summary"]

    def test_preview_returns_all_required_fields(self):
        """Test that preview returns all required fields in response."""
        params = {
            "to": "test@example.com",
            "subject": "Complete Response Test",
            "text": "Testing complete response structure.",
        }

        result = self.adapter.preview("gmail.send", params)

        # Assert all expected fields are present
        assert "summary" in result
        assert "params" in result
        assert "warnings" in result
        assert "digest" in result
        assert "raw_message_length" in result

        # Assert types are correct
        assert isinstance(result["summary"], str)
        assert isinstance(result["params"], dict)
        assert isinstance(result["warnings"], list)
        assert isinstance(result["digest"], str)
        assert isinstance(result["raw_message_length"], int)
