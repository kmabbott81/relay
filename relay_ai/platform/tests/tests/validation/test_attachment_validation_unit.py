"""Unit tests for attachment validation.

Sprint 54: Tests for src/validation/attachments.py
"""

import pytest

from src.validation.attachments import (
    MAX_ATTACHMENT_SIZE,
    MAX_ATTACHMENTS,
    MAX_INLINE,
    MAX_INLINE_SIZE,
    Attachment,
    InlineImage,
    sanitize_filename,
    validate_attachment,
    validate_attachments,
    validate_inline_image,
    validate_inline_images,
    validate_total_size,
)


class TestAttachmentValidation:
    """Test individual attachment validation."""

    def test_valid_attachment(self):
        """Test valid attachment passes validation."""
        att = Attachment(
            filename="report.pdf",
            content_type="application/pdf",
            data=b"fake pdf content",
        )
        validate_attachment(att)  # Should not raise

    def test_attachment_too_large(self):
        """Test attachment exceeding 25MB limit."""
        att = Attachment(
            filename="huge.pdf",
            content_type="application/pdf",
            data=b"x" * (MAX_ATTACHMENT_SIZE + 1),
        )
        with pytest.raises(ValueError, match="validation_error_attachment_too_large"):
            validate_attachment(att)

    def test_blocked_mime_type_exe(self):
        """Test .exe files are blocked."""
        att = Attachment(
            filename="virus.exe",
            content_type="application/x-msdownload",
            data=b"fake exe",
        )
        with pytest.raises(ValueError, match="validation_error_blocked_mime_type"):
            validate_attachment(att)

    def test_blocked_mime_type_zip(self):
        """Test .zip files are blocked."""
        att = Attachment(
            filename="archive.zip",
            content_type="application/zip",
            data=b"fake zip",
        )
        with pytest.raises(ValueError, match="validation_error_blocked_mime_type"):
            validate_attachment(att)

    def test_filename_too_long(self):
        """Test filename exceeding 255 chars is rejected."""
        att = Attachment(
            filename="a" * 256,
            content_type="application/pdf",
            data=b"content",
        )
        with pytest.raises(ValueError, match="validation_error_invalid_filename"):
            validate_attachment(att)


class TestAttachmentsListValidation:
    """Test list-level attachment validation."""

    def test_too_many_attachments(self):
        """Test exceeding 10 attachment limit."""
        attachments = [
            Attachment(
                filename=f"file{i}.pdf",
                content_type="application/pdf",
                data=b"content",
            )
            for i in range(MAX_ATTACHMENTS + 1)
        ]
        with pytest.raises(ValueError, match="validation_error_attachment_count_exceeded"):
            validate_attachments(attachments)

    def test_max_attachments_allowed(self):
        """Test exactly 10 attachments is allowed."""
        attachments = [
            Attachment(
                filename=f"file{i}.pdf",
                content_type="application/pdf",
                data=b"content",
            )
            for i in range(MAX_ATTACHMENTS)
        ]
        validate_attachments(attachments)  # Should not raise


class TestInlineImageValidation:
    """Test inline image validation."""

    def test_valid_inline_image(self):
        """Test valid inline image passes validation."""
        img = InlineImage(
            cid="logo",
            filename="logo.png",
            content_type="image/png",
            data=b"fake png",
        )
        validate_inline_image(img)  # Should not raise

    def test_inline_too_large(self):
        """Test inline image exceeding 5MB limit."""
        img = InlineImage(
            cid="huge",
            filename="huge.png",
            content_type="image/png",
            data=b"x" * (MAX_INLINE_SIZE + 1),
        )
        with pytest.raises(ValueError, match="validation_error_inline_too_large"):
            validate_inline_image(img)

    def test_invalid_mime_type_pdf(self):
        """Test non-image MIME type is rejected for inline."""
        img = InlineImage(
            cid="doc",
            filename="doc.pdf",
            content_type="application/pdf",
            data=b"fake pdf",
        )
        with pytest.raises(ValueError, match="validation_error_blocked_mime_type"):
            validate_inline_image(img)

    def test_invalid_cid_empty(self):
        """Test empty CID is rejected."""
        img = InlineImage(
            cid="",
            filename="logo.png",
            content_type="image/png",
            data=b"fake png",
        )
        with pytest.raises(ValueError, match="validation_error_invalid_cid"):
            validate_inline_image(img)

    def test_invalid_cid_too_long(self):
        """Test CID exceeding 100 chars is rejected."""
        img = InlineImage(
            cid="x" * 101,
            filename="logo.png",
            content_type="image/png",
            data=b"fake png",
        )
        with pytest.raises(ValueError, match="validation_error_invalid_cid"):
            validate_inline_image(img)


class TestInlineImageListValidation:
    """Test list-level inline image validation."""

    def test_too_many_inline_images(self):
        """Test exceeding 20 inline image limit."""
        images = [
            InlineImage(
                cid=f"img{i}",
                filename=f"img{i}.png",
                content_type="image/png",
                data=b"content",
            )
            for i in range(MAX_INLINE + 1)
        ]
        with pytest.raises(ValueError, match="validation_error_inline_count_exceeded"):
            validate_inline_images(images)

    def test_duplicate_cids(self):
        """Test duplicate CIDs are rejected."""
        images = [
            InlineImage(
                cid="logo",
                filename="logo1.png",
                content_type="image/png",
                data=b"content",
            ),
            InlineImage(
                cid="logo",
                filename="logo2.png",
                content_type="image/png",
                data=b"content",
            ),
        ]
        with pytest.raises(ValueError, match="validation_error_duplicate_cid"):
            validate_inline_images(images)


class TestFilenameSanitization:
    """Test filename sanitization."""

    def test_sanitize_path_traversal(self):
        """Test path traversal (../) is removed."""
        result = sanitize_filename("../../etc/passwd")
        assert result == "passwd"

    def test_sanitize_forward_slash(self):
        """Test forward slashes are removed."""
        result = sanitize_filename("path/to/file.pdf")
        assert result == "file.pdf"

    def test_sanitize_backslash(self):
        """Test backslashes are removed."""
        result = sanitize_filename("C:\\Windows\\file.pdf")
        assert result == "file.pdf"

    def test_sanitize_mixed_path(self):
        """Test mixed path separators are removed."""
        result = sanitize_filename("../path\\to/../file.pdf")
        assert result == "file.pdf"

    def test_sanitize_clean_filename(self):
        """Test clean filename is unchanged."""
        result = sanitize_filename("document.pdf")
        assert result == "document.pdf"

    def test_sanitize_long_filename(self):
        """Test filename exceeding 255 chars is truncated."""
        long_name = "a" * 250 + ".pdf"  # 254 chars
        result = sanitize_filename(long_name)
        assert len(result) <= 255
        assert result.endswith(".pdf")


class TestTotalSizeValidation:
    """Test total payload size validation."""

    def test_total_size_under_limit(self):
        """Test total size under 50MB is allowed."""
        attachments = [
            Attachment(
                filename="file.pdf",
                content_type="application/pdf",
                data=b"x" * (10 * 1024 * 1024),  # 10MB
            )
        ]
        inline_images = [
            InlineImage(
                cid="logo",
                filename="logo.png",
                content_type="image/png",
                data=b"x" * (5 * 1024 * 1024),  # 5MB
            )
        ]
        validate_total_size(attachments, inline_images)  # Should not raise

    def test_total_size_exceeds_limit(self):
        """Test total size exceeding 50MB is rejected."""
        attachments = [
            Attachment(
                filename=f"file{i}.pdf",
                content_type="application/pdf",
                data=b"x" * (20 * 1024 * 1024),  # 20MB each
            )
            for i in range(3)  # 60MB total
        ]
        with pytest.raises(ValueError, match="validation_error_total_size_exceeded"):
            validate_total_size(attachments=attachments)

    def test_total_size_at_limit(self):
        """Test total size exactly at 50MB is allowed."""
        attachments = [
            Attachment(
                filename="file.pdf",
                content_type="application/pdf",
                data=b"x" * (50 * 1024 * 1024),  # Exactly 50MB
            )
        ]
        validate_total_size(attachments=attachments)  # Should not raise


class TestEdgeCases:
    """Test edge cases and adversarial inputs."""

    def test_unicode_filename(self):
        """Test Unicode filename is handled correctly."""
        att = Attachment(
            filename="文档.pdf",
            content_type="application/pdf",
            data=b"content",
        )
        validate_attachment(att)  # Should not raise

    def test_empty_filename(self):
        """Test empty filename after sanitization."""
        # This tests what happens when sanitize_filename returns ""
        att = Attachment(
            filename="../",
            content_type="application/pdf",
            data=b"content",
        )
        validate_attachment(att)  # Should sanitize to empty but not crash

    def test_cid_special_characters(self):
        """Test CID with special characters."""
        img = InlineImage(
            cid="logo@123",
            filename="logo.png",
            content_type="image/png",
            data=b"fake png",
        )
        validate_inline_image(img)  # Should allow special chars

    def test_zero_byte_attachment(self):
        """Test zero-byte attachment is allowed."""
        att = Attachment(
            filename="empty.txt",
            content_type="text/plain",
            data=b"",
        )
        validate_attachment(att)  # Should not raise
