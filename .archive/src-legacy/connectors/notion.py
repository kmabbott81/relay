"""Notion connector using Notion REST API.

Supports DRY_RUN (mock) and LIVE (real API) modes.
Handles pages, databases, and blocks via Notion API v1.
"""

import json
import os
import time
from pathlib import Path
from typing import Optional

from .base import Connector, ConnectorResult
from .circuit import CircuitBreaker
from .http_client import request
from .http_mock import get_mock_transport, is_mock_enabled
from .metrics import record_call
from .oauth2 import load_token, needs_refresh
from .retry import compute_backoff_ms


class NotionAPIError(Exception):
    """Non-retryable Notion API error."""

    pass


class NotionConnector(Connector):
    """Notion connector with OAuth2, retry, circuit breaker, metrics."""

    def __init__(self, connector_id: str, tenant_id: str, user_id: str):
        """Initialize Notion connector.

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

        # Notion API config
        self.base_url = os.getenv("NOTION_API_BASE", "https://api.notion.com/v1")
        self.notion_version = os.getenv("NOTION_VERSION", "2022-06-28")

        # OAuth2 credentials
        self.api_token = os.getenv("NOTION_API_TOKEN", "")

        # Observability
        self.circuit = CircuitBreaker(connector_id)
        self.max_retries = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))

        # Retry configuration
        self.retry_status_codes = self._parse_retry_statuses()

        # Mock data path
        self.mock_path = Path("logs/connectors/notion_mock.jsonl")

        # Token service ID (supports multi-tenant)
        self.token_service_id = f"notion:{self.tenant_id}"

    def _parse_retry_statuses(self) -> set[int]:
        """Parse NOTION_RETRY_STATUS env var into set of status codes.

        Returns:
            Set of HTTP status codes that should trigger retry
        """
        retry_str = os.getenv("NOTION_RETRY_STATUS", "429,500,502,503,504")
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
            return "mock-notion-token"

        # Try loading from unified token store
        token = load_token(self.connector_id, self.token_service_id)

        if not token:
            # Fallback to API token env var (for initial setup)
            if self.api_token:
                return self.api_token
            raise Exception("No Notion token found. Set NOTION_API_TOKEN or run OAuth2 setup.")

        if needs_refresh(token):
            # Notion uses long-lived tokens; refresh not typically needed
            raise Exception("Token expired. Please generate new integration token.")

        return token["access_token"]

    def _call_api(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        """Call Notion REST API with retry/circuit breaker/metrics.

        Args:
            method: HTTP method
            endpoint: API endpoint (e.g., pages, databases/{id}/query)
            json_data: Request body for POST/PATCH
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
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": self.notion_version,
        }

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

                    # Notion API errors can be returned with error field
                    if isinstance(body, dict) and "object" in body and body["object"] == "error":
                        error_msg = body.get("message", "unknown_error")
                        error_code = body.get("code", "unknown")

                        # Check if retryable (rate limit)
                        if error_code == "rate_limited":
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

                        # Other Notion API errors (non-retryable)
                        self.circuit.record_failure()
                        record_call(
                            self.connector_id,
                            endpoint,
                            "error",
                            duration_ms,
                            error=f"Notion API error: {error_msg}",
                        )
                        raise NotionAPIError(f"Notion API error: {error_msg}")

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
                    raise NotionAPIError(f"API error {response['status_code']}: {response.get('body')}")

            except NotionAPIError:
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
                # Sample pages list
                f.write(
                    json.dumps(
                        {
                            "endpoint": "search",
                            "method": "POST",
                            "response": {
                                "object": "list",
                                "results": [
                                    {
                                        "object": "page",
                                        "id": "page-123",
                                        "created_time": "2023-01-01T00:00:00.000Z",
                                        "last_edited_time": "2023-01-02T00:00:00.000Z",
                                        "properties": {
                                            "title": {
                                                "id": "title",
                                                "type": "title",
                                                "title": [
                                                    {
                                                        "type": "text",
                                                        "text": {"content": "Sample Page"},
                                                        "plain_text": "Sample Page",
                                                    }
                                                ],
                                            }
                                        },
                                    }
                                ],
                                "has_more": False,
                            },
                        }
                    )
                    + "\n"
                )
                # Sample page get
                f.write(
                    json.dumps(
                        {
                            "endpoint": "pages/",
                            "method": "GET",
                            "response": {
                                "object": "page",
                                "id": "page-123",
                                "created_time": "2023-01-01T00:00:00.000Z",
                                "last_edited_time": "2023-01-02T00:00:00.000Z",
                                "properties": {
                                    "title": {
                                        "id": "title",
                                        "type": "title",
                                        "title": [
                                            {
                                                "type": "text",
                                                "text": {"content": "Sample Page"},
                                                "plain_text": "Sample Page",
                                            }
                                        ],
                                    }
                                },
                            },
                        }
                    )
                    + "\n"
                )
                # Sample database query
                f.write(
                    json.dumps(
                        {
                            "endpoint": "databases/",
                            "method": "POST",
                            "response": {
                                "object": "list",
                                "results": [
                                    {
                                        "object": "page",
                                        "id": "page-db-123",
                                        "created_time": "2023-01-01T00:00:00.000Z",
                                        "properties": {},
                                    }
                                ],
                                "has_more": False,
                            },
                        }
                    )
                    + "\n"
                )
                # Sample blocks list
                f.write(
                    json.dumps(
                        {
                            "endpoint": "blocks/",
                            "method": "GET",
                            "response": {
                                "object": "list",
                                "results": [
                                    {
                                        "object": "block",
                                        "id": "block-123",
                                        "type": "paragraph",
                                        "paragraph": {
                                            "rich_text": [
                                                {
                                                    "type": "text",
                                                    "text": {"content": "Sample paragraph text"},
                                                    "plain_text": "Sample paragraph text",
                                                }
                                            ]
                                        },
                                    }
                                ],
                                "has_more": False,
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
        return {"object": "list", "results": [], "has_more": False}

    def connect(self) -> ConnectorResult:
        """Connect to Notion (validates token in LIVE mode).

        Returns:
            ConnectorResult with status and message
        """
        if self.dry_run:
            self.connected = True
            return ConnectorResult(status="success", message="Connected (DRY_RUN mode)")

        # Validate token with users/me endpoint (bot user info)
        try:
            # Notion doesn't have a direct auth test endpoint, but we can list users
            response = self._call_api("GET", "users/me")
            if response.get("object") == "user":
                self.connected = True
                return ConnectorResult(status="success", message="Connected to Notion")
            else:
                return ConnectorResult(status="error", message="Invalid token response")
        except Exception as e:
            return ConnectorResult(status="error", message=f"Connection failed: {str(e)}")

    def disconnect(self) -> ConnectorResult:
        """Disconnect from Notion (no-op for REST API).

        Returns:
            ConnectorResult with status
        """
        self.connected = False
        return ConnectorResult(status="success", message="Disconnected")

    def list_resources(self, resource_type: str, filters: Optional[dict] = None) -> ConnectorResult:
        """List resources (pages, databases, blocks).

        Args:
            resource_type: Resource type (pages, databases, blocks)
            filters: Optional filters (database_id, page_id, query)

        Returns:
            ConnectorResult with list of resources in data field
        """
        # RBAC: reads require Operator or higher
        if not self.check_rbac():
            return ConnectorResult(status="denied", message="Insufficient permissions")

        filters = filters or {}

        try:
            if resource_type == "pages":
                # Search for pages using search endpoint
                query_params = {
                    "filter": {"property": "object", "value": "page"},
                    "page_size": filters.get("limit", 100),
                }
                if "query" in filters:
                    query_params["query"] = filters["query"]

                response = self._call_api("POST", "search", json_data=query_params)
                pages = response.get("results", [])
                return ConnectorResult(status="success", data=pages)

            elif resource_type == "databases":
                # Search for databases
                query_params = {
                    "filter": {"property": "object", "value": "database"},
                    "page_size": filters.get("limit", 100),
                }
                if "query" in filters:
                    query_params["query"] = filters["query"]

                response = self._call_api("POST", "search", json_data=query_params)
                databases = response.get("results", [])
                return ConnectorResult(status="success", data=databases)

            elif resource_type == "blocks":
                # List blocks requires page_id or block_id
                parent_id = filters.get("page_id") or filters.get("block_id")
                if not parent_id:
                    return ConnectorResult(status="error", message="page_id or block_id required for blocks")

                response = self._call_api("GET", f"blocks/{parent_id}/children")
                blocks = response.get("results", [])
                return ConnectorResult(status="success", data=blocks)

            else:
                return ConnectorResult(status="error", message=f"Unknown resource type: {resource_type}")

        except Exception as e:
            return ConnectorResult(status="error", message=str(e))

    def get_resource(self, resource_type: str, resource_id: str) -> ConnectorResult:
        """Get specific resource by ID.

        Args:
            resource_type: Type of resource
            resource_id: Unique resource identifier

        Returns:
            ConnectorResult with resource data
        """
        # RBAC: reads require Operator or higher
        if not self.check_rbac():
            return ConnectorResult(status="denied", message="Insufficient permissions")

        try:
            if resource_type == "pages":
                response = self._call_api("GET", f"pages/{resource_id}")
                return ConnectorResult(status="success", data=response)

            elif resource_type == "databases":
                response = self._call_api("GET", f"databases/{resource_id}")
                return ConnectorResult(status="success", data=response)

            elif resource_type == "blocks":
                response = self._call_api("GET", f"blocks/{resource_id}")
                return ConnectorResult(status="success", data=response)

            else:
                return ConnectorResult(status="error", message=f"Unknown resource type: {resource_type}")

        except Exception as e:
            return ConnectorResult(status="error", message=str(e))

    def create_resource(self, resource_type: str, payload: dict) -> ConnectorResult:
        """Create new resource.

        Args:
            resource_type: Type of resource to create
            payload: Resource data

        Returns:
            ConnectorResult with created resource data
        """
        # RBAC: writes require Admin
        old_required = self.required_role
        self.required_role = "Admin"
        if not self.check_rbac():
            self.required_role = old_required
            return ConnectorResult(status="denied", message="Create requires Admin role")
        self.required_role = old_required

        try:
            if resource_type == "pages":
                # Create page
                response = self._call_api("POST", "pages", json_data=payload)
                return ConnectorResult(status="success", data=response)

            elif resource_type == "databases":
                # Create database (requires parent page)
                response = self._call_api("POST", "databases", json_data=payload)
                return ConnectorResult(status="success", data=response)

            elif resource_type == "blocks":
                # Append blocks to page (requires page_id in payload or via parent_id)
                parent_id = payload.get("parent_id")
                if not parent_id:
                    return ConnectorResult(status="error", message="parent_id required for creating blocks")

                children = payload.get("children", [])
                append_payload = {"children": children}
                response = self._call_api("PATCH", f"blocks/{parent_id}/children", json_data=append_payload)
                return ConnectorResult(status="success", data=response)

            else:
                return ConnectorResult(status="error", message=f"Create not supported for: {resource_type}")

        except Exception as e:
            return ConnectorResult(status="error", message=str(e))

    def update_resource(self, resource_type: str, resource_id: str, payload: dict) -> ConnectorResult:
        """Update existing resource.

        Args:
            resource_type: Type of resource
            resource_id: Resource identifier
            payload: Updated data

        Returns:
            ConnectorResult with updated resource data
        """
        # RBAC: writes require Admin
        old_required = self.required_role
        self.required_role = "Admin"
        if not self.check_rbac():
            self.required_role = old_required
            return ConnectorResult(status="denied", message="Update requires Admin role")
        self.required_role = old_required

        try:
            if resource_type == "pages":
                # Update page properties
                response = self._call_api("PATCH", f"pages/{resource_id}", json_data=payload)
                return ConnectorResult(status="success", data=response)

            elif resource_type == "databases":
                # Update database properties
                response = self._call_api("PATCH", f"databases/{resource_id}", json_data=payload)
                return ConnectorResult(status="success", data=response)

            elif resource_type == "blocks":
                # Update block content
                response = self._call_api("PATCH", f"blocks/{resource_id}", json_data=payload)
                return ConnectorResult(status="success", data=response)

            else:
                return ConnectorResult(status="error", message=f"Update not supported for: {resource_type}")

        except Exception as e:
            return ConnectorResult(status="error", message=str(e))

    def delete_resource(self, resource_type: str, resource_id: str) -> ConnectorResult:
        """Delete resource.

        Args:
            resource_type: Type of resource
            resource_id: Resource identifier

        Returns:
            ConnectorResult with deletion status
        """
        # RBAC: writes require Admin
        old_required = self.required_role
        self.required_role = "Admin"
        if not self.check_rbac():
            self.required_role = old_required
            return ConnectorResult(status="denied", message="Delete requires Admin role")
        self.required_role = old_required

        try:
            if resource_type == "pages":
                # Archive page (Notion doesn't have true delete, only archive)
                payload = {"archived": True}
                response = self._call_api("PATCH", f"pages/{resource_id}", json_data=payload)
                return ConnectorResult(status="success", data=response, message="Page archived")

            elif resource_type == "databases":
                # Archive database
                payload = {"archived": True}
                response = self._call_api("PATCH", f"databases/{resource_id}", json_data=payload)
                return ConnectorResult(status="success", data=response, message="Database archived")

            elif resource_type == "blocks":
                # Delete block
                response = self._call_api("DELETE", f"blocks/{resource_id}")
                return ConnectorResult(status="success", data=response, message="Block deleted")

            else:
                return ConnectorResult(status="error", message=f"Delete not supported for: {resource_type}")

        except Exception as e:
            return ConnectorResult(status="error", message=str(e))
