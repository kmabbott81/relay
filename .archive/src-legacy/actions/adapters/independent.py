"""Independent action adapter (Webhook).

Sprint 49 Phase B: Webhook action with optional HMAC signing.
"""

import hashlib
import hmac
import json
import os
from typing import Any

import httpx

from ..contracts import ActionDefinition, Provider


class IndependentAdapter:
    """Adapter for independent actions (Webhook, SMTP stub)."""

    def __init__(self):
        """Initialize independent adapter."""
        self.webhook_url = os.getenv("WEBHOOK_URL")
        self.signing_secret = os.getenv("ACTIONS_SIGNING_SECRET")

    def list_actions(self) -> list[ActionDefinition]:
        """List available independent actions."""
        actions = [
            ActionDefinition(
                id="webhook.save",
                name="Send Webhook",
                description="Send data to a webhook endpoint",
                provider=Provider.INDEPENDENT,
                schema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "format": "uri",
                            "description": "Webhook URL",
                        },
                        "payload": {
                            "type": "object",
                            "description": "JSON payload to send",
                        },
                        "method": {
                            "type": "string",
                            "enum": ["POST", "PUT", "PATCH"],
                            "default": "POST",
                            "description": "HTTP method",
                        },
                    },
                    "required": ["url", "payload"],
                },
                enabled=bool(self.webhook_url),
            )
        ]

        return actions

    def preview(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """Preview an independent action."""
        if action == "webhook.save":
            url = params.get("url", self.webhook_url)
            payload = params.get("payload", {})
            method = params.get("method", "POST")

            summary = f"Send {method} request to {url} with payload: {json.dumps(payload, indent=2)[:100]}..."
            warnings = []

            if not self.webhook_url and not url:
                warnings.append("WEBHOOK_URL not configured")

            if self.signing_secret:
                summary += "\n\nRequest will be signed with X-Signature header."

            return {
                "summary": summary,
                "params": params,
                "warnings": warnings,
            }

        raise ValueError(f"Unknown action: {action}")

    async def execute(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute an independent action."""
        if action == "webhook.save":
            return await self._execute_webhook(params)

        raise ValueError(f"Unknown action: {action}")

    async def _execute_webhook(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute webhook action with optional HMAC signing."""
        url = params.get("url", self.webhook_url)
        payload = params.get("payload", {})
        method = params.get("method", "POST")

        if not url:
            raise ValueError("Webhook URL not configured (set WEBHOOK_URL)")

        # Serialize payload
        body = json.dumps(payload)

        # Prepare headers
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Relay-Actions/1.0",
        }

        # Add HMAC signature if secret is configured
        if self.signing_secret:
            signature = self._compute_signature(body)
            headers["X-Signature"] = f"sha256={signature}"

        # Send request with improved error handling
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    content=body,
                    headers=headers,
                )

                # Check response status
                if response.status_code >= 400:
                    error_body = response.text[:200]

                    raise httpx.HTTPStatusError(
                        f"Webhook returned {response.status_code}: {error_body}",
                        request=response.request,
                        response=response,
                    )

                return {
                    "status_code": response.status_code,
                    "response_body": response.text[:500],  # Truncate
                    "url": url,
                    "method": method,
                }

        except httpx.TimeoutException as e:
            raise TimeoutError(f"Webhook request timed out after 10s: {url}") from e
        except httpx.NetworkError as e:
            raise ConnectionError(f"Network error connecting to webhook: {url}") from e
        except httpx.HTTPStatusError:
            # Re-raise with our enhanced message
            raise

    def _compute_signature(self, body: str) -> str:
        """Compute HMAC-SHA256 signature for request body."""
        if not self.signing_secret:
            return ""

        signature = hmac.new(
            key=self.signing_secret.encode("utf-8"),
            msg=body.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        return signature
