"""Unit tests for Gmail MIME builder.

Sprint 54: Tests for src/actions/adapters/google_mime.py
"""

import base64
import re

import pytest

from src.actions.adapters.google_mime import MimeBuilder
from src.validation.attachments import Attachment, InlineImage


class TestMimeBuilderTextOnly:
    """Test text-only MIME messages."""

    def test_simple_text_message(self):
        """Test building simple text/plain message."""
        builder = MimeBuilder()
        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="Hello world!",
        )

        assert "To: alice@example.com" in result
        assert "Subject: Test" in result
        assert "MIME-Version: 1.0" in result
        assert 'Content-Type: text/plain; charset="utf-8"' in result
        assert "Hello world!" in result

    def test_text_with_cc_bcc(self):
        """Test text message with CC and BCC."""
        builder = MimeBuilder()
        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="Hello",
            cc=["bob@example.com"],
            bcc=["charlie@example.com"],
        )

        assert "Cc: bob@example.com" in result
        assert "Bcc: charlie@example.com" in result

    def test_unicode_subject(self):
        """Test Unicode characters in subject are encoded."""
        builder = MimeBuilder()
        result = builder.build_message(
            to="alice@example.com",
            subject="Hello 世界",
            text="Body",
        )

        # Should use RFC 2047 encoding for non-ASCII
        assert "Subject:" in result
        # Either original or encoded version should appear
        assert "世界" in result or "=?utf-8?b?" in result


class TestMimeBuilderHtmlAlternative:
    """Test HTML with text fallback (multipart/alternative)."""

    def test_html_with_text(self):
        """Test HTML message with text fallback."""
        builder = MimeBuilder()
        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="Plain text version",
            html="<p>HTML <strong>version</strong></p>",
        )

        assert "multipart/alternative" in result
        assert "Plain text version" in result
        assert "<p>HTML" in result or "HTML" in result  # May be sanitized
        assert "boundary=" in result

    def test_html_sanitization(self):
        """Test HTML is sanitized before building."""
        builder = MimeBuilder()
        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="Safe",
            html="<p>Safe</p><script>alert(1)</script>",
        )

        # Script should be removed
        assert "script" not in result.lower()
        assert "Safe" in result


class TestMimeBuilderInlineImages:
    """Test HTML with inline images (multipart/related)."""

    def test_html_with_inline_image(self):
        """Test HTML with single inline image."""
        builder = MimeBuilder()
        html = '<p>See logo: <img src="cid:logo"></p>'
        inline = [
            InlineImage(
                cid="logo",
                filename="logo.png",
                content_type="image/png",
                data=b"fake png data",
            )
        ]

        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="Plain text",
            html=html,
            inline=inline,
        )

        assert "multipart/related" in result
        assert "multipart/alternative" in result
        assert "Content-ID: <logo>" in result
        assert "Content-Type: image/png" in result
        assert "Content-Disposition: inline" in result
        # Base64-encoded image data should be present
        encoded = base64.b64encode(b"fake png data").decode("ascii")
        assert encoded in result

    def test_multiple_inline_images(self):
        """Test HTML with multiple inline images."""
        builder = MimeBuilder()
        html = '<img src="cid:logo"><img src="cid:banner">'
        inline = [
            InlineImage(
                cid="logo",
                filename="logo.png",
                content_type="image/png",
                data=b"logo data",
            ),
            InlineImage(
                cid="banner",
                filename="banner.jpg",
                content_type="image/jpeg",
                data=b"banner data",
            ),
        ]

        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="Plain",
            html=html,
            inline=inline,
        )

        assert "Content-ID: <logo>" in result
        assert "Content-ID: <banner>" in result
        assert "image/png" in result
        assert "image/jpeg" in result

    def test_cid_validation_mismatch(self):
        """Test CID mismatch raises error."""
        builder = MimeBuilder()
        html = '<img src="cid:logo">'
        inline = [
            InlineImage(
                cid="wrong",
                filename="wrong.png",
                content_type="image/png",
                data=b"data",
            )
        ]

        with pytest.raises(ValueError, match="validation_error"):
            builder.build_message(
                to="alice@example.com",
                subject="Test",
                text="Plain",
                html=html,
                inline=inline,
            )


class TestMimeBuilderAttachments:
    """Test messages with attachments (multipart/mixed)."""

    def test_single_attachment(self):
        """Test message with single attachment."""
        builder = MimeBuilder()
        attachments = [
            Attachment(
                filename="report.pdf",
                content_type="application/pdf",
                data=b"fake pdf",
            )
        ]

        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="See attached",
            attachments=attachments,
        )

        assert "multipart/mixed" in result
        assert "Content-Type: application/pdf" in result
        assert "Content-Disposition: attachment" in result
        assert 'filename="report.pdf"' in result or "report.pdf" in result
        # Base64-encoded attachment data
        encoded = base64.b64encode(b"fake pdf").decode("ascii")
        assert encoded in result

    def test_html_with_attachments(self):
        """Test HTML message with attachments."""
        builder = MimeBuilder()
        attachments = [
            Attachment(
                filename="doc.pdf",
                content_type="application/pdf",
                data=b"pdf data",
            )
        ]

        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="Plain",
            html="<p>HTML</p>",
            attachments=attachments,
        )

        assert "multipart/mixed" in result
        assert "multipart/alternative" in result
        assert "application/pdf" in result

    def test_full_complexity(self):
        """Test HTML + inline images + attachments (full nesting)."""
        builder = MimeBuilder()
        html = '<p>Logo: <img src="cid:logo"></p>'
        inline = [
            InlineImage(
                cid="logo",
                filename="logo.png",
                content_type="image/png",
                data=b"logo",
            )
        ]
        attachments = [
            Attachment(
                filename="report.pdf",
                content_type="application/pdf",
                data=b"pdf",
            )
        ]

        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="Plain",
            html=html,
            inline=inline,
            attachments=attachments,
        )

        # Should have all three multipart types
        assert "multipart/mixed" in result
        assert "multipart/related" in result
        assert "multipart/alternative" in result
        assert "Content-ID: <logo>" in result
        assert "application/pdf" in result


class TestMimeBoundaries:
    """Test MIME boundary generation and structure."""

    def test_unique_boundaries(self):
        """Test boundaries are unique across multiple messages."""
        builder = MimeBuilder()
        result1 = builder.build_message(
            to="alice@example.com",
            subject="Test 1",
            text="Plain",
            html="<p>HTML</p>",
        )
        result2 = builder.build_message(
            to="bob@example.com",
            subject="Test 2",
            text="Plain",
            html="<p>HTML</p>",
        )

        # Extract boundaries from both messages
        boundaries1 = re.findall(r"boundary=\"(===.+?===)\"", result1)
        boundaries2 = re.findall(r"boundary=\"(===.+?===)\"", result2)

        # Boundaries should be different
        assert boundaries1 != boundaries2

    def test_boundary_format(self):
        """Test boundary format matches expected pattern."""
        builder = MimeBuilder()
        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="Plain",
            html="<p>HTML</p>",
        )

        # Should match: ===<32 hex chars>===
        boundaries = re.findall(r"boundary=\"(===.+?===)\"", result)
        assert len(boundaries) > 0
        for boundary in boundaries:
            assert boundary.startswith("===")
            assert boundary.endswith("===")
            # Remove === from both ends, should be 32 hex chars
            hex_part = boundary[3:-3]
            assert len(hex_part) == 32
            assert all(c in "0123456789abcdef" for c in hex_part)


class TestBase64Encoding:
    """Test Base64 encoding for attachments and inline images."""

    def test_base64_line_wrapping(self):
        """Test Base64 output is wrapped at 76 characters (RFC 2045)."""
        builder = MimeBuilder()
        # Create large attachment to test line wrapping
        attachments = [
            Attachment(
                filename="large.bin",
                content_type="application/octet-stream",
                data=b"x" * 200,  # Will produce >76 chars of base64
            )
        ]

        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="Plain",
            attachments=attachments,
        )

        # Extract base64 lines after the attachment header
        lines = result.split("\n")
        in_base64 = False
        for line in lines:
            if "Content-Transfer-Encoding: base64" in line:
                in_base64 = True
                continue
            if in_base64 and line.strip() and not line.startswith("--"):
                # This should be a base64 line
                # RFC 2045 says max 76 chars
                assert len(line.strip()) <= 76


class TestEdgeCases:
    """Test edge cases and adversarial inputs."""

    def test_empty_text_body(self):
        """Test message with empty text body."""
        builder = MimeBuilder()
        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="",
        )
        assert "To: alice@example.com" in result

    def test_unicode_filename(self):
        """Test Unicode filename is encoded correctly."""
        builder = MimeBuilder()
        attachments = [
            Attachment(
                filename="文档.pdf",
                content_type="application/pdf",
                data=b"data",
            )
        ]

        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="Plain",
            attachments=attachments,
        )

        # Should use RFC 2231 encoding for non-ASCII filenames
        assert "filename*=utf-8''" in result or "文档" in result

    def test_long_subject(self):
        """Test very long subject is handled."""
        builder = MimeBuilder()
        long_subject = "A" * 200
        result = builder.build_message(
            to="alice@example.com",
            subject=long_subject,
            text="Body",
        )

        assert "Subject:" in result

    def test_special_chars_in_email(self):
        """Test special characters in email addresses."""
        builder = MimeBuilder()
        result = builder.build_message(
            to="user+tag@example.com",
            subject="Test",
            text="Body",
        )

        assert "To: user+tag@example.com" in result

    def test_multiple_cc_recipients(self):
        """Test multiple CC recipients."""
        builder = MimeBuilder()
        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="Body",
            cc=["bob@example.com", "charlie@example.com"],
        )

        assert "Cc: bob@example.com, charlie@example.com" in result

    def test_binary_attachment(self):
        """Test binary data in attachment is handled."""
        builder = MimeBuilder()
        # Create binary data with null bytes
        binary_data = bytes(range(256))
        attachments = [
            Attachment(
                filename="binary.bin",
                content_type="application/octet-stream",
                data=binary_data,
            )
        ]

        result = builder.build_message(
            to="alice@example.com",
            subject="Test",
            text="Plain",
            attachments=attachments,
        )

        # Base64 encoding should handle binary data (may be line-wrapped)
        encoded = base64.b64encode(binary_data).decode("ascii")
        # Remove whitespace from result to compare
        result_no_whitespace = result.replace("\n", "").replace("\r", "")
        assert encoded in result_no_whitespace


class TestRFC5322Compliance:
    """Test RFC 5322 compliance (CRLF line endings)."""

    def test_mime_uses_crlf_only(self):
        """Test that MIME output uses CRLF (\\r\\n) line endings, not bare LF (\\n).

        RFC 5322 requires CRLF for email line endings. Bare LF is non-compliant.
        """
        builder = MimeBuilder()
        result = builder.build_message(
            to="alice@example.com",
            subject="Test CRLF",
            text="Test body",
            html="<p>HTML body</p>",
        )

        # Check that result contains CRLF line endings
        assert "\r\n" in result, "MIME output must contain CRLF line endings"

        # Check for bare LF (not preceded by CR)
        # Split by \r\n first, then check if any remaining segments have \n
        segments = result.split("\r\n")
        for segment in segments:
            # If a segment contains \n, it's a bare LF (non-compliant)
            assert "\n" not in segment, (
                f"Found bare LF (not CRLF) in MIME output. "
                f"RFC 5322 requires CRLF line endings. Segment: {segment[:100]!r}"
            )
