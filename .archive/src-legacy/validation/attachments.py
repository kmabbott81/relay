"""Attachment validation for Gmail rich email.

Sprint 54: Validates attachment size, MIME types, filenames.
"""

import os
from dataclasses import dataclass
from typing import Optional


def _record_validation_error(error_code: str) -> None:
    """Record structured error metric for validation errors.

    Args:
        error_code: Validation error code (e.g., "validation_error_attachment_too_large")
    """
    from relay_ai.telemetry.prom import record_structured_error

    record_structured_error(provider="google", action="gmail.send", code=error_code, source="gmail.validation")


@dataclass
class Attachment:
    """Regular attachment (not inline)."""

    filename: str
    content_type: str
    data: bytes  # Raw binary (NOT base64-encoded)


@dataclass
class InlineImage:
    """Inline image with CID reference."""

    cid: str
    filename: str
    content_type: str
    data: bytes  # Raw binary (NOT base64-encoded)


# Allowed MIME types (from spec)
ALLOWED_ATTACHMENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "text/plain",
    "text/csv",
    "application/json",
    "application/xml",
}

# Blocked MIME types (from spec)
BLOCKED_ATTACHMENT_TYPES = {
    "application/x-msdownload",  # .exe
    "application/x-sh",  # .sh
    "application/x-bat",  # .bat
    "application/x-powershell",  # .ps1
    "application/zip",
    "application/x-rar-compressed",
    "application/x-7z-compressed",
    "application/java-archive",  # .jar
    "application/x-deb",
    "application/x-rpm",
}

# Allowed inline image types
ALLOWED_INLINE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
}

# Size limits (from spec)
MAX_ATTACHMENT_SIZE = 25 * 1024 * 1024  # 25MB
MAX_INLINE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_ATTACHMENTS = 10
MAX_INLINE = 20
MAX_FILENAME_LENGTH = 255


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename (basename only, no path components)
    """
    # Remove any path components
    filename = os.path.basename(filename)

    # Remove any remaining .. or path separators
    filename = filename.replace("..", "").replace("/", "").replace("\\", "")

    # Trim to max length
    if len(filename) > MAX_FILENAME_LENGTH:
        name, ext = os.path.splitext(filename)
        max_name_len = MAX_FILENAME_LENGTH - len(ext)
        filename = name[:max_name_len] + ext

    return filename


def validate_attachment(attachment: Attachment) -> None:
    """Validate a single attachment.

    Args:
        attachment: Attachment to validate

    Raises:
        ValueError: If validation fails (with reason code)
    """
    # Check size
    if len(attachment.data) > MAX_ATTACHMENT_SIZE:
        _record_validation_error("validation_error_attachment_too_large")
        raise ValueError(
            f"validation_error_attachment_too_large: {len(attachment.data)} bytes "
            f"exceeds {MAX_ATTACHMENT_SIZE} bytes"
        )

    # Check blocked MIME types
    if attachment.content_type in BLOCKED_ATTACHMENT_TYPES:
        _record_validation_error("validation_error_blocked_mime_type")
        raise ValueError(f"validation_error_blocked_mime_type: {attachment.content_type} is not allowed")

    # Check filename length
    if len(attachment.filename) > MAX_FILENAME_LENGTH:
        raise ValueError(f"validation_error_invalid_filename: filename exceeds {MAX_FILENAME_LENGTH} chars")

    # Check for path traversal
    sanitized = sanitize_filename(attachment.filename)
    if sanitized != attachment.filename:
        # Auto-correct (not an error, but warn)
        attachment.filename = sanitized


def validate_attachments(attachments: list[Attachment]) -> None:
    """Validate list of attachments.

    Args:
        attachments: List of attachments

    Raises:
        ValueError: If validation fails
    """
    if len(attachments) > MAX_ATTACHMENTS:
        raise ValueError(
            f"validation_error_attachment_count_exceeded: {len(attachments)} attachments "
            f"exceeds limit of {MAX_ATTACHMENTS}"
        )

    for att in attachments:
        validate_attachment(att)


def validate_inline_image(inline: InlineImage) -> None:
    """Validate a single inline image.

    Args:
        inline: Inline image to validate

    Raises:
        ValueError: If validation fails
    """
    # Check size
    if len(inline.data) > MAX_INLINE_SIZE:
        raise ValueError(
            f"validation_error_inline_too_large: {len(inline.data)} bytes " f"exceeds {MAX_INLINE_SIZE} bytes"
        )

    # Check MIME type (only images allowed for inline)
    if inline.content_type not in ALLOWED_INLINE_TYPES:
        raise ValueError(f"validation_error_blocked_mime_type: {inline.content_type} not allowed for inline images")

    # Check CID format
    if not inline.cid or len(inline.cid) > 100:
        raise ValueError(f"validation_error_invalid_cid: CID '{inline.cid}' is invalid or too long")

    # Sanitize filename
    sanitized = sanitize_filename(inline.filename)
    if sanitized != inline.filename:
        inline.filename = sanitized


def validate_inline_images(inline_images: list[InlineImage]) -> None:
    """Validate list of inline images.

    Args:
        inline_images: List of inline images

    Raises:
        ValueError: If validation fails
    """
    if len(inline_images) > MAX_INLINE:
        raise ValueError(
            f"validation_error_inline_count_exceeded: {len(inline_images)} inline images "
            f"exceeds limit of {MAX_INLINE}"
        )

    # Check for duplicate CIDs
    cids = [img.cid for img in inline_images]
    if len(cids) != len(set(cids)):
        duplicates = [cid for cid in cids if cids.count(cid) > 1]
        raise ValueError(f"validation_error_duplicate_cid: Duplicate CIDs found: {duplicates}")

    for img in inline_images:
        validate_inline_image(img)


def validate_total_size(
    attachments: Optional[list[Attachment]] = None,
    inline_images: Optional[list[InlineImage]] = None,
) -> None:
    """Validate total payload size.

    Args:
        attachments: List of attachments
        inline_images: List of inline images

    Raises:
        ValueError: If total size exceeds 50MB
    """
    total_size = 0

    if attachments:
        total_size += sum(len(att.data) for att in attachments)

    if inline_images:
        total_size += sum(len(img.data) for img in inline_images)

    MAX_TOTAL_SIZE = 50 * 1024 * 1024  # 50MB
    if total_size > MAX_TOTAL_SIZE:
        raise ValueError(f"validation_error_total_size_exceeded: {total_size} bytes exceeds {MAX_TOTAL_SIZE} bytes")
