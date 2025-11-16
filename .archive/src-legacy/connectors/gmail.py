"""Gmail connector using Gmail REST API.

Supports DRY_RUN (mock) and LIVE (real API) modes.
Handles messages, threads, and labels via Gmail API v1.
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


class GmailAPIError(Exception):
    """Non-retryable Gmail API error."""

    pass


class GmailConnector(Connector):
    """Gmail connector with OAuth2, retry, circuit breaker, metrics."""

    def __init__(self, connector_id: str, tenant_id: str, user_id: str):
        """Initialize Gmail connector.

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

        # Gmail API config
        self.base_url = os.getenv("GMAIL_API_BASE", "https://gmail.googleapis.com/gmail/v1")

        # OAuth2 credentials
        self.client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
        self.refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN", "")

        # Observability
        self.circuit = CircuitBreaker(connector_id)
        self.max_retries = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))

        # Retry configuration
        self.retry_status_codes = self._parse_retry_statuses()

        # Mock data path
        self.mock_path = Path("logs/connectors/gmail_mock.jsonl")

        # Token service ID (supports multi-tenant)
        self.token_service_id = f"gmail:{self.tenant_id}"

    def _parse_retry_statuses(self) -> set[int]:
        """Parse GMAIL_RETRY_STATUS env var into set of status codes.

        Returns:
            Set of HTTP status codes that should trigger retry
        """
        retry_str = os.getenv("GMAIL_RETRY_STATUS", "429,500,502,503,504")
        try:
            return {int(code.strip()) for code in retry_str.split(",")}
        except ValueError:
            # Default retry codes
            return {429, 500, 502, 503, 504}

    def _get_token(self) -> str:
        """Get OAuth2 access token.

        Returns:
            Access token

        Raises:
            Exception if token not available or refresh fails
        """
        # In dry_run or mock mode, use placeholder token
        if self.dry_run or is_mock_enabled():
            return "mock-gmail-token"

        # Try loading from unified token store
        token = load_token(self.connector_id, self.token_service_id)

        if not token:
            # Fallback to refresh token env var (for initial setup)
            if self.refresh_token:
                # In production, this would trigger refresh flow
                # For now, just use refresh_token as placeholder
                raise Exception("No Gmail token found. Set GOOGLE_REFRESH_TOKEN or run OAuth2 setup.")
            raise Exception("No Gmail token found. Run OAuth2 setup.")

        if needs_refresh(token):
            # TODO: Implement refresh_token() in oauth2.py for Gmail
            raise Exception("Token expired. Refresh not yet implemented.")

        return token["access_token"]

    def _call_api(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        """Call Gmail REST API with retry/circuit breaker/metrics.

        Args:
            method: HTTP method
            endpoint: API endpoint (e.g., users/me/messages)
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
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

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
                    # Success
                    body = response["body"]

                    # Gmail API errors are returned with 200 status but error field
                    if isinstance(body, dict) and "error" in body:
                        error_data = body["error"]
                        error_msg = error_data.get("message", "unknown_error")
                        error_code = error_data.get("code", 0)

                        # Check if retryable (rate limit)
                        if error_code == 429:
                            self.circuit.record_failure()
                            record_call(
                                self.connector_id,
                                endpoint,
                                "error",
                                duration_ms,
                                error=f"Rate limited: {error_msg}",
                            )

                            if attempt < self.max_retries - 1:
                                backoff_ms = compute_backoff_ms(attempt)
                                time.sleep(backoff_ms / 1000.0)
                                continue

                        # Other Gmail API errors (non-retryable)
                        self.circuit.record_failure()
                        record_call(
                            self.connector_id,
                            endpoint,
                            "error",
                            duration_ms,
                            error=f"Gmail API error: {error_msg}",
                        )
                        raise GmailAPIError(f"Gmail API error: {error_msg}")

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
                    raise GmailAPIError(f"API error {response['status_code']}: {response.get('body')}")

            except GmailAPIError:
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
                # Sample messages list
                f.write(
                    json.dumps(
                        {
                            "endpoint": "users/me/messages",
                            "method": "GET",
                            "response": {
                                "messages": [
                                    {
                                        "id": "18c8f123456789ab",
                                        "threadId": "18c8f123456789ab",
                                    }
                                ],
                                "resultSizeEstimate": 1,
                            },
                        }
                    )
                    + "\n"
                )
                # Sample message get
                f.write(
                    json.dumps(
                        {
                            "endpoint": "users/me/messages/",
                            "method": "GET",
                            "response": {
                                "id": "18c8f123456789ab",
                                "threadId": "18c8f123456789ab",
                                "labelIds": ["INBOX"],
                                "snippet": "Hello from Gmail...",
                                "payload": {
                                    "headers": [
                                        {"name": "From", "value": "sender@example.com"},
                                        {"name": "To", "value": "recipient@example.com"},
                                        {"name": "Subject", "value": "Test Message"},
                                    ],
                                    "body": {"data": "SGVsbG8gZnJvbSBHbWFpbA=="},
                                },
                                "internalDate": "1609459200000",
                            },
                        }
                    )
                    + "\n"
                )
                # Sample threads list
                f.write(
                    json.dumps(
                        {
                            "endpoint": "users/me/threads",
                            "method": "GET",
                            "response": {
                                "threads": [
                                    {
                                        "id": "18c8f123456789ab",
                                        "snippet": "Hello from Gmail...",
                                        "historyId": "123456",
                                    }
                                ],
                                "resultSizeEstimate": 1,
                            },
                        }
                    )
                    + "\n"
                )
                # Sample labels list
                f.write(
                    json.dumps(
                        {
                            "endpoint": "users/me/labels",
                            "method": "GET",
                            "response": {
                                "labels": [
                                    {
                                        "id": "INBOX",
                                        "name": "INBOX",
                                        "type": "system",
                                        "messageListVisibility": "show",
                                        "labelListVisibility": "labelShow",
                                    },
                                    {
                                        "id": "Label_1",
                                        "name": "Test Label",
                                        "type": "user",
                                        "messageListVisibility": "show",
                                        "labelListVisibility": "labelShow",
                                    },
                                ],
                            },
                        }
                    )
                    + "\n"
                )
                # Sample send message
                f.write(
                    json.dumps(
                        {
                            "endpoint": "users/me/messages/send",
                            "method": "POST",
                            "response": {
                                "id": "18c8f987654321cd",
                                "threadId": "18c8f987654321cd",
                                "labelIds": ["SENT"],
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
        return {"messages": [], "threads": [], "labels": []}

    def list_resources(self, resource_type: str, **kwargs) -> list[dict]:
        """List resources (messages, threads, labels).

        Args:
            resource_type: Resource type (messages, threads, labels)
            **kwargs: Optional filters (q for query, labelIds)

        Returns:
            List of resources
        """
        if resource_type == "messages":
            params = {}
            if "q" in kwargs:
                params["q"] = kwargs["q"]
            if "labelIds" in kwargs:
                params["labelIds"] = kwargs["labelIds"]
            if "maxResults" in kwargs:
                params["maxResults"] = kwargs["maxResults"]

            response = self._call_api("GET", "users/me/messages", params=params)
            return response.get("messages", [])

        elif resource_type == "threads":
            params = {}
            if "q" in kwargs:
                params["q"] = kwargs["q"]
            if "maxResults" in kwargs:
                params["maxResults"] = kwargs["maxResults"]

            response = self._call_api("GET", "users/me/threads", params=params)
            return response.get("threads", [])

        elif resource_type == "labels":
            response = self._call_api("GET", "users/me/labels")
            return response.get("labels", [])

        else:
            raise ValueError(f"Unknown resource type: {resource_type}")

    def get_resource(self, resource_type: str, resource_id: str, **kwargs) -> dict:
        """Get specific resource.

        Args:
            resource_type: Resource type
            resource_id: Resource ID
            **kwargs: Optional parameters (format for messages)

        Returns:
            Resource data
        """
        if resource_type == "messages":
            params = kwargs.get("format", {})
            if isinstance(params, str):
                params = {"format": params}

            response = self._call_api("GET", f"users/me/messages/{resource_id}", params=params)
            return response

        elif resource_type == "threads":
            response = self._call_api("GET", f"users/me/threads/{resource_id}")
            return response

        elif resource_type == "labels":
            response = self._call_api("GET", f"users/me/labels/{resource_id}")
            return response

        else:
            raise ValueError(f"Unknown resource type: {resource_type}")

    def create_resource(self, resource_type: str, payload: dict, **kwargs) -> dict:
        """Create resource (messages send, labels create).

        Args:
            resource_type: Resource type (messages, labels)
            payload: Resource data
            **kwargs: Additional context

        Returns:
            Created resource
        """
        # RBAC: writes require Admin
        if not self._check_rbac("Admin"):
            raise PermissionError("Create requires Admin role")

        if resource_type == "messages":
            # Send message via Gmail API
            # payload should contain 'raw' (base64url encoded RFC 2822 message)
            return self._call_api("POST", "users/me/messages/send", json_data=payload)

        elif resource_type == "labels":
            # Create label
            return self._call_api("POST", "users/me/labels", json_data=payload)

        else:
            raise ValueError(f"Create not supported for: {resource_type}")

    def update_resource(self, resource_type: str, resource_id: str, payload: dict, **kwargs) -> dict:
        """Update resource (message labels, label properties).

        Args:
            resource_type: Resource type
            resource_id: Resource ID
            payload: Update data
            **kwargs: Additional context

        Returns:
            Updated resource
        """
        # RBAC: writes require Admin
        if not self._check_rbac("Admin"):
            raise PermissionError("Update requires Admin role")

        if resource_type == "messages":
            # Modify message labels
            # payload should contain 'addLabelIds' and/or 'removeLabelIds'
            return self._call_api("POST", f"users/me/messages/{resource_id}/modify", json_data=payload)

        elif resource_type == "labels":
            # Update label properties
            return self._call_api("PATCH", f"users/me/labels/{resource_id}", json_data=payload)

        else:
            raise ValueError(f"Update not supported for: {resource_type}")

    def delete_resource(self, resource_type: str, resource_id: str, **kwargs) -> bool:
        """Delete resource (message, label).

        Args:
            resource_type: Resource type
            resource_id: Resource ID
            **kwargs: Additional context

        Returns:
            True if deleted
        """
        # RBAC: writes require Admin
        if not self._check_rbac("Admin"):
            raise PermissionError("Delete requires Admin role")

        if resource_type == "messages":
            # Delete message (moves to trash by default, unless 'trash' endpoint used)
            self._call_api("DELETE", f"users/me/messages/{resource_id}")
            return True

        elif resource_type == "labels":
            # Delete label
            self._call_api("DELETE", f"users/me/labels/{resource_id}")
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
        """Connect to Gmail (validates token in LIVE mode).

        Returns:
            True if connection successful
        """
        if self.dry_run:
            return True

        # Validate token with profile endpoint
        try:
            response = self._call_api("GET", "users/me/profile")
            return "emailAddress" in response
        except Exception:
            return False

    def disconnect(self) -> bool:
        """Disconnect from Gmail (no-op for REST API).

        Returns:
            True
        """
        return True
