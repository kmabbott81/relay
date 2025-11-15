"""Google action adapter (Gmail Send).

Sprint 53 Phase B: Gmail send action with OAuth token refresh.
Sprint 54 Phase C: Rich email with MIME builder, attachments, inline images.
"""

import base64
import hashlib
import json
import os
import re
import time
import uuid
from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

from ..contracts import ActionDefinition, Provider

# Simple email regex (RFC 5322 simplified)
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# Recipient limits
MAX_TOTAL_RECIPIENTS = 100


class AttachmentInput(BaseModel):
    """Attachment input (base64-encoded)."""

    filename: str = Field(..., description="Filename")
    content_type: str = Field(..., description="MIME type")
    data: str = Field(..., description="Base64-encoded file data")


class InlineImageInput(BaseModel):
    """Inline image input (base64-encoded)."""

    cid: str = Field(..., description="Content-ID for HTML reference")
    filename: str = Field(..., description="Filename")
    content_type: str = Field(..., description="MIME type (image/*)")
    data: str = Field(..., description="Base64-encoded image data")


class GmailSendParams(BaseModel):
    """Parameters for gmail.send action."""

    to: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject")
    text: str = Field(..., description="Email body (plain text)")
    html: Optional[str] = Field(None, description="HTML body (optional)")
    cc: Optional[list[str]] = Field(None, description="CC recipients")
    bcc: Optional[list[str]] = Field(None, description="BCC recipients")
    attachments: Optional[list[AttachmentInput]] = Field(None, description="Attachments")
    inline: Optional[list[InlineImageInput]] = Field(None, description="Inline images")

    @field_validator("to")
    @classmethod
    def validate_to_email(cls, v: str) -> str:
        if not EMAIL_REGEX.match(v):
            raise ValueError(f"Invalid email address: {v}")
        return v

    @field_validator("cc", "bcc")
    @classmethod
    def validate_email_list(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is not None:
            for email in v:
                if not EMAIL_REGEX.match(email):
                    raise ValueError(f"Invalid email address in list: {email}")
        return v

    def validate_recipient_count(self) -> None:
        """Validate total recipient count."""
        total = 1  # 'to' is required
        if self.cc:
            total += len(self.cc)
        if self.bcc:
            total += len(self.bcc)

        if total > MAX_TOTAL_RECIPIENTS:
            raise ValueError(f"Total recipients ({total}) exceeds limit of {MAX_TOTAL_RECIPIENTS}")


class GoogleAdapter:
    """Adapter for Google actions (Gmail)."""

    def __init__(self, rollout_gate=None):
        """Initialize Google adapter.

        Args:
            rollout_gate: Optional RolloutGate for gradual feature rollout
        """
        self.enabled = os.getenv("PROVIDER_GOOGLE_ENABLED", "false").lower() == "true"
        self.client_id = os.getenv("GOOGLE_CLIENT_ID")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        self.rollout_gate = rollout_gate

        # Internal-only configuration
        self.internal_only = os.getenv("GOOGLE_INTERNAL_ONLY", "true").lower() == "true"
        allowed_domains = os.getenv("GOOGLE_INTERNAL_ALLOWED_DOMAINS", "")
        self.internal_allowed_domains = [d.strip() for d in allowed_domains.split(",") if d.strip()]
        test_recipients = os.getenv("GOOGLE_INTERNAL_TEST_RECIPIENTS", "")
        self.internal_test_recipients = [e.strip() for e in test_recipients.split(",") if e.strip()]

    def _create_structured_error(
        self,
        error_code: str,
        message: str,
        field: Optional[str] = None,
        details: Optional[dict] = None,
        remediation: str = "",
        retriable: bool = False,
    ) -> dict:
        """Create structured error payload.

        Args:
            error_code: Error code from spec (e.g., validation_error_attachment_too_large)
            message: Human-readable message
            field: Field that failed (e.g., "attachments[0]")
            details: Additional context
            remediation: How to fix
            retriable: Whether the operation can be retried

        Returns:
            Structured error dict
        """
        # Record structured error metric
        from relay_ai.telemetry.prom import record_structured_error

        record_structured_error(provider="google", action="gmail.send", code=error_code, source="gmail.adapter")

        return {
            "error_code": error_code,
            "message": message,
            "field": field,
            "details": details or {},
            "remediation": remediation,
            "retriable": retriable,
            "correlation_id": str(uuid.uuid4()),
            "source": "gmail.adapter",
        }

    def _check_internal_only_recipients(self, to: str, cc: Optional[list[str]], bcc: Optional[list[str]]) -> None:
        """Check if all recipients are allowed under internal-only mode.

        Args:
            to: Primary recipient
            cc: CC recipients
            bcc: BCC recipients

        Raises:
            ValueError: If any recipient is not allowed
        """
        if not self.internal_only:
            return  # Not in internal-only mode

        all_recipients = [to]
        if cc:
            all_recipients.extend(cc)
        if bcc:
            all_recipients.extend(bcc)

        # Check test recipients bypass
        for recipient in all_recipients:
            if recipient in self.internal_test_recipients:
                continue  # Bypass for test recipient

            # Check domain allowlist
            domain_allowed = any(recipient.endswith(f"@{domain}") for domain in self.internal_allowed_domains)

            if not domain_allowed:
                error = self._create_structured_error(
                    error_code="internal_only_recipient_blocked",
                    message=f"Recipient '{recipient}' not allowed in internal-only mode",
                    field="recipients",
                    details={
                        "blocked_recipient": recipient,
                        "allowed_domains": self.internal_allowed_domains,
                        "test_recipients": self.internal_test_recipients,
                    },
                    remediation=f"Use recipient from allowed domains: {', '.join(self.internal_allowed_domains)}",
                    retriable=False,
                )
                raise ValueError(json.dumps(error))

    def list_actions(self) -> list[ActionDefinition]:
        """List available Google actions."""
        actions = [
            ActionDefinition(
                id="gmail.send",
                name="Send Gmail",
                description="Send an email via Gmail API",
                provider=Provider.GOOGLE,
                schema={
                    "type": "object",
                    "properties": {
                        "to": {
                            "type": "string",
                            "format": "email",
                            "description": "Recipient email address",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Email subject",
                        },
                        "text": {
                            "type": "string",
                            "description": "Email body (plain text)",
                        },
                        "html": {
                            "type": "string",
                            "description": "HTML body (optional, will be sanitized)",
                        },
                        "cc": {
                            "type": "array",
                            "items": {"type": "string", "format": "email"},
                            "description": "CC recipients",
                        },
                        "bcc": {
                            "type": "array",
                            "items": {"type": "string", "format": "email"},
                            "description": "BCC recipients",
                        },
                        "attachments": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "filename": {"type": "string"},
                                    "content_type": {"type": "string"},
                                    "data": {"type": "string", "description": "Base64-encoded"},
                                },
                                "required": ["filename", "content_type", "data"],
                            },
                            "description": "Attachments (max 10, 25MB each)",
                        },
                        "inline": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "cid": {"type": "string"},
                                    "filename": {"type": "string"},
                                    "content_type": {"type": "string"},
                                    "data": {"type": "string", "description": "Base64-encoded"},
                                },
                                "required": ["cid", "filename", "content_type", "data"],
                            },
                            "description": "Inline images (max 20, 5MB each)",
                        },
                    },
                    "required": ["to", "subject", "text"],
                },
                enabled=self.enabled,
            )
        ]

        return actions

    def preview(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """Preview a Google action.

        Validates parameters, builds MIME message, and returns digest.
        No network side effects.
        """
        if action == "gmail.send":
            return self._preview_gmail_send(params)

        raise ValueError(f"Unknown action: {action}")

    def _preview_gmail_send(self, params: dict[str, Any]) -> dict[str, Any]:
        """Preview gmail.send action."""
        # Validate with Pydantic
        try:
            validated = GmailSendParams(**params)
        except ValidationError as e:
            raise ValueError(f"Validation error: {e}") from e

        # Validate recipient count
        validated.validate_recipient_count()

        # Check internal-only recipients
        self._check_internal_only_recipients(validated.to, validated.cc, validated.bcc)

        # Build MIME message (returns tuple with sanitization summary)
        mime_message, sanitization_summary = self._build_mime_message(
            to=validated.to,
            subject=validated.subject,
            text=validated.text,
            html=validated.html,
            cc=validated.cc,
            bcc=validated.bcc,
            attachments=validated.attachments,
            inline=validated.inline,
        )

        # Base64URL encode (no padding)
        raw_message = base64.urlsafe_b64encode(mime_message.encode("utf-8"))
        raw_message = raw_message.rstrip(b"=")  # Remove padding

        # Compute digest (SHA256 of headers + subject + first 64 chars of body)
        digest_input = f"{validated.to}|{validated.subject}|{validated.text[:64]}"
        digest = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:16]

        # Build summary
        summary = f"Send email to {validated.to}\nSubject: {validated.subject}\nBody: {validated.text[:100]}..."
        if validated.cc:
            summary += f"\nCC: {', '.join(validated.cc)}"
        if validated.bcc:
            summary += f"\nBCC: {', '.join(validated.bcc)}"
        if validated.html:
            summary += "\nFormat: HTML + plain text"
        if validated.attachments:
            summary += f"\nAttachments: {len(validated.attachments)}"
        if validated.inline:
            summary += f"\nInline images: {len(validated.inline)}"

        warnings = []
        if not self.enabled:
            warnings.append("PROVIDER_GOOGLE_ENABLED is false - execution will fail")
        if not self.client_id or not self.client_secret:
            warnings.append("Google OAuth credentials not configured")

        result = {
            "summary": summary,
            "params": params,
            "warnings": warnings,
            "digest": digest,
            "raw_message_length": len(raw_message),
        }

        # Add sanitization summary if HTML was sanitized
        if sanitization_summary:
            result["sanitization_summary"] = sanitization_summary

            # Include sanitized HTML for preview
            if validated.html:
                from relay_ai.validation.html_sanitization import sanitize_html

                sanitized_html, _ = sanitize_html(validated.html)
                result["sanitized_html"] = sanitized_html

        return result

    def _build_mime_message(
        self,
        to: str,
        subject: str,
        text: str,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        html: Optional[str] = None,
        attachments: Optional[list[AttachmentInput]] = None,
        inline: Optional[list[InlineImageInput]] = None,
    ) -> tuple[str, Optional[dict]]:
        """Build RFC822 MIME message using MimeBuilder.

        Args:
            to: Recipient email
            subject: Email subject
            text: Plain text body
            cc: CC recipients
            bcc: BCC recipients
            html: HTML body (optional)
            attachments: Attachments (optional)
            inline: Inline images (optional)

        Returns:
            Tuple of (mime_message_string, sanitization_summary)
            sanitization_summary is None if no HTML provided

        Raises:
            ValueError: With structured error payload (JSON string)
        """
        # Convert input models to validation types
        import binascii

        from relay_ai.actions.adapters.google_mime import MimeBuilder
        from relay_ai.validation.attachments import Attachment, InlineImage

        attachments_validated = None
        if attachments:
            try:
                attachments_validated = [
                    Attachment(
                        filename=att.filename,
                        content_type=att.content_type,
                        data=base64.b64decode(att.data),
                    )
                    for att in attachments
                ]
            except (binascii.Error, ValueError) as e:
                error = self._create_structured_error(
                    error_code="validation_error_invalid_attachment_data",
                    message=f"Failed to decode attachment data: {str(e)}",
                    field="attachments",
                    details={"error": str(e)},
                    remediation="Ensure attachment data is valid base64",
                    retriable=False,
                )
                raise ValueError(json.dumps(error)) from e

        inline_validated = None
        if inline:
            try:
                inline_validated = [
                    InlineImage(
                        cid=img.cid,
                        filename=img.filename,
                        content_type=img.content_type,
                        data=base64.b64decode(img.data),
                    )
                    for img in inline
                ]
            except (binascii.Error, ValueError) as e:
                error = self._create_structured_error(
                    error_code="validation_error_invalid_inline_data",
                    message=f"Failed to decode inline image data: {str(e)}",
                    field="inline",
                    details={"error": str(e)},
                    remediation="Ensure inline image data is valid base64",
                    retriable=False,
                )
                raise ValueError(json.dumps(error)) from e

        # Build MIME message
        builder = MimeBuilder()

        try:
            mime_message = builder.build_message(
                to=to,
                subject=subject,
                text=text,
                html=html,
                cc=cc,
                bcc=bcc,
                attachments=attachments_validated,
                inline=inline_validated,
            )

            # Extract sanitization summary if HTML was provided
            sanitization_summary = None
            if html:
                from relay_ai.validation.html_sanitization import sanitize_html

                _, changes = sanitize_html(html)
                if any(count > 0 for count in changes.values()):
                    sanitization_summary = {
                        "sanitized": True,
                        "changes": changes,
                    }

            return mime_message, sanitization_summary

        except ValueError as e:
            # Parse validation error from MimeBuilder/validator
            error_msg = str(e)

            # Check if it's already a structured error
            if "validation_error_" in error_msg or "cid" in error_msg.lower():
                # Extract error code and details
                error_code = "validation_error_mime_build"
                if "validation_error_attachment_too_large" in error_msg:
                    error_code = "validation_error_attachment_too_large"
                elif "validation_error_blocked_mime_type" in error_msg:
                    error_code = "validation_error_blocked_mime_type"
                elif "validation_error_missing_inline_image" in error_msg:
                    error_code = "validation_error_missing_inline_image"
                elif "validation_error_cid_not_referenced" in error_msg:
                    error_code = "validation_error_cid_not_referenced"
                elif "validation_error_total_size_exceeded" in error_msg:
                    error_code = "validation_error_total_size_exceeded"

                error = self._create_structured_error(
                    error_code=error_code,
                    message=error_msg,
                    field="mime",
                    details={"original_error": error_msg},
                    remediation="Check validation requirements in error message",
                    retriable=False,
                )
                raise ValueError(json.dumps(error)) from e
            else:
                # Unknown error
                error = self._create_structured_error(
                    error_code="unknown_mime_error",
                    message=f"MIME build failed: {error_msg}",
                    field="mime",
                    details={"error": error_msg},
                    remediation="Contact support if issue persists",
                    retriable=False,
                )
                raise ValueError(json.dumps(error)) from e

    async def execute(self, action: str, params: dict[str, Any], workspace_id: str, actor_id: str) -> dict[str, Any]:
        """Execute a Google action.

        Args:
            action: Action ID (e.g., 'gmail.send')
            params: Validated parameters from preview
            workspace_id: Workspace UUID
            actor_id: Actor ID (user email or API key ID)

        Returns:
            Execution result with status and response data

        Raises:
            ValueError: If action is unknown or validation fails
            httpx.HTTPStatusError: If Gmail API returns error
        """
        if action == "gmail.send":
            return await self._execute_gmail_send(params, workspace_id, actor_id)

        raise ValueError(f"Unknown action: {action}")

    async def _execute_gmail_send(self, params: dict[str, Any], workspace_id: str, actor_id: str) -> dict[str, Any]:
        """Execute gmail.send action.

        Bounded error reasons:
        - provider_disabled: PROVIDER_GOOGLE_ENABLED=false
        - rollout_gated: Feature not rolled out to this user
        - oauth_token_missing: No tokens found for workspace
        - oauth_token_expired: Token refresh failed
        - gmail_4xx: Client error (400-499)
        - gmail_5xx: Server error (500-599)
        - validation_error: Invalid parameters
        """
        from relay_ai.telemetry.prom import record_action_error, record_action_execution

        start_time = time.perf_counter()

        # Guard: Check feature flag
        if not self.enabled:
            record_action_error(provider="google", action="gmail.send", reason="provider_disabled")
            raise ValueError("Google provider is disabled (PROVIDER_GOOGLE_ENABLED=false)")

        # Guard: Check rollout gate
        if self.rollout_gate is not None:
            context = {"actor_id": actor_id, "workspace_id": workspace_id}
            if not self.rollout_gate.allow("google", context):
                record_action_error(provider="google", action="gmail.send", reason="rollout_gated")
                raise ValueError("Gmail send not rolled out to this user (rollout gate)")

        # Validate parameters
        try:
            validated = GmailSendParams(**params)
        except ValidationError as e:
            record_action_error(provider="google", action="gmail.send", reason="validation_error")
            raise ValueError(f"Validation error: {e}") from e

        # Validate recipient count
        validated.validate_recipient_count()

        # Check internal-only recipients
        self._check_internal_only_recipients(validated.to, validated.cc, validated.bcc)

        # Fetch OAuth tokens (with auto-refresh)
        from relay_ai.auth.oauth.tokens import OAuthTokenCache

        token_cache = OAuthTokenCache()
        try:
            tokens = await token_cache.get_tokens_with_auto_refresh(
                provider="google", workspace_id=workspace_id, actor_id=actor_id
            )
        except Exception as e:
            record_action_error(provider="google", action="gmail.send", reason="oauth_token_missing")
            raise ValueError(f"OAuth token error: {e}") from e

        if not tokens:
            record_action_error(provider="google", action="gmail.send", reason="oauth_token_missing")
            raise ValueError("No OAuth tokens found for workspace")

        access_token = tokens.get("access_token")
        if not access_token:
            record_action_error(provider="google", action="gmail.send", reason="oauth_token_missing")
            raise ValueError("Access token missing from token cache")

        # Build MIME message with correlation_id for tracing
        correlation_id = str(uuid.uuid4())
        import logging

        logger = logging.getLogger(__name__)

        try:
            mime_message, _ = self._build_mime_message(
                to=validated.to,
                subject=validated.subject,
                text=validated.text,
                html=validated.html,
                cc=validated.cc,
                bcc=validated.bcc,
                attachments=validated.attachments,
                inline=validated.inline,
            )
        except ValueError as e:
            # Parse structured error from MIME builder
            try:
                error_payload = json.loads(str(e))
                # Override correlation_id with our tracking ID
                error_payload["correlation_id"] = correlation_id
            except json.JSONDecodeError:
                # Fallback for non-JSON errors
                error_payload = self._create_structured_error(
                    error_code="unknown_error",
                    message=str(e),
                    retriable=False,
                )
                error_payload["correlation_id"] = correlation_id

            # Record metrics
            record_action_error(provider="google", action="gmail.send", reason=error_payload["error_code"])
            duration = time.perf_counter() - start_time
            record_action_execution(provider="google", action="gmail.send", status="error", duration_seconds=duration)

            # Log for ops with correlation_id
            logger.error(
                f"Gmail send failed: {error_payload['error_code']}",
                extra={
                    "correlation_id": correlation_id,
                    "error_code": error_payload["error_code"],
                    "workspace_id": workspace_id,
                    "actor_id": actor_id,
                },
            )

            # Return structured error to caller
            raise ValueError(json.dumps(error_payload)) from e

        # Base64URL encode (no padding)
        raw_message = base64.urlsafe_b64encode(mime_message.encode("utf-8"))
        raw_message = raw_message.rstrip(b"=")  # Remove padding

        # Call Gmail API
        gmail_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        payload = {"raw": raw_message.decode("utf-8")}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(gmail_url, json=payload, headers=headers)

                # Handle errors
                if 400 <= response.status_code < 500:
                    error_detail = response.text[:200]
                    record_action_error(provider="google", action="gmail.send", reason="gmail_4xx")

                    # Record execution (failed)
                    duration = time.perf_counter() - start_time
                    record_action_execution(
                        provider="google", action="gmail.send", status="error", duration_seconds=duration
                    )

                    raise httpx.HTTPStatusError(
                        f"Gmail API client error {response.status_code}: {error_detail}",
                        request=response.request,
                        response=response,
                    )

                if 500 <= response.status_code < 600:
                    error_detail = response.text[:200]
                    record_action_error(provider="google", action="gmail.send", reason="gmail_5xx")

                    # Record execution (failed)
                    duration = time.perf_counter() - start_time
                    record_action_execution(
                        provider="google", action="gmail.send", status="error", duration_seconds=duration
                    )

                    raise httpx.HTTPStatusError(
                        f"Gmail API server error {response.status_code}: {error_detail}",
                        request=response.request,
                        response=response,
                    )

                # Success
                response_data = response.json()

                # Record metrics
                duration = time.perf_counter() - start_time
                record_action_execution(provider="google", action="gmail.send", status="ok", duration_seconds=duration)

                # Log success with correlation_id
                logger.info(
                    "Gmail sent successfully",
                    extra={
                        "correlation_id": correlation_id,
                        "message_id": response_data.get("id"),
                        "workspace_id": workspace_id,
                        "actor_id": actor_id,
                    },
                )

                # NOTE: correlation_id is NOT included in API response (only in logs)
                return {
                    "status": "sent",
                    "message_id": response_data.get("id"),
                    "thread_id": response_data.get("threadId"),
                    "to": validated.to,
                    "subject": validated.subject,
                }

        except httpx.TimeoutException as e:
            record_action_error(provider="google", action="gmail.send", reason="gmail_timeout")

            # Record execution (failed)
            duration = time.perf_counter() - start_time
            record_action_execution(provider="google", action="gmail.send", status="error", duration_seconds=duration)

            raise TimeoutError("Gmail API request timed out after 30s") from e

        except httpx.NetworkError as e:
            record_action_error(provider="google", action="gmail.send", reason="gmail_network_error")

            # Record execution (failed)
            duration = time.perf_counter() - start_time
            record_action_execution(provider="google", action="gmail.send", status="error", duration_seconds=duration)

            raise ConnectionError("Network error connecting to Gmail API") from e
