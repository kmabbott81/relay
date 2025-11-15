"""Microsoft Graph API JSON message builder.

Sprint 55 Week 2: Translates our MIME model to Microsoft Graph sendMail JSON format.

Microsoft Graph uses JSON instead of MIME, with different structure:
- fileAttachment with contentBytes (base64) and contentId for inline images
- HTML body with separate text body
- attachments array with type discriminator (fileAttachment)
"""

import base64
import time
from typing import Any, Optional

from relay_ai.validation.attachments import Attachment, InlineImage
from relay_ai.validation.html_sanitization import (
    extract_cids_from_html,
    sanitize_html,
    validate_cid_references,
)


class GraphMessageBuilder:
    """Builds Microsoft Graph sendMail JSON payloads.

    Microsoft Graph sendMail endpoint expects:
    POST https://graph.microsoft.com/v1.0/me/sendMail
    {
      "message": {
        "subject": "...",
        "body": {
          "contentType": "Text" or "HTML",
          "content": "..."
        },
        "toRecipients": [{"emailAddress": {"address": "..."}}],
        "ccRecipients": [...],
        "bccRecipients": [...],
        "attachments": [
          {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": "...",
            "contentType": "...",
            "contentBytes": "base64...",
            "contentId": "cid" (optional, for inline),
            "isInline": true/false
          }
        ]
      },
      "saveToSentItems": false
    }
    """

    def __init__(self):
        """Initialize Graph message builder."""
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
    ) -> dict[str, Any]:
        """Build Microsoft Graph sendMail JSON payload.

        Args:
            to: Recipient email address
            subject: Email subject
            text: Plain text body (required fallback)
            html: HTML body (optional, preferred over text if provided)
            cc: CC recipients (optional)
            bcc: BCC recipients (optional)
            attachments: Regular attachments (optional)
            inline: Inline images with CID refs (optional)

        Returns:
            JSON payload for POST /me/sendMail

        Raises:
            ValueError: If validation fails

        Metrics emitted:
            - outlook_graph_build_seconds (histogram)
            - outlook_attachment_bytes_total (counter)
            - outlook_inline_refs_total (counter)
            - outlook_html_sanitization_changes_total (counter)
        """
        self._start_time = time.perf_counter()

        try:
            # Import metrics here to avoid circular dependency
            from relay_ai.telemetry.prom import (
                outlook_attachment_bytes_total,
                outlook_graph_build_seconds,
                outlook_html_sanitization_changes_total,
                outlook_inline_refs_total,
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
                if outlook_html_sanitization_changes_total:
                    for change_type, count in changes.items():
                        if count > 0:
                            outlook_html_sanitization_changes_total.labels(change_type=change_type).inc(count)

            # Validate CID references
            if html_sanitized and inline:
                validate_cid_references(html_sanitized, inline)

            # Track attachment sizes (if telemetry enabled)
            if attachments and outlook_attachment_bytes_total:
                for att in attachments:
                    outlook_attachment_bytes_total.labels(result="accepted").inc(len(att.data))

            # Track inline CID matching (if telemetry enabled)
            if inline and outlook_inline_refs_total:
                cids_in_html = extract_cids_from_html(html_sanitized or "")
                for img in inline:
                    if img.cid in cids_in_html:
                        outlook_inline_refs_total.labels(result="matched").inc()
                    else:
                        outlook_inline_refs_total.labels(result="orphan_cid").inc()

            # Build Graph API JSON payload
            message = {
                "subject": subject,
                "body": {
                    "contentType": "HTML" if html_sanitized else "Text",
                    "content": html_sanitized if html_sanitized else text,
                },
                "toRecipients": [{"emailAddress": {"address": to}}],
            }

            # Add CC recipients
            if cc:
                message["ccRecipients"] = [{"emailAddress": {"address": addr}} for addr in cc]

            # Add BCC recipients
            if bcc:
                message["bccRecipients"] = [{"emailAddress": {"address": addr}} for addr in bcc]

            # Add attachments (regular + inline)
            graph_attachments = []

            # Regular attachments
            if attachments:
                for att in attachments:
                    graph_attachments.append(
                        {
                            "@odata.type": "#microsoft.graph.fileAttachment",
                            "name": att.filename,
                            "contentType": att.content_type,
                            "contentBytes": base64.b64encode(att.data).decode("ascii"),
                            "isInline": False,
                        }
                    )

            # Inline images (with contentId for CID references)
            if inline:
                for img in inline:
                    graph_attachments.append(
                        {
                            "@odata.type": "#microsoft.graph.fileAttachment",
                            "name": img.filename,
                            "contentType": img.content_type,
                            "contentBytes": base64.b64encode(img.data).decode("ascii"),
                            "contentId": img.cid,  # CID for inline reference
                            "isInline": True,
                        }
                    )

            if graph_attachments:
                message["attachments"] = graph_attachments

            # Wrap in sendMail request body
            payload = {"message": message, "saveToSentItems": False}

            return payload

        finally:
            # Emit build time metric (if telemetry enabled)
            if self._start_time:
                duration = time.perf_counter() - self._start_time
                from relay_ai.telemetry.prom import outlook_graph_build_seconds

                if outlook_graph_build_seconds:
                    outlook_graph_build_seconds.observe(duration)

    def estimate_payload_size(
        self,
        attachments: Optional[list[Attachment]] = None,
        inline: Optional[list[InlineImage]] = None,
    ) -> int:
        """Estimate JSON payload size for large attachment handling.

        Microsoft Graph API limits:
        - Total request size: ~4 MB for sendMail
        - For larger attachments, must use createUploadSession

        Args:
            attachments: Regular attachments
            inline: Inline images

        Returns:
            Estimated payload size in bytes (including base64 overhead)
        """
        size = 1024  # Base JSON structure overhead

        if attachments:
            for att in attachments:
                # Base64 encoding increases size by ~33%
                size += len(att.data) * 4 // 3
                size += 200  # JSON structure overhead per attachment

        if inline:
            for img in inline:
                size += len(img.data) * 4 // 3
                size += 200  # JSON structure overhead per inline image

        return size


def should_use_upload_session(
    attachments: Optional[list[Attachment]] = None,
    inline: Optional[list[InlineImage]] = None,
) -> bool:
    """Check if large attachment upload session is needed.

    Microsoft Graph API limits:
    - sendMail: ~4 MB total payload (3 MB attachments after base64)
    - createUploadSession: up to 150 MB per attachment

    Args:
        attachments: Regular attachments
        inline: Inline images

    Returns:
        True if upload session needed, False otherwise
    """
    builder = GraphMessageBuilder()
    estimated_size = builder.estimate_payload_size(attachments, inline)

    # Use 3 MB threshold (conservative, allows for JSON overhead)
    UPLOAD_SESSION_THRESHOLD = 3 * 1024 * 1024

    return estimated_size > UPLOAD_SESSION_THRESHOLD
