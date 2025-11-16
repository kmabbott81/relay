"""Validation utilities for Gmail rich email features.

Sprint 54: Attachment and HTML validation for safe email sending.
"""

from .attachments import (
    Attachment,
    InlineImage,
    sanitize_filename,
    validate_attachment,
    validate_attachments,
)
from .html_sanitization import extract_cids_from_html, sanitize_html

__all__ = [
    "Attachment",
    "InlineImage",
    "validate_attachment",
    "validate_attachments",
    "sanitize_filename",
    "sanitize_html",
    "extract_cids_from_html",
]
