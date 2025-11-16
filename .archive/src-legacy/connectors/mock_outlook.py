"""Mock Outlook connector for testing email integration.

Simulates Outlook/Exchange operations using local JSONL storage.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .base import Connector, ConnectorResult


class MockOutlookConnector(Connector):
    """Mock connector for Outlook/Exchange email operations.

    Uses local JSONL file to simulate email storage.
    Validates OUTLOOK_TOKEN for configuration (not used for auth).
    """

    def __init__(self, connector_id: str, tenant_id: str, user_id: str):
        """Initialize mock Outlook connector.

        Args:
            connector_id: Connector identifier
            tenant_id: Tenant for isolation
            user_id: User for RBAC
        """
        super().__init__(connector_id, tenant_id, user_id)
        self.storage_path = Path("logs") / f"mock_outlook_{tenant_id}.jsonl"
        self.dry_run = os.environ.get("DRY_RUN", "true").lower() == "true"
        self.token = os.environ.get("OUTLOOK_TOKEN", "placeholder")

    def connect(self) -> ConnectorResult:
        """Connect to mock Outlook (validates token and permissions).

        Returns:
            ConnectorResult with status
        """
        if not self.check_rbac():
            return ConnectorResult(status="denied", message=f"User {self.user_id} lacks {self.required_role} role")

        if not self.token or self.token == "":
            return ConnectorResult(status="error", message="OUTLOOK_TOKEN not configured")

        # Ensure storage directory exists
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        self.connected = True
        mode = "DRY-RUN" if self.dry_run else "LIVE"
        return ConnectorResult(status="success", message=f"Connected to mock Outlook ({mode})")

    def disconnect(self) -> ConnectorResult:
        """Disconnect from mock Outlook.

        Returns:
            ConnectorResult with status
        """
        self.connected = False
        return ConnectorResult(status="success", message="Disconnected from mock Outlook")

    def list_resources(self, resource_type: str, filters: Optional[dict[str, Any]] = None) -> ConnectorResult:
        """List Outlook resources (messages, folders, contacts).

        Args:
            resource_type: Type of resource (messages, folders, contacts)
            filters: Optional filters (e.g., {"folder": "Inbox", "unread": true})

        Returns:
            ConnectorResult with list of resources
        """
        if not self.check_rbac():
            return ConnectorResult(status="denied", message=f"User {self.user_id} lacks {self.required_role} role")

        if not self.connected:
            return ConnectorResult(status="error", message="Not connected")

        if not self.storage_path.exists():
            return ConnectorResult(status="success", data=[], message=f"No {resource_type} found")

        resources = []
        with open(self.storage_path, encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line.strip())
                if entry.get("type") == resource_type:
                    # Apply filters if provided
                    if filters:
                        match = all(entry.get("data", {}).get(k) == v for k, v in filters.items())
                        if not match:
                            continue
                    resources.append(entry["data"])

        # Last-wins: deduplicate by ID
        unique = {}
        for resource in resources:
            unique[resource["id"]] = resource

        return ConnectorResult(
            status="success", data=list(unique.values()), message=f"Listed {len(unique)} {resource_type}"
        )

    def get_resource(self, resource_type: str, resource_id: str) -> ConnectorResult:
        """Get specific Outlook resource by ID.

        Args:
            resource_type: Type of resource
            resource_id: Resource identifier

        Returns:
            ConnectorResult with resource data
        """
        if not self.check_rbac():
            return ConnectorResult(status="denied", message=f"User {self.user_id} lacks {self.required_role} role")

        if not self.connected:
            return ConnectorResult(status="error", message="Not connected")

        if not self.storage_path.exists():
            return ConnectorResult(status="error", message=f"Resource {resource_id} not found")

        # Find latest version of resource
        latest = None
        with open(self.storage_path, encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line.strip())
                if entry.get("type") == resource_type and entry.get("data", {}).get("id") == resource_id:
                    latest = entry["data"]

        if not latest:
            return ConnectorResult(status="error", message=f"Resource {resource_type}/{resource_id} not found")

        return ConnectorResult(status="success", data=latest, message=f"Retrieved {resource_type}/{resource_id}")

    def create_resource(self, resource_type: str, payload: dict[str, Any]) -> ConnectorResult:
        """Create Outlook resource (send email, create folder, add contact).

        Args:
            resource_type: Type of resource
            payload: Resource data

        Returns:
            ConnectorResult with created resource
        """
        if not self.check_rbac():
            return ConnectorResult(status="denied", message=f"User {self.user_id} lacks {self.required_role} role")

        if not self.connected:
            return ConnectorResult(status="error", message="Not connected")

        # Generate ID if not provided
        if "id" not in payload:
            payload["id"] = f"{resource_type}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Add timestamp
        payload["created_at"] = datetime.now().isoformat()

        if self.dry_run:
            return ConnectorResult(
                status="success", data=payload, message=f"[DRY-RUN] Would create {resource_type}/{payload['id']}"
            )

        # Append to JSONL
        entry = {"type": resource_type, "data": payload, "operation": "create", "timestamp": payload["created_at"]}

        with open(self.storage_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        return ConnectorResult(status="success", data=payload, message=f"Created {resource_type}/{payload['id']}")

    def update_resource(self, resource_type: str, resource_id: str, payload: dict[str, Any]) -> ConnectorResult:
        """Update Outlook resource.

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

        # Verify resource exists
        existing = self.get_resource(resource_type, resource_id)
        if existing.status != "success":
            return existing

        # Merge updates
        updated = {**existing.data, **payload, "id": resource_id, "updated_at": datetime.now().isoformat()}

        if self.dry_run:
            return ConnectorResult(
                status="success", data=updated, message=f"[DRY-RUN] Would update {resource_type}/{resource_id}"
            )

        # Append update to JSONL
        entry = {"type": resource_type, "data": updated, "operation": "update", "timestamp": updated["updated_at"]}

        with open(self.storage_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        return ConnectorResult(status="success", data=updated, message=f"Updated {resource_type}/{resource_id}")

    def delete_resource(self, resource_type: str, resource_id: str) -> ConnectorResult:
        """Delete Outlook resource.

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

        # Verify resource exists
        existing = self.get_resource(resource_type, resource_id)
        if existing.status != "success":
            return existing

        if self.dry_run:
            return ConnectorResult(status="success", message=f"[DRY-RUN] Would delete {resource_type}/{resource_id}")

        # Append deletion to JSONL (tombstone)
        entry = {
            "type": resource_type,
            "data": {"id": resource_id, "deleted": True},
            "operation": "delete",
            "timestamp": datetime.now().isoformat(),
        }

        with open(self.storage_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        return ConnectorResult(status="success", message=f"Deleted {resource_type}/{resource_id}")
