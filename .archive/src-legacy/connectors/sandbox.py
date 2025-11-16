"""Sandbox connector for testing and demos.

In-memory CRUD operations with configurable latency and error injection.
"""

import os
import random
import time
from typing import Any, Optional

from .base import Connector, ConnectorResult


class SandboxConnector(Connector):
    """In-memory connector for testing without external APIs.

    Supports:
    - CRUD operations on in-memory resources
    - Configurable latency (SANDBOX_LATENCY_MS)
    - Error injection (SANDBOX_ERROR_RATE)
    """

    def __init__(self, connector_id: str, tenant_id: str, user_id: str):
        """Initialize sandbox connector.

        Args:
            connector_id: Connector identifier
            tenant_id: Tenant for isolation
            user_id: User for RBAC
        """
        super().__init__(connector_id, tenant_id, user_id)
        self.resources: dict[str, dict[str, Any]] = {}
        self.latency_ms = int(os.environ.get("SANDBOX_LATENCY_MS", "0"))
        self.error_rate = float(os.environ.get("SANDBOX_ERROR_RATE", "0.0"))

    def _simulate_latency(self):
        """Simulate network latency."""
        if self.latency_ms > 0:
            time.sleep(self.latency_ms / 1000.0)

    def _inject_error(self) -> Optional[ConnectorResult]:
        """Inject random error based on error rate.

        Returns:
            ConnectorResult with error if injected, None otherwise
        """
        if self.error_rate > 0 and random.random() < self.error_rate:
            return ConnectorResult(status="error", message="Simulated error injection")
        return None

    def connect(self) -> ConnectorResult:
        """Connect to sandbox (always succeeds).

        Returns:
            ConnectorResult with success status
        """
        if not self.check_rbac():
            return ConnectorResult(status="denied", message=f"User {self.user_id} lacks {self.required_role} role")

        self._simulate_latency()

        if error := self._inject_error():
            return error

        self.connected = True
        return ConnectorResult(status="success", message="Connected to sandbox")

    def disconnect(self) -> ConnectorResult:
        """Disconnect from sandbox.

        Returns:
            ConnectorResult with success status
        """
        self.connected = False
        return ConnectorResult(status="success", message="Disconnected from sandbox")

    def list_resources(self, resource_type: str, filters: Optional[dict[str, Any]] = None) -> ConnectorResult:
        """List sandbox resources.

        Args:
            resource_type: Type of resource
            filters: Optional filters (not implemented in sandbox)

        Returns:
            ConnectorResult with list of resources
        """
        if not self.check_rbac():
            return ConnectorResult(status="denied", message=f"User {self.user_id} lacks {self.required_role} role")

        if not self.connected:
            return ConnectorResult(status="error", message="Not connected")

        self._simulate_latency()

        if error := self._inject_error():
            return error

        resources = self.resources.get(resource_type, {})
        return ConnectorResult(
            status="success", data=list(resources.values()), message=f"Listed {len(resources)} {resource_type}"
        )

    def get_resource(self, resource_type: str, resource_id: str) -> ConnectorResult:
        """Get sandbox resource by ID.

        Args:
            resource_type: Type of resource
            resource_id: Resource identifier

        Returns:
            ConnectorResult with resource data or error
        """
        if not self.check_rbac():
            return ConnectorResult(status="denied", message=f"User {self.user_id} lacks {self.required_role} role")

        if not self.connected:
            return ConnectorResult(status="error", message="Not connected")

        self._simulate_latency()

        if error := self._inject_error():
            return error

        resource = self.resources.get(resource_type, {}).get(resource_id)
        if not resource:
            return ConnectorResult(status="error", message=f"Resource {resource_id} not found")

        return ConnectorResult(status="success", data=resource, message=f"Retrieved {resource_type}/{resource_id}")

    def create_resource(self, resource_type: str, payload: dict[str, Any]) -> ConnectorResult:
        """Create sandbox resource.

        Args:
            resource_type: Type of resource
            payload: Resource data (must include 'id' field)

        Returns:
            ConnectorResult with created resource
        """
        if not self.check_rbac():
            return ConnectorResult(status="denied", message=f"User {self.user_id} lacks {self.required_role} role")

        if not self.connected:
            return ConnectorResult(status="error", message="Not connected")

        self._simulate_latency()

        if error := self._inject_error():
            return error

        if "id" not in payload:
            return ConnectorResult(status="error", message="Payload must include 'id' field")

        resource_id = payload["id"]

        # Initialize resource type if needed
        if resource_type not in self.resources:
            self.resources[resource_type] = {}

        # Store resource
        self.resources[resource_type][resource_id] = payload

        return ConnectorResult(status="success", data=payload, message=f"Created {resource_type}/{resource_id}")

    def update_resource(self, resource_type: str, resource_id: str, payload: dict[str, Any]) -> ConnectorResult:
        """Update sandbox resource.

        Args:
            resource_type: Type of resource
            resource_id: Resource identifier
            payload: Updated data

        Returns:
            ConnectorResult with updated resource
        """
        if not self.check_rbac():
            return ConnectorResult(status="denied", message=f"User {self.user_id} lacks {self.required_role} role")

        if not self.connected:
            return ConnectorResult(status="error", message="Not connected")

        self._simulate_latency()

        if error := self._inject_error():
            return error

        if resource_type not in self.resources or resource_id not in self.resources[resource_type]:
            return ConnectorResult(status="error", message=f"Resource {resource_type}/{resource_id} not found")

        # Update resource
        self.resources[resource_type][resource_id].update(payload)
        updated = self.resources[resource_type][resource_id]

        return ConnectorResult(status="success", data=updated, message=f"Updated {resource_type}/{resource_id}")

    def delete_resource(self, resource_type: str, resource_id: str) -> ConnectorResult:
        """Delete sandbox resource.

        Args:
            resource_type: Type of resource
            resource_id: Resource identifier

        Returns:
            ConnectorResult with deletion status
        """
        if not self.check_rbac():
            return ConnectorResult(status="denied", message=f"User {self.user_id} lacks {self.required_role} role")

        if not self.connected:
            return ConnectorResult(status="error", message="Not connected")

        self._simulate_latency()

        if error := self._inject_error():
            return error

        if resource_type not in self.resources or resource_id not in self.resources[resource_type]:
            return ConnectorResult(status="error", message=f"Resource {resource_type}/{resource_id} not found")

        # Delete resource
        del self.resources[resource_type][resource_id]

        return ConnectorResult(status="success", message=f"Deleted {resource_type}/{resource_id}")
