"""Slack connector using Slack Web API.

Supports DRY_RUN (mock) and LIVE (real API) modes.
Handles channels, messages, and users via Slack Web API.
"""

import json
import os
import time
from pathlib import Path
from typing import Optional

from .base import Connector
from .circuit import CircuitBreaker
from .http_client import request
from .http_mock import get_mock_transport, is_mock_enabled
from .metrics import record_call
from .oauth2 import load_token, needs_refresh
from .retry import compute_backoff_ms


class SlackAPIError(Exception):
    """Non-retryable Slack API error."""

    pass


class SlackConnector(Connector):
    """Slack connector with OAuth2, retry, circuit breaker, metrics."""

    def __init__(self, connector_id: str, tenant_id: str, user_id: str):
        """Initialize Slack connector.

        Args:
            connector_id: Connector identifier
            tenant_id: Tenant for isolation
            user_id: User for RBAC
        """
        super().__init__(connector_id, tenant_id, user_id)

        # Mode
        self.live_mode = os.getenv("LIVE", "false").lower() == "true"
        self.dry_run = os.getenv("DRY_RUN", "true").lower() == "true"

        # If LIVE=true, DRY_RUN is forced to false
        if self.live_mode:
            self.dry_run = False

        # Slack API config
        self.base_url = os.getenv("SLACK_BASE_URL", "https://slack.com/api")
        self.bot_token = os.getenv("SLACK_BOT_TOKEN", "")

        # Defaults
        self.default_channel_id = os.getenv("SLACK_DEFAULT_CHANNEL_ID", "")

        # Observability
        self.circuit = CircuitBreaker(connector_id)
        self.max_retries = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))

        # Retry configuration
        self.retry_status_codes = self._parse_retry_statuses()

        # Mock data path
        self.mock_path = Path("logs/connectors/slack_mock.jsonl")

        # Token service ID (supports multi-tenant)
        self.token_service_id = f"slack:{self.tenant_id}"

    def _parse_retry_statuses(self) -> set[int]:
        """Parse SLACK_RETRY_STATUS env var into set of status codes.

        Returns:
            Set of HTTP status codes that should trigger retry
        """
        retry_str = os.getenv("SLACK_RETRY_STATUS", "429,500,502,503,504")
        try:
            return {int(code.strip()) for code in retry_str.split(",")}
        except ValueError:
            # Default retry codes
            return {429, 500, 502, 503, 504}

    def _get_token(self) -> str:
        """Get OAuth2 access token.

        Returns:
            Bot token

        Raises:
            Exception if token not available or refresh fails
        """
        # For Slack, we can use bot token directly or OAuth2 token
        if self.bot_token:
            return self.bot_token

        token = load_token(self.connector_id, self.token_service_id)

        if not token:
            raise Exception("No Slack token found. Set SLACK_BOT_TOKEN or run OAuth2 setup.")

        if needs_refresh(token):
            # TODO: Implement refresh_token() in oauth2.py for Slack
            raise Exception("Token expired. Refresh not yet implemented.")

        return token["access_token"]

    def _call_api(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        """Call Slack Web API with retry/circuit breaker/metrics.

        Args:
            method: HTTP method
            endpoint: API endpoint (e.g., conversations.list)
            json_data: Request body for POST
            params: Query parameters for GET

        Returns:
            Response body

        Raises:
            Exception on failure after retries
        """
        # Check if using mock transport
        use_mock = is_mock_enabled() or self.dry_run

        if use_mock and not is_mock_enabled():
            # Legacy dry_run behavior (JSONL-based mocks)
            return self._mock_response(method, endpoint, json_data)

        # Check circuit breaker
        if not self.circuit.allow():
            raise Exception(f"Circuit breaker open for {self.connector_id}")

        url = f"{self.base_url}/{endpoint}"

        # Add query params to URL if present
        if params:
            from urllib.parse import urlencode

            query_string = urlencode(params)
            url = f"{url}?{query_string}"

        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}

        last_error = None
        for attempt in range(self.max_retries):
            start_time = time.time()

            try:
                # Use mock transport if enabled
                if use_mock:
                    mock = get_mock_transport()
                    response = mock.request(method, url, headers=headers, json_data=json_data)
                else:
                    response = request(method, url, headers=headers, json_data=json_data)

                duration_ms = (time.time() - start_time) * 1000

                # Check status
                if 200 <= response["status_code"] < 300:
                    # Slack API wraps responses with {ok: true/false}
                    body = response["body"]

                    if isinstance(body, dict) and body.get("ok") is False:
                        # Slack API error
                        error_msg = body.get("error", "unknown_error")

                        # Handle rate limiting
                        if error_msg == "rate_limited":
                            self.circuit.record_failure()
                            record_call(
                                self.connector_id,
                                endpoint,
                                "error",
                                duration_ms,
                                error=f"Rate limited: {error_msg}",
                            )

                            if attempt < self.max_retries - 1:
                                # Use Retry-After header if present
                                retry_after = response.get("headers", {}).get("Retry-After", "1")
                                backoff_ms = max(compute_backoff_ms(attempt), int(retry_after) * 1000)
                                time.sleep(backoff_ms / 1000.0)
                                continue

                        # Other Slack API errors (non-retryable)
                        self.circuit.record_failure()
                        record_call(
                            self.connector_id,
                            endpoint,
                            "error",
                            duration_ms,
                            error=f"Slack API error: {error_msg}",
                        )
                        raise SlackAPIError(f"Slack API error: {error_msg}")

                    # Success
                    self.circuit.record_success()
                    record_call(
                        self.connector_id,
                        endpoint,
                        "success",
                        duration_ms,
                    )
                    return body

                elif response["status_code"] in self.retry_status_codes:
                    # Retryable HTTP error (429, 5xx, etc.)
                    self.circuit.record_failure()
                    error_type = "rate_limited" if response["status_code"] == 429 else "server_error"
                    record_call(
                        self.connector_id,
                        endpoint,
                        "error",
                        duration_ms,
                        error=f"{error_type}: {response['status_code']}",
                    )

                    if attempt < self.max_retries - 1:
                        # Use Retry-After header if present for 429
                        if response["status_code"] == 429:
                            retry_after = response.get("headers", {}).get("Retry-After", "1")
                            try:
                                retry_after_ms = int(retry_after) * 1000
                            except (ValueError, TypeError):
                                retry_after_ms = compute_backoff_ms(attempt)
                            backoff_ms = max(compute_backoff_ms(attempt), retry_after_ms)
                        else:
                            backoff_ms = compute_backoff_ms(attempt)

                        time.sleep(backoff_ms / 1000.0)
                        continue

                else:
                    # Client error - don't retry (non-retryable)
                    self.circuit.record_failure()
                    record_call(
                        self.connector_id,
                        endpoint,
                        "error",
                        duration_ms,
                        error=f"Client error: {response['status_code']}",
                    )
                    raise SlackAPIError(f"API error {response['status_code']}: {response.get('body')}")

            except SlackAPIError:
                # Non-retryable error - re-raise immediately
                raise

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                self.circuit.record_failure()
                record_call(
                    self.connector_id,
                    endpoint,
                    "error",
                    duration_ms,
                    error=str(e),
                )
                last_error = e

                if attempt < self.max_retries - 1:
                    backoff_ms = compute_backoff_ms(attempt)
                    time.sleep(backoff_ms / 1000.0)
                    continue

        raise last_error or Exception("Max retries exceeded")

    def _mock_response(self, method: str, endpoint: str, json_data: Optional[dict]) -> dict:
        """Generate mock response from local JSONL.

        Args:
            method: HTTP method
            endpoint: API endpoint
            json_data: Request body

        Returns:
            Mock response body
        """
        # Record mock call
        record_call(self.connector_id, endpoint, "success", 10.0)

        # Check if mock file exists
        if not self.mock_path.exists():
            self.mock_path.parent.mkdir(parents=True, exist_ok=True)
            # Create with sample data
            with open(self.mock_path, "w", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "endpoint": "conversations.list",
                            "method": "GET",
                            "response": {
                                "ok": True,
                                "channels": [
                                    {
                                        "id": "C1234567890",
                                        "name": "general",
                                        "is_channel": True,
                                        "is_member": True,
                                        "num_members": 10,
                                    }
                                ],
                            },
                        }
                    )
                    + "\n"
                )
                f.write(
                    json.dumps(
                        {
                            "endpoint": "conversations.history",
                            "method": "GET",
                            "response": {
                                "ok": True,
                                "messages": [
                                    {
                                        "ts": "1609459200.000100",
                                        "text": "Hello, world!",
                                        "user": "U1234567890",
                                        "type": "message",
                                    }
                                ],
                            },
                        }
                    )
                    + "\n"
                )
                f.write(
                    json.dumps(
                        {
                            "endpoint": "users.list",
                            "method": "GET",
                            "response": {
                                "ok": True,
                                "members": [
                                    {
                                        "id": "U1234567890",
                                        "name": "john.doe",
                                        "real_name": "John Doe",
                                        "is_bot": False,
                                    }
                                ],
                            },
                        }
                    )
                    + "\n"
                )

        # Load mock responses
        mock_responses = []
        with open(self.mock_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    mock_responses.append(json.loads(line))

        # Find matching response
        for mock in mock_responses:
            if mock.get("endpoint") in endpoint and mock.get("method") == method:
                return mock.get("response", {})

        # Default response
        return {"ok": True, "channels": [], "messages": [], "members": []}

    def list_resources(self, resource_type: str, **kwargs) -> list[dict]:
        """List resources (channels, messages, users).

        Args:
            resource_type: Resource type (channels, messages, users)
            **kwargs: Optional filters (channel_id)

        Returns:
            List of resources
        """
        if resource_type == "channels":
            response = self._call_api("GET", "conversations.list", params={"types": "public_channel,private_channel"})
            return response.get("channels", [])

        elif resource_type == "messages":
            channel_id = kwargs.get("channel_id", self.default_channel_id)
            if not channel_id:
                raise ValueError("channel_id required for messages")

            response = self._call_api("GET", "conversations.history", params={"channel": channel_id})
            return response.get("messages", [])

        elif resource_type == "users":
            response = self._call_api("GET", "users.list")
            return response.get("members", [])

        else:
            raise ValueError(f"Unknown resource type: {resource_type}")

    def get_resource(self, resource_type: str, resource_id: str, **kwargs) -> dict:
        """Get specific resource.

        Args:
            resource_type: Resource type
            resource_id: Resource ID
            **kwargs: Optional context (channel_id)

        Returns:
            Resource data
        """
        if resource_type == "channels":
            response = self._call_api("GET", "conversations.info", params={"channel": resource_id})
            return response.get("channel", {})

        elif resource_type == "messages":
            channel_id = kwargs.get("channel_id", self.default_channel_id)
            if not channel_id:
                raise ValueError("channel_id required for messages")

            # Get single message by timestamp
            response = self._call_api(
                "GET",
                "conversations.history",
                params={"channel": channel_id, "latest": resource_id, "inclusive": True, "limit": 1},
            )
            messages = response.get("messages", [])
            if messages:
                return messages[0]
            raise Exception(f"Message {resource_id} not found")

        elif resource_type == "users":
            response = self._call_api("GET", "users.info", params={"user": resource_id})
            return response.get("user", {})

        else:
            raise ValueError(f"Unknown resource type: {resource_type}")

    def create_resource(self, resource_type: str, payload: dict, **kwargs) -> dict:
        """Create resource (message only).

        Args:
            resource_type: Resource type (messages)
            payload: Resource data
            **kwargs: Context (channel_id)

        Returns:
            Created resource
        """
        # RBAC: writes require Admin
        if not self._check_rbac("Admin"):
            raise PermissionError("Create requires Admin role")

        if resource_type == "messages":
            channel_id = kwargs.get("channel_id", self.default_channel_id)
            if not channel_id:
                raise ValueError("channel_id required")

            # Ensure channel is in payload
            payload["channel"] = channel_id

            return self._call_api("POST", "chat.postMessage", json_data=payload)

        else:
            raise ValueError(f"Create not supported for: {resource_type}")

    def update_resource(self, resource_type: str, resource_id: str, payload: dict, **kwargs) -> dict:
        """Update resource (message only).

        Args:
            resource_type: Resource type
            resource_id: Resource ID (message timestamp)
            payload: Update data
            **kwargs: Context (channel_id)

        Returns:
            Updated resource
        """
        # RBAC: writes require Admin
        if not self._check_rbac("Admin"):
            raise PermissionError("Update requires Admin role")

        if resource_type == "messages":
            channel_id = kwargs.get("channel_id", self.default_channel_id)
            if not channel_id:
                raise ValueError("channel_id required")

            # Slack requires channel, ts, and text for updates
            payload["channel"] = channel_id
            payload["ts"] = resource_id

            return self._call_api("POST", "chat.update", json_data=payload)

        else:
            raise ValueError(f"Update not supported for: {resource_type}")

    def delete_resource(self, resource_type: str, resource_id: str, **kwargs) -> bool:
        """Delete resource (message only).

        Args:
            resource_type: Resource type
            resource_id: Resource ID (message timestamp)
            **kwargs: Context (channel_id)

        Returns:
            True if deleted
        """
        # RBAC: writes require Admin
        if not self._check_rbac("Admin"):
            raise PermissionError("Delete requires Admin role")

        if resource_type == "messages":
            channel_id = kwargs.get("channel_id", self.default_channel_id)
            if not channel_id:
                raise ValueError("channel_id required")

            self._call_api("POST", "chat.delete", json_data={"channel": channel_id, "ts": resource_id})
            return True

        else:
            raise ValueError(f"Delete not supported for: {resource_type}")

    def _check_rbac(self, required_role: str) -> bool:
        """Check if user has required role.

        Args:
            required_role: Minimum role required

        Returns:
            True if authorized
        """
        user_role = os.getenv("USER_ROLE", "Viewer")
        roles = ["Admin", "Deployer", "Operator", "Viewer"]

        try:
            user_idx = roles.index(user_role)
            required_idx = roles.index(required_role)
            return user_idx <= required_idx
        except ValueError:
            return False

    def connect(self) -> bool:
        """Connect to Slack (validates token in LIVE mode).

        Returns:
            True if connection successful
        """
        if self.dry_run:
            return True

        # Validate token with auth.test
        try:
            response = self._call_api("GET", "auth.test")
            return response.get("ok", False)
        except Exception:
            return False

    def disconnect(self) -> bool:
        """Disconnect from Slack (no-op for REST API).

        Returns:
            True
        """
        return True
