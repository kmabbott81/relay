"""MIME message builder for Gmail API.

Sprint 54: Builds RFC822 MIME messages with HTML, attachments, and inline images.
"""

import base64
import secrets
import time
from typing import Optional

from relay_ai.validation.attachments import Attachment, InlineImage
from relay_ai.validation.html_sanitization import (
    extract_cids_from_html,
    sanitize_html,
    validate_cid_references,
)


def _generate_boundary() -> str:
    """Generate secure random MIME boundary.

    Returns:
        Boundary string: ===<16 hex bytes>===
    """
    random_hex = secrets.token_hex(16)
    return f"==={random_hex}==="


def _encode_header(value: str) -> str:
    """Encode header value for non-ASCII characters (RFC 2047).

    Args:
        value: Header value (e.g., subject, filename)

    Returns:
        RFC 2047 encoded string if needed, otherwise original
    """
    try:
        # Try ASCII encoding first
        value.encode("ascii")
        return value
    except UnicodeEncodeError:
        # Need RFC 2047 encoding
        encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
        return f"=?utf-8?b?{encoded}?="


def _encode_filename(filename: str) -> str:
    """Encode filename for Content-Disposition header (RFC 2231).

    Args:
        filename: Filename string

    Returns:
        Encoded filename parameter
    """
    try:
        # Try ASCII first
        filename.encode("ascii")
        return f'filename="{filename}"'
    except UnicodeEncodeError:
        # Use RFC 2231 encoding
        import urllib.parse

        encoded = urllib.parse.quote(filename, safe="")
        return f"filename*=utf-8''{encoded}"


class MimeBuilder:
    """Builds RFC822 MIME messages for Gmail API.

    Handles:
    - Text-only messages
    - HTML with text fallback (multipart/alternative)
    - Inline images with CID references (multipart/related)
    - Regular attachments (multipart/mixed)
    - Nested multipart structures

    Emits telemetry for build time, attachment sizes, CID tracking.
    """

    def __init__(self):
        """Initialize MIME builder."""
        self._start_time: Optional[float] = None

    def build_message(
        self,
        to: str,
        subject: str,
        text: str,
        html: Optional[str] = None,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        attachments: Optional[list[Attachment]] = None,
        inline: Optional[list[InlineImage]] = None,
    ) -> str:
        """Build complete MIME message.

        Args:
            to: Recipient email
            subject: Email subject
            text: Plain text body (required fallback)
            html: HTML body (optional)
            cc: CC recipients (optional)
            bcc: BCC recipients (optional)
            attachments: Regular attachments (optional)
            inline: Inline images with CID refs (optional)

        Returns:
            RFC822 MIME message string

        Raises:
            ValueError: If validation fails

        Metrics emitted:
            - gmail_mime_build_seconds (histogram)
            - gmail_attachment_bytes_total (counter)
            - gmail_inline_refs_total (counter)
            - gmail_html_sanitization_changes_total (counter)
        """
        self._start_time = time.perf_counter()

        try:
            # Import metrics here to avoid circular dependency
            from relay_ai.telemetry.prom import (
                gmail_attachment_bytes_total,
                gmail_html_sanitization_changes_total,
                gmail_inline_refs_total,
                gmail_mime_build_seconds,
            )

            # Validate attachments (size, MIME type, count)
            if attachments:
                from relay_ai.validation.attachments import validate_attachments

                validate_attachments(attachments)

            # Validate inline images (size, MIME type, count, CID format)
            if inline:
                from relay_ai.validation.attachments import validate_inline_images

                validate_inline_images(inline)

            # Validate total size (attachments + inline)
            if attachments or inline:
                from relay_ai.validation.attachments import validate_total_size

                validate_total_size(attachments, inline)

            # Validate and sanitize HTML if provided
            html_sanitized = None
            if html:
                html_sanitized, changes = sanitize_html(html)
                # Emit sanitization metrics (if telemetry enabled)
                if gmail_html_sanitization_changes_total:
                    for change_type, count in changes.items():
                        if count > 0:
                            gmail_html_sanitization_changes_total.labels(change_type=change_type).inc(count)

            # Validate CID references
            if html_sanitized and inline:
                validate_cid_references(html_sanitized, inline)

            # Track attachment sizes (if telemetry enabled)
            if attachments and gmail_attachment_bytes_total:
                for att in attachments:
                    gmail_attachment_bytes_total.labels(result="accepted").inc(len(att.data))

            # Track inline CID matching (if telemetry enabled)
            if inline and gmail_inline_refs_total:
                cids_in_html = extract_cids_from_html(html_sanitized or "")
                for img in inline:
                    if img.cid in cids_in_html:
                        gmail_inline_refs_total.labels(result="matched").inc()
                    else:
                        gmail_inline_refs_total.labels(result="orphan_cid").inc()

            # Choose MIME structure based on content
            if not html_sanitized and not attachments and not inline:
                # Simple text-only message
                return self._build_text_only(to, subject, text, cc, bcc)

            elif html_sanitized and not attachments and not inline:
                # HTML with text fallback (multipart/alternative)
                return self._build_html_alternative(to, subject, text, html_sanitized, cc, bcc)

            elif html_sanitized and inline and not attachments:
                # HTML + inline images (multipart/related wrapping alternative)
                return self._build_with_inline(to, subject, text, html_sanitized, cc, bcc, inline)

            else:
                # Full complexity: attachments with optional HTML/inline
                return self._build_with_attachments(to, subject, text, html_sanitized, cc, bcc, attachments, inline)

        finally:
            # Emit build time metric (if telemetry enabled)
            if self._start_time:
                duration = time.perf_counter() - self._start_time
                from relay_ai.telemetry.prom import gmail_mime_build_seconds

                if gmail_mime_build_seconds:
                    gmail_mime_build_seconds.observe(duration)

    def _build_text_only(
        self,
        to: str,
        subject: str,
        text: str,
        cc: Optional[list[str]],
        bcc: Optional[list[str]],
    ) -> str:
        """Build simple text/plain message."""
        lines = []
        lines.append(f"To: {to}")
        if cc:
            lines.append(f"Cc: {', '.join(cc)}")
        if bcc:
            lines.append(f"Bcc: {', '.join(bcc)}")
        lines.append(f"Subject: {_encode_header(subject)}")
        lines.append("MIME-Version: 1.0")
        lines.append('Content-Type: text/plain; charset="utf-8"')
        lines.append("Content-Transfer-Encoding: 8bit")
        lines.append("")
        lines.append(text)

        return "\r\n".join(lines)

    def _build_html_alternative(
        self,
        to: str,
        subject: str,
        text: str,
        html: str,
        cc: Optional[list[str]],
        bcc: Optional[list[str]],
    ) -> str:
        """Build multipart/alternative (text + HTML)."""
        boundary = _generate_boundary()

        lines = []
        lines.append(f"To: {to}")
        if cc:
            lines.append(f"Cc: {', '.join(cc)}")
        if bcc:
            lines.append(f"Bcc: {', '.join(bcc)}")
        lines.append(f"Subject: {_encode_header(subject)}")
        lines.append("MIME-Version: 1.0")
        lines.append(f'Content-Type: multipart/alternative; boundary="{boundary}"')
        lines.append("")

        # Text part
        lines.append(f"--{boundary}")
        lines.append('Content-Type: text/plain; charset="utf-8"')
        lines.append("Content-Transfer-Encoding: 8bit")
        lines.append("")
        lines.append(text)
        lines.append("")

        # HTML part
        lines.append(f"--{boundary}")
        lines.append('Content-Type: text/html; charset="utf-8"')
        lines.append("Content-Transfer-Encoding: 8bit")
        lines.append("")
        lines.append(html)
        lines.append("")

        lines.append(f"--{boundary}--")

        return "\r\n".join(lines)

    def _build_with_inline(
        self,
        to: str,
        subject: str,
        text: str,
        html: str,
        cc: Optional[list[str]],
        bcc: Optional[list[str]],
        inline: list[InlineImage],
    ) -> str:
        """Build multipart/related (HTML + inline images)."""
        boundary_related = _generate_boundary()
        boundary_alt = _generate_boundary()

        lines = []
        lines.append(f"To: {to}")
        if cc:
            lines.append(f"Cc: {', '.join(cc)}")
        if bcc:
            lines.append(f"Bcc: {', '.join(bcc)}")
        lines.append(f"Subject: {_encode_header(subject)}")
        lines.append("MIME-Version: 1.0")
        lines.append(f'Content-Type: multipart/related; boundary="{boundary_related}"')
        lines.append("")

        # Nested multipart/alternative
        lines.append(f"--{boundary_related}")
        lines.append(f'Content-Type: multipart/alternative; boundary="{boundary_alt}"')
        lines.append("")

        # Text part
        lines.append(f"--{boundary_alt}")
        lines.append('Content-Type: text/plain; charset="utf-8"')
        lines.append("Content-Transfer-Encoding: 8bit")
        lines.append("")
        lines.append(text)
        lines.append("")

        # HTML part
        lines.append(f"--{boundary_alt}")
        lines.append('Content-Type: text/html; charset="utf-8"')
        lines.append("Content-Transfer-Encoding: 8bit")
        lines.append("")
        lines.append(html)
        lines.append("")

        lines.append(f"--{boundary_alt}--")
        lines.append("")

        # Inline images
        for img in inline:
            lines.append(f"--{boundary_related}")
            lines.append(f"Content-Type: {img.content_type}")
            lines.append("Content-Transfer-Encoding: base64")
            lines.append(f"Content-ID: <{img.cid}>")
            lines.append(f"Content-Disposition: inline; {_encode_filename(img.filename)}")
            lines.append("")
            # Base64 encode image data
            encoded = base64.b64encode(img.data).decode("ascii")
            # Split into 76-char lines (RFC 2045)
            for i in range(0, len(encoded), 76):
                lines.append(encoded[i : i + 76])
            lines.append("")

        lines.append(f"--{boundary_related}--")

        return "\r\n".join(lines)

    def _build_with_attachments(
        self,
        to: str,
        subject: str,
        text: str,
        html: Optional[str],
        cc: Optional[list[str]],
        bcc: Optional[list[str]],
        attachments: Optional[list[Attachment]],
        inline: Optional[list[InlineImage]],
    ) -> str:
        """Build multipart/mixed (with attachments)."""
        boundary_mixed = _generate_boundary()

        lines = []
        lines.append(f"To: {to}")
        if cc:
            lines.append(f"Cc: {', '.join(cc)}")
        if bcc:
            lines.append(f"Bcc: {', '.join(bcc)}")
        lines.append(f"Subject: {_encode_header(subject)}")
        lines.append("MIME-Version: 1.0")
        lines.append(f'Content-Type: multipart/mixed; boundary="{boundary_mixed}"')
        lines.append("")

        # Body part (could be text, HTML, or related)
        lines.append(f"--{boundary_mixed}")

        if html and inline:
            # Embedded multipart/related
            boundary_related = _generate_boundary()
            boundary_alt = _generate_boundary()

            lines.append(f'Content-Type: multipart/related; boundary="{boundary_related}"')
            lines.append("")

            # Nested multipart/alternative
            lines.append(f"--{boundary_related}")
            lines.append(f'Content-Type: multipart/alternative; boundary="{boundary_alt}"')
            lines.append("")

            # Text part
            lines.append(f"--{boundary_alt}")
            lines.append('Content-Type: text/plain; charset="utf-8"')
            lines.append("Content-Transfer-Encoding: 8bit")
            lines.append("")
            lines.append(text)
            lines.append("")

            # HTML part
            lines.append(f"--{boundary_alt}")
            lines.append('Content-Type: text/html; charset="utf-8"')
            lines.append("Content-Transfer-Encoding: 8bit")
            lines.append("")
            lines.append(html)
            lines.append("")

            lines.append(f"--{boundary_alt}--")
            lines.append("")

            # Inline images
            for img in inline:
                lines.append(f"--{boundary_related}")
                lines.append(f"Content-Type: {img.content_type}")
                lines.append("Content-Transfer-Encoding: base64")
                lines.append(f"Content-ID: <{img.cid}>")
                lines.append(f"Content-Disposition: inline; {_encode_filename(img.filename)}")
                lines.append("")
                encoded = base64.b64encode(img.data).decode("ascii")
                for i in range(0, len(encoded), 76):
                    lines.append(encoded[i : i + 76])
                lines.append("")

            lines.append(f"--{boundary_related}--")
            lines.append("")

        elif html:
            # Just multipart/alternative
            boundary_alt = _generate_boundary()
            lines.append(f'Content-Type: multipart/alternative; boundary="{boundary_alt}"')
            lines.append("")

            # Text part
            lines.append(f"--{boundary_alt}")
            lines.append('Content-Type: text/plain; charset="utf-8"')
            lines.append("Content-Transfer-Encoding: 8bit")
            lines.append("")
            lines.append(text)
            lines.append("")

            # HTML part
            lines.append(f"--{boundary_alt}")
            lines.append('Content-Type: text/html; charset="utf-8"')
            lines.append("Content-Transfer-Encoding: 8bit")
            lines.append("")
            lines.append(html)
            lines.append("")

            lines.append(f"--{boundary_alt}--")
            lines.append("")

        else:
            # Just plain text
            lines.append('Content-Type: text/plain; charset="utf-8"')
            lines.append("Content-Transfer-Encoding: 8bit")
            lines.append("")
            lines.append(text)
            lines.append("")

        # Regular attachments
        if attachments:
            for att in attachments:
                lines.append(f"--{boundary_mixed}")
                lines.append(f"Content-Type: {att.content_type}")
                lines.append("Content-Transfer-Encoding: base64")
                lines.append(f"Content-Disposition: attachment; {_encode_filename(att.filename)}")
                lines.append("")
                encoded = base64.b64encode(att.data).decode("ascii")
                for i in range(0, len(encoded), 76):
                    lines.append(encoded[i : i + 76])
                lines.append("")

        lines.append(f"--{boundary_mixed}--")

        return "\r\n".join(lines)
