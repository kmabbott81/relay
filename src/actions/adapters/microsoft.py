"""Microsoft action adapter (Outlook Send via Graph API).

Sprint 55 Phase 1: Scaffold Microsoft Outlook integration with rich email parity.

This adapter provides outlook.send action with same capabilities as gmail.send:
- HTML + plain text (multipart)
- Attachments (regular files)
- Inline images (referenced via contentId in HTML)
- Internal-only mode with domain allowlist
- Rollout gate integration
- Telemetry: action_exec_total, action_error_total, action_latency_seconds

Graph API Constraints:
- Max 150 recipients (to + cc + bcc combined)
- Max 4 MB total message size
- Max 20 attachments per message
- API endpoint: POST https://graph.microsoft.com/v1.0/me/sendMail
"""

import asyncio
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

# Microsoft Graph API recipient limits
MAX_TOTAL_RECIPIENTS = 150  # Microsoft limit (different from Gmail's 100)

# Microsoft Graph API size limits
MAX_MESSAGE_SIZE = 4 * 1024 * 1024  # 4 MB (includes attachments + body)
MAX_ATTACHMENTS = 20  # Maximum number of attachments per message


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


class OutlookSendParams(BaseModel):
    """Parameters for outlook.send action."""

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
        """Validate total recipient count (Microsoft limit: 150)."""
        total = 1  # 'to' is required
        if self.cc:
            total += len(self.cc)
        if self.bcc:
            total += len(self.bcc)

        if total > MAX_TOTAL_RECIPIENTS:
            raise ValueError(f"Total recipients ({total}) exceeds Microsoft limit of {MAX_TOTAL_RECIPIENTS}")


class MicrosoftAdapter:
    """Adapter for Microsoft actions (Outlook via Graph API)."""

    def __init__(self, rollout_gate=None):
        """Initialize Microsoft adapter.

        Args:
            rollout_gate: Optional RolloutGate for gradual feature rollout
        """
        self.enabled = os.getenv("PROVIDER_MICROSOFT_ENABLED", "false").lower() == "true"
        self.client_id = os.getenv("MS_CLIENT_ID")
        self.client_secret = os.getenv("MS_CLIENT_SECRET")
        self.tenant_id = os.getenv("MS_TENANT_ID", "common")
        self.rollout_gate = rollout_gate

        # Internal-only configuration (same pattern as Google)
        self.internal_only = os.getenv("MICROSOFT_INTERNAL_ONLY", "true").lower() == "true"
        allowed_domains = os.getenv("MICROSOFT_INTERNAL_ALLOWED_DOMAINS", "")
        self.internal_allowed_domains = [d.strip() for d in allowed_domains.split(",") if d.strip()]
        test_recipients = os.getenv("MICROSOFT_INTERNAL_TEST_RECIPIENTS", "")
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

        record_structured_error(provider="microsoft", action="outlook.send", code=error_code, source="outlook.adapter")

        return {
            "error_code": error_code,
            "message": message,
            "field": field,
            "details": details or {},
            "remediation": remediation,
            "retriable": retriable,
            "correlation_id": str(uuid.uuid4()),
            "source": "outlook.adapter",
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
        """List available Microsoft actions."""
        actions = [
            ActionDefinition(
                id="outlook.send",
                name="Send Outlook Email",
                description="Send an email via Microsoft Graph API (Outlook)",
                provider=Provider.MICROSOFT,
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
                            "description": f"Attachments (max {MAX_ATTACHMENTS}, 4MB total)",
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
                            "description": "Inline images with contentId for HTML reference",
                        },
                    },
                    "required": ["to", "subject", "text"],
                },
                enabled=self.enabled,
            )
        ]

        return actions

    def preview(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """Preview a Microsoft action.

        Validates parameters and returns summary. No network side effects.

        Args:
            action: Action ID (e.g., 'outlook.send')
            params: Action parameters

        Returns:
            Preview result with summary, warnings, digest

        Raises:
            ValueError: If action unknown or validation fails
        """
        if action == "outlook.send":
            return self._preview_outlook_send(params)

        raise ValueError(f"Unknown action: {action}")

    def _preview_outlook_send(self, params: dict[str, Any]) -> dict[str, Any]:
        """Preview outlook.send action.

        Validates parameters, checks internal-only recipients, computes digest.
        Does not build MIME (Microsoft uses JSON payload, not MIME).
        """
        # Validate with Pydantic
        try:
            validated = OutlookSendParams(**params)
        except ValidationError as e:
            raise ValueError(f"Validation error: {e}") from e

        # Validate recipient count (Microsoft limit: 150)
        validated.validate_recipient_count()

        # Check internal-only recipients
        self._check_internal_only_recipients(validated.to, validated.cc, validated.bcc)

        # Check for large attachments (>3MB) - Sprint 55 Week 2 stub
        import base64
        import binascii

        from relay_ai.actions.adapters.microsoft_graph import should_use_upload_session
        from relay_ai.validation.attachments import Attachment, InlineImage

        attachments = None
        if validated.attachments:
            try:
                attachments = [
                    Attachment(
                        filename=att.filename,
                        content_type=att.content_type,
                        data=base64.b64decode(att.data),
                    )
                    for att in validated.attachments
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

        inline = None
        if validated.inline:
            try:
                inline = [
                    InlineImage(
                        cid=img.cid,
                        filename=img.filename,
                        content_type=img.content_type,
                        data=base64.b64decode(img.data),
                    )
                    for img in validated.inline
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

        # Check if upload session is needed (>3MB attachments)
        if should_use_upload_session(attachments, inline):
            upload_sessions_enabled = os.getenv("MS_UPLOAD_SESSIONS_ENABLED", "false").lower() == "true"

            if not upload_sessions_enabled:
                # Stub for Week 3: Large attachment upload sessions not yet implemented
                error = self._create_structured_error(
                    error_code="provider_payload_too_large",
                    message="Attachments exceed 3MB - upload sessions required but not enabled",
                    field="attachments",
                    details={
                        "total_size_estimate_mb": round(
                            sum(len(att.data) for att in (attachments or [])) / (1024 * 1024), 2
                        )
                        + round(sum(len(img.data) for img in (inline or [])) / (1024 * 1024), 2),
                        "threshold_mb": 3,
                        "feature": "upload_sessions",
                        "status": "not_implemented",
                    },
                    remediation="Reduce attachment size to <3MB or enable MS_UPLOAD_SESSIONS_ENABLED=true (Week 3 feature)",
                    retriable=False,
                )
                raise ValueError(json.dumps(error))

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
            warnings.append("PROVIDER_MICROSOFT_ENABLED is false - execution will fail")
        if not self.client_id:
            warnings.append("Microsoft OAuth credentials not configured (MS_CLIENT_ID missing)")

        return {
            "summary": summary,
            "params": params,
            "warnings": warnings,
            "digest": digest,
        }

    async def execute(self, action: str, params: dict[str, Any], workspace_id: str, actor_id: str) -> dict[str, Any]:
        """Execute a Microsoft action.

        Args:
            action: Action ID (e.g., 'outlook.send')
            params: Validated parameters from preview
            workspace_id: Workspace UUID
            actor_id: Actor ID (user email or API key ID)

        Returns:
            Execution result with status and response data

        Raises:
            ValueError: If action is unknown or validation fails
            httpx.HTTPStatusError: If Graph API returns error

        Bounded error reasons:
        - provider_disabled: PROVIDER_MICROSOFT_ENABLED=false
        - rollout_gated: Feature not rolled out to this user
        - oauth_token_missing: No tokens found for workspace
        - oauth_token_expired: Token refresh failed
        - graph_4xx: Client error (400-499)
        - graph_5xx: Server error (500-599)
        - validation_error: Invalid parameters
        """
        if action == "outlook.send":
            return await self._execute_outlook_send(params, workspace_id, actor_id)

        raise ValueError(f"Unknown action: {action}")

    async def _execute_outlook_send(self, params: dict[str, Any], workspace_id: str, actor_id: str) -> dict[str, Any]:
        """Execute outlook.send action with full Graph API integration.

        Sprint 55 Week 2: Real implementation with:
        - OAuth token fetch with auto-refresh
        - Graph API JSON payload construction
        - Graph API sendMail call with retry logic
        - Error handling and telemetry
        """
        import random

        from relay_ai.telemetry.prom import record_action_error, record_action_execution

        start_time = time.perf_counter()

        # Guard: Check feature flag
        if not self.enabled:
            record_action_error(provider="microsoft", action="outlook.send", reason="provider_disabled")
            raise ValueError("Microsoft provider is disabled (PROVIDER_MICROSOFT_ENABLED=false)")

        # Guard: Check rollout gate
        if self.rollout_gate is not None:
            context = {"actor_id": actor_id, "workspace_id": workspace_id}
            if not self.rollout_gate.allow("microsoft", context):
                record_action_error(provider="microsoft", action="outlook.send", reason="rollout_gated")
                raise ValueError("Outlook send not rolled out to this user (rollout gate)")

        # Validate parameters
        try:
            validated = OutlookSendParams(**params)
        except ValidationError as e:
            record_action_error(provider="microsoft", action="outlook.send", reason="validation_error")
            raise ValueError(f"Validation error: {e}") from e

        # Validate recipient count
        validated.validate_recipient_count()

        # Check internal-only recipients
        self._check_internal_only_recipients(validated.to, validated.cc, validated.bcc)

        # Convert parameters to attachment/inline objects (needed for size check)
        import base64
        import binascii

        from relay_ai.actions.adapters.microsoft_graph import should_use_upload_session
        from relay_ai.validation.attachments import Attachment, InlineImage

        attachments = None
        if validated.attachments:
            try:
                attachments = [
                    Attachment(
                        filename=att.filename,
                        content_type=att.content_type,
                        data=base64.b64decode(att.data),
                    )
                    for att in validated.attachments
                ]
            except (binascii.Error, ValueError) as e:
                record_action_error(
                    provider="microsoft", action="outlook.send", reason="validation_error_invalid_base64"
                )
                error = self._create_structured_error(
                    error_code="validation_error_invalid_attachment_data",
                    message=f"Failed to decode attachment data: {str(e)}",
                    field="attachments",
                    details={"error": str(e)},
                    remediation="Ensure attachment data is valid base64",
                    retriable=False,
                )
                raise ValueError(json.dumps(error)) from e

        inline = None
        if validated.inline:
            try:
                inline = [
                    InlineImage(
                        cid=img.cid,
                        filename=img.filename,
                        content_type=img.content_type,
                        data=base64.b64decode(img.data),
                    )
                    for img in validated.inline
                ]
            except (binascii.Error, ValueError) as e:
                record_action_error(
                    provider="microsoft", action="outlook.send", reason="validation_error_invalid_base64"
                )
                error = self._create_structured_error(
                    error_code="validation_error_invalid_inline_data",
                    message=f"Failed to decode inline image data: {str(e)}",
                    field="inline",
                    details={"error": str(e)},
                    remediation="Ensure inline image data is valid base64",
                    retriable=False,
                )
                raise ValueError(json.dumps(error)) from e

        # Get OAuth tokens with auto-refresh (needed for both paths)
        from relay_ai.auth.oauth.ms_tokens import get_tokens

        tokens = await get_tokens(workspace_id, actor_id)
        if not tokens:
            record_action_error(provider="microsoft", action="outlook.send", reason="oauth_token_missing")
            raise ValueError(f"No Microsoft OAuth tokens found for workspace={workspace_id}, actor={actor_id}")

        access_token = tokens.get("access_token")
        if not access_token:
            record_action_error(provider="microsoft", action="outlook.send", reason="oauth_token_invalid")
            raise ValueError("OAuth token missing access_token")

        # Check for large attachments (>3MB) - Sprint 55 Week 3: Upload sessions
        if should_use_upload_session(attachments, inline):
            upload_sessions_enabled = os.getenv("MS_UPLOAD_SESSIONS_ENABLED", "false").lower() == "true"

            if not upload_sessions_enabled:
                # Feature flag not enabled
                record_action_error(provider="microsoft", action="outlook.send", reason="provider_payload_too_large")
                error = self._create_structured_error(
                    error_code="provider_payload_too_large",
                    message="Attachments exceed 3MB - upload sessions required but not enabled",
                    field="attachments",
                    details={
                        "total_size_estimate_mb": round(
                            sum(len(att.data) for att in (attachments or [])) / (1024 * 1024), 2
                        )
                        + round(sum(len(img.data) for img in (inline or [])) / (1024 * 1024), 2),
                        "threshold_mb": 3,
                        "feature": "upload_sessions",
                        "status": "disabled",
                    },
                    remediation="Reduce attachment size to <3MB or enable MS_UPLOAD_SESSIONS_ENABLED=true",
                    retriable=False,
                )
                raise ValueError(json.dumps(error))

            # Sprint 55 Week 3: Use draft + upload session flow for large attachments
            return await self._execute_outlook_send_with_upload_session(
                validated, attachments, inline, access_token, workspace_id, actor_id, start_time
            )

        # Build Graph API JSON payload
        from relay_ai.actions.adapters.microsoft_graph import GraphMessageBuilder

        builder = GraphMessageBuilder()

        # Note: attachments and inline already converted above for size check

        try:
            payload = builder.build_message(
                to=validated.to,
                subject=validated.subject,
                text=validated.text,
                html=validated.html,
                cc=validated.cc,
                bcc=validated.bcc,
                attachments=attachments,
                inline=inline,
            )
        except ValueError as e:
            record_action_error(provider="microsoft", action="outlook.send", reason="graph_payload_build_error")
            raise ValueError(f"Failed to build Graph payload: {e}") from e

        # Call Graph API sendMail with retry logic
        graph_url = "https://graph.microsoft.com/v1.0/me/sendMail"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        # Exponential backoff retry parameters
        max_retries = 3
        base_delay = 1.0  # seconds

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(graph_url, json=payload, headers=headers)

                    if response.status_code == 202:
                        # Success: Microsoft Graph sendMail returns 202 Accepted
                        duration = time.perf_counter() - start_time
                        record_action_execution(
                            provider="microsoft",
                            action="outlook.send",
                            status="ok",
                            duration_seconds=duration,
                        )

                        return {
                            "status": "sent",
                            "message": "Email sent successfully via Microsoft Graph API",
                            "to": validated.to,
                            "subject": validated.subject,
                            "provider": "microsoft",
                            "http_status": 202,
                        }

                    elif response.status_code == 429:
                        # Rate limiting - parse Retry-After header
                        from relay_ai.actions.adapters.microsoft_errors import parse_retry_after

                        retry_after = parse_retry_after(response.headers.get("Retry-After"))

                        # Record throttling error
                        record_action_error(provider="microsoft", action="outlook.send", reason="throttled_429")

                        if attempt < max_retries:
                            # Add jitter to retry delay (±20%)
                            jitter = random.uniform(0.8, 1.2)
                            delay = retry_after * jitter
                            await asyncio.sleep(delay)
                            continue  # Retry
                        else:
                            # Max retries exceeded
                            from relay_ai.actions.adapters.microsoft_errors import (
                                map_graph_error_to_structured_code,
                            )

                            error = map_graph_error_to_structured_code(
                                429, response.json() if response.content else None
                            )
                            duration = time.perf_counter() - start_time
                            record_action_execution(
                                provider="microsoft",
                                action="outlook.send",
                                status="error",
                                duration_seconds=duration,
                            )
                            raise ValueError(json.dumps(error))

                    else:
                        # Other error (4xx, 5xx)
                        from relay_ai.actions.adapters.microsoft_errors import (
                            map_graph_error_to_structured_code,
                        )

                        error = map_graph_error_to_structured_code(
                            response.status_code, response.json() if response.content else None
                        )

                        # Check if retriable (5xx errors)
                        if error.get("retriable") and attempt < max_retries:
                            # Exponential backoff with jitter
                            delay = (base_delay * (2**attempt)) * random.uniform(0.8, 1.2)
                            await asyncio.sleep(delay)

                            record_action_error(
                                provider="microsoft",
                                action="outlook.send",
                                reason=f"graph_{response.status_code}_retry",
                            )
                            continue  # Retry
                        else:
                            # Non-retriable error or max retries exceeded
                            record_action_error(
                                provider="microsoft",
                                action="outlook.send",
                                reason=f"graph_{response.status_code}",
                            )

                            duration = time.perf_counter() - start_time
                            record_action_execution(
                                provider="microsoft",
                                action="outlook.send",
                                status="error",
                                duration_seconds=duration,
                            )
                            raise ValueError(json.dumps(error))

            except httpx.TimeoutException as e:
                last_error = e
                record_action_error(provider="microsoft", action="outlook.send", reason="graph_timeout")

                if attempt < max_retries:
                    # Exponential backoff with jitter
                    delay = (base_delay * (2**attempt)) * random.uniform(0.8, 1.2)
                    await asyncio.sleep(delay)
                    continue  # Retry
                else:
                    # Max retries exceeded
                    duration = time.perf_counter() - start_time
                    record_action_execution(
                        provider="microsoft",
                        action="outlook.send",
                        status="error",
                        duration_seconds=duration,
                    )
                    raise ValueError(f"Microsoft Graph API timeout after {max_retries} retries: {e}") from e

            except httpx.RequestError as e:
                last_error = e
                record_action_error(provider="microsoft", action="outlook.send", reason="graph_request_error")

                if attempt < max_retries:
                    # Exponential backoff with jitter
                    delay = (base_delay * (2**attempt)) * random.uniform(0.8, 1.2)
                    await asyncio.sleep(delay)
                    continue  # Retry
                else:
                    # Max retries exceeded
                    duration = time.perf_counter() - start_time
                    record_action_execution(
                        provider="microsoft",
                        action="outlook.send",
                        status="error",
                        duration_seconds=duration,
                    )
                    raise ValueError(f"Microsoft Graph API request error after {max_retries} retries: {e}") from e

        # Should never reach here (loop always returns or raises)
        if last_error:
            raise ValueError(f"Unexpected error in retry loop: {last_error}")
        raise ValueError("Unexpected: retry loop exited without result")

    async def _execute_outlook_send_with_upload_session(
        self,
        validated: OutlookSendParams,
        attachments: Optional[list],  # list[Attachment]
        inline: Optional[list],  # list[InlineImage]
        access_token: str,
        workspace_id: str,
        actor_id: str,
        start_time: float,
    ) -> dict[str, Any]:
        """Execute outlook.send using draft + upload session flow for large attachments.

        Sprint 55 Week 3: Upload session flow for attachments >3 MB.

        Flow:
        1. Create draft message (without attachments)
        2. For each attachment (regular + inline), create upload session and upload chunks
        3. Send draft message

        Args:
            validated: Validated parameters
            attachments: Regular attachments (already decoded)
            inline: Inline images (already decoded)
            access_token: OAuth access token
            workspace_id: Workspace UUID
            actor_id: Actor ID
            start_time: Request start time

        Returns:
            Execution result with status and response data

        Raises:
            ValueError: If upload session fails
        """
        from relay_ai.actions.adapters.microsoft_upload import (
            UploadChunkError,
            UploadFinalizeError,
            UploadSessionCreateError,
            UploadSessionError,
            create_draft,
            create_upload_session,
            put_chunks,
            send_draft,
        )
        from relay_ai.telemetry.prom import record_action_error, record_action_execution

        try:
            # Step 1: Build message without attachments (draft)
            from relay_ai.actions.adapters.microsoft_graph import GraphMessageBuilder

            builder = GraphMessageBuilder()
            draft_payload = builder.build_message(
                to=validated.to,
                subject=validated.subject,
                text=validated.text,
                html=validated.html,
                cc=validated.cc,
                bcc=validated.bcc,
                attachments=None,  # No attachments in draft
                inline=None,  # No inline in draft
            )

            # Extract message portion (create_draft needs message only, not sendMail wrapper)
            draft_message = draft_payload["message"]

            # Step 2: Create draft
            message_id, internet_message_id = await create_draft(access_token, draft_message)

            # Step 3: Upload attachments via upload sessions
            # Upload regular attachments
            if attachments:
                for att in attachments:
                    attachment_meta = {
                        "attachmentType": "file",
                        "name": att.filename,
                        "size": len(att.data),
                        "contentType": att.content_type,
                    }

                    upload_url = await create_upload_session(access_token, message_id, attachment_meta)
                    await put_chunks(upload_url, att.data)

            # Upload inline images
            if inline:
                for img in inline:
                    attachment_meta = {
                        "attachmentType": "file",
                        "name": img.filename,
                        "size": len(img.data),
                        "contentType": img.content_type,
                        "isInline": True,
                        "contentId": img.cid,  # CID for inline reference
                    }

                    upload_url = await create_upload_session(access_token, message_id, attachment_meta)
                    await put_chunks(upload_url, img.data)

            # Step 4: Send draft
            await send_draft(access_token, message_id)

            # Success
            duration = time.perf_counter() - start_time
            record_action_execution(
                provider="microsoft",
                action="outlook.send",
                status="ok",
                duration_seconds=duration,
            )

            return {
                "status": "sent",
                "message": "Email sent successfully via Microsoft Graph API (upload session)",
                "to": validated.to,
                "subject": validated.subject,
                "provider": "microsoft",
                "draft_id": message_id,
                "internet_message_id": internet_message_id,
                "upload_session_used": True,
            }

        except UploadSessionCreateError as e:
            # Failed to create draft or upload session
            record_action_error(provider="microsoft", action="outlook.send", reason="upload_session_create_error")
            error = self._create_structured_error(
                error_code="provider_upload_session_create_failed",
                message=f"Failed to create upload session: {str(e)}",
                field="attachments",
                details={"error": str(e)},
                remediation="Check attachment sizes and Graph API permissions. Retry may succeed.",
                retriable=True,
            )
            duration = time.perf_counter() - start_time
            record_action_execution(
                provider="microsoft",
                action="outlook.send",
                status="error",
                duration_seconds=duration,
            )
            raise ValueError(json.dumps(error)) from e

        except UploadChunkError as e:
            # Failed to upload chunk
            record_action_error(provider="microsoft", action="outlook.send", reason="upload_chunk_error")
            error = self._create_structured_error(
                error_code="provider_upload_chunk_failed",
                message=f"Failed to upload attachment chunk: {str(e)}",
                field="attachments",
                details={"error": str(e)},
                remediation="Check network stability and attachment sizes. Retry may succeed.",
                retriable=True,
            )
            duration = time.perf_counter() - start_time
            record_action_execution(
                provider="microsoft",
                action="outlook.send",
                status="error",
                duration_seconds=duration,
            )
            raise ValueError(json.dumps(error)) from e

        except UploadFinalizeError as e:
            # Failed to send draft
            record_action_error(provider="microsoft", action="outlook.send", reason="upload_finalize_error")
            error = self._create_structured_error(
                error_code="provider_upload_finalize_failed",
                message=f"Failed to send draft after uploading attachments: {str(e)}",
                field="attachments",
                details={"error": str(e), "draft_id": message_id if "message_id" in locals() else None},
                remediation="Attachments uploaded but send failed. Draft may exist in mailbox. Retry may succeed.",
                retriable=True,
            )
            duration = time.perf_counter() - start_time
            record_action_execution(
                provider="microsoft",
                action="outlook.send",
                status="error",
                duration_seconds=duration,
            )
            raise ValueError(json.dumps(error)) from e

        except UploadSessionError as e:
            # Generic upload session error
            record_action_error(provider="microsoft", action="outlook.send", reason="upload_session_error")
            error = self._create_structured_error(
                error_code="provider_upload_session_failed",
                message=f"Upload session error: {str(e)}",
                field="attachments",
                details={"error": str(e)},
                remediation="Check attachment sizes and Graph API status. Retry may succeed.",
                retriable=True,
            )
            duration = time.perf_counter() - start_time
            record_action_execution(
                provider="microsoft",
                action="outlook.send",
                status="error",
                duration_seconds=duration,
            )
            raise ValueError(json.dumps(error)) from e


def is_configured() -> bool:
    """Check if Microsoft provider is properly configured.

    Returns:
        True if MS_CLIENT_ID is set, False otherwise
    """
    return bool(os.getenv("MS_CLIENT_ID"))
