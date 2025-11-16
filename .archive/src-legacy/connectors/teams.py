"""Microsoft Teams connector using Graph API.

Supports DRY_RUN (mock) and LIVE (real API) modes.
"""

import json
import os
import time
from pathlib import Path
from typing import Optional

from .base import Connector
from .circuit import CircuitBreaker
from .http_client import request
from .metrics import record_call
from .oauth2 import load_token, needs_refresh
from .retry import compute_backoff_ms


class TeamsConnector(Connector):
    """Microsoft Teams connector with OAuth2, retry, circuit breaker, metrics."""

    def __init__(self, connector_id: str, tenant_id: str, user_id: str):
        """Initialize Teams connector.

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

        # Graph API config
        self.base_url = os.getenv("GRAPH_BASE_URL", "https://graph.microsoft.com/v1.0")
        self.client_id = os.getenv("MS_CLIENT_ID", "")
        self.tenant_ms_id = os.getenv("MS_TENANT_ID", "")
        self.client_secret = os.getenv("MS_CLIENT_SECRET", "")

        # Defaults
        self.default_team_id = os.getenv("TEAMS_DEFAULT_TEAM_ID", "")
        self.default_channel_id = os.getenv("TEAMS_DEFAULT_CHANNEL_ID", "")

        # Observability
        self.circuit = CircuitBreaker(connector_id)
        self.max_retries = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))

        # Mock data path
        self.mock_path = Path("logs/connectors/teams_mock.jsonl")

    def _get_token(self) -> str:
        """Get OAuth2 access token.

        Returns:
            Access token

        Raises:
            Exception if token not available or refresh fails
        """
        token = load_token(self.connector_id)

        if not token:
            raise Exception("No OAuth2 token found. Run token setup first.")

        if needs_refresh(token):
            # TODO: Implement refresh_token() in oauth2.py for Microsoft
            raise Exception("Token expired. Refresh not yet implemented.")

        return token["access_token"]

    def _call_api(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[dict] = None,
    ) -> dict:
        """Call Microsoft Graph API with retry/circuit breaker/metrics.

        Args:
            method: HTTP method
            endpoint: API endpoint (relative to base_url)
            json_data: Request body

        Returns:
            Response body

        Raises:
            Exception on failure after retries
        """
        if self.dry_run:
            return self._mock_response(method, endpoint, json_data)

        # Check circuit breaker
        if not self.circuit.allow():
            raise Exception(f"Circuit breaker open for {self.connector_id}")

        url = f"{self.base_url}/{endpoint}"
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}

        last_error = None
        for attempt in range(self.max_retries):
            start_time = time.time()

            try:
                response = request(method, url, headers=headers, json_data=json_data)
                duration_ms = (time.time() - start_time) * 1000

                # Check status
                if 200 <= response["status_code"] < 300:
                    # Success
                    self.circuit.record_success()
                    record_call(
                        self.connector_id,
                        endpoint,
                        "success",
                        duration_ms,
                    )
                    return response["body"]

                elif response["status_code"] == 429:
                    # Rate limit - retry with backoff
                    self.circuit.record_failure()
                    record_call(
                        self.connector_id,
                        endpoint,
                        "error",
                        duration_ms,
                        error=f"Rate limited: {response['status_code']}",
                    )

                    if attempt < self.max_retries - 1:
                        backoff_ms = compute_backoff_ms(attempt)
                        time.sleep(backoff_ms / 1000.0)
                        continue

                elif response["status_code"] >= 500:
                    # Server error - retry
                    self.circuit.record_failure()
                    record_call(
                        self.connector_id,
                        endpoint,
                        "error",
                        duration_ms,
                        error=f"Server error: {response['status_code']}",
                    )

                    if attempt < self.max_retries - 1:
                        backoff_ms = compute_backoff_ms(attempt)
                        time.sleep(backoff_ms / 1000.0)
                        continue

                else:
                    # Client error - don't retry
                    self.circuit.record_failure()
                    record_call(
                        self.connector_id,
                        endpoint,
                        "error",
                        duration_ms,
                        error=f"Client error: {response['status_code']}",
                    )
                    raise Exception(f"API error {response['status_code']}: {response.get('body')}")

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
                            "endpoint": "teams",
                            "method": "GET",
                            "response": {
                                "value": [
                                    {
                                        "id": "team-1",
                                        "displayName": "Engineering Team",
                                        "description": "Engineering team workspace",
                                    }
                                ]
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
        return {"value": [], "message": "Mock response"}

    def list_resources(self, resource_type: str, **kwargs) -> list[dict]:
        """List resources (teams, channels, messages).

        Args:
            resource_type: Resource type (teams, channels, messages)
            **kwargs: Optional filters (team_id, channel_id)

        Returns:
            List of resources
        """
        if resource_type == "teams":
            response = self._call_api("GET", "teams")
            return response.get("value", [])

        elif resource_type == "channels":
            team_id = kwargs.get("team_id", self.default_team_id)
            if not team_id:
                raise ValueError("team_id required for channels")

            response = self._call_api("GET", f"teams/{team_id}/channels")
            return response.get("value", [])

        elif resource_type == "messages":
            team_id = kwargs.get("team_id", self.default_team_id)
            channel_id = kwargs.get("channel_id", self.default_channel_id)

            if not team_id or not channel_id:
                raise ValueError("team_id and channel_id required for messages")

            response = self._call_api("GET", f"teams/{team_id}/channels/{channel_id}/messages")
            return response.get("value", [])

        else:
            raise ValueError(f"Unknown resource type: {resource_type}")

    def get_resource(self, resource_type: str, resource_id: str, **kwargs) -> dict:
        """Get specific resource.

        Args:
            resource_type: Resource type
            resource_id: Resource ID
            **kwargs: Optional context (team_id, channel_id)

        Returns:
            Resource data
        """
        if resource_type == "teams":
            return self._call_api("GET", f"teams/{resource_id}")

        elif resource_type == "channels":
            team_id = kwargs.get("team_id", self.default_team_id)
            if not team_id:
                raise ValueError("team_id required")

            return self._call_api("GET", f"teams/{team_id}/channels/{resource_id}")

        elif resource_type == "messages":
            team_id = kwargs.get("team_id", self.default_team_id)
            channel_id = kwargs.get("channel_id", self.default_channel_id)

            if not team_id or not channel_id:
                raise ValueError("team_id and channel_id required")

            return self._call_api("GET", f"teams/{team_id}/channels/{channel_id}/messages/{resource_id}")

        else:
            raise ValueError(f"Unknown resource type: {resource_type}")

    def create_resource(self, resource_type: str, payload: dict, **kwargs) -> dict:
        """Create resource (message only).

        Args:
            resource_type: Resource type (messages)
            payload: Resource data
            **kwargs: Context (team_id, channel_id)

        Returns:
            Created resource
        """
        # RBAC: writes require Admin
        if not self._check_rbac("Admin"):
            raise PermissionError("Create requires Admin role")

        if resource_type == "messages":
            team_id = kwargs.get("team_id", self.default_team_id)
            channel_id = kwargs.get("channel_id", self.default_channel_id)

            if not team_id or not channel_id:
                raise ValueError("team_id and channel_id required")

            return self._call_api(
                "POST",
                f"teams/{team_id}/channels/{channel_id}/messages",
                json_data=payload,
            )

        else:
            raise ValueError(f"Create not supported for: {resource_type}")

    def update_resource(self, resource_type: str, resource_id: str, payload: dict, **kwargs) -> dict:
        """Update resource (message only).

        Args:
            resource_type: Resource type
            resource_id: Resource ID
            payload: Update data
            **kwargs: Context

        Returns:
            Updated resource
        """
        # RBAC: writes require Admin
        if not self._check_rbac("Admin"):
            raise PermissionError("Update requires Admin role")

        if resource_type == "messages":
            team_id = kwargs.get("team_id", self.default_team_id)
            channel_id = kwargs.get("channel_id", self.default_channel_id)

            if not team_id or not channel_id:
                raise ValueError("team_id and channel_id required")

            return self._call_api(
                "PATCH",
                f"teams/{team_id}/channels/{channel_id}/messages/{resource_id}",
                json_data=payload,
            )

        else:
            raise ValueError(f"Update not supported for: {resource_type}")

    def delete_resource(self, resource_type: str, resource_id: str, **kwargs) -> bool:
        """Delete resource (best-effort for messages).

        Args:
            resource_type: Resource type
            resource_id: Resource ID
            **kwargs: Context

        Returns:
            True if deleted
        """
        # RBAC: writes require Admin
        if not self._check_rbac("Admin"):
            raise PermissionError("Delete requires Admin role")

        if resource_type == "messages":
            team_id = kwargs.get("team_id", self.default_team_id)
            channel_id = kwargs.get("channel_id", self.default_channel_id)

            if not team_id or not channel_id:
                raise ValueError("team_id and channel_id required")

            # Note: Graph API doesn't support message deletion directly
            # This is best-effort via soft delete
            self._call_api(
                "DELETE",
                f"teams/{team_id}/channels/{channel_id}/messages/{resource_id}/softDelete",
            )
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
        """Connect to Teams (validates token in LIVE mode).

        Returns:
            True if connection successful
        """
        if self.dry_run:
            return True

        # Validate token exists
        try:
            self._get_token()
            return True
        except Exception:
            return False

    def disconnect(self) -> bool:
        """Disconnect from Teams (no-op for REST API).

        Returns:
            True
        """
        return True
