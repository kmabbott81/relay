"""Base connector interface for external system integrations.

All connectors must inherit from Connector and implement abstract methods.
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from ..security.teams import get_team_role


@dataclass
class ConnectorResult:
    """Result from connector operation.

    Attributes:
        status: Operation status (success, error, denied)
        data: Result data (if successful)
        message: Human-readable message
    """

    status: str  # success, error, denied
    data: Optional[Any] = None
    message: str = ""


class Connector(ABC):
    """Abstract base class for external system connectors.

    All connectors must implement lifecycle and CRUD methods.
    RBAC enforcement via CONNECTOR_RBAC_ROLE environment variable.
    """

    def __init__(self, connector_id: str, tenant_id: str, user_id: str):
        """Initialize connector.

        Args:
            connector_id: Unique connector identifier
            tenant_id: Tenant identifier for isolation
            user_id: User identifier for RBAC
        """
        self.connector_id = connector_id
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.connected = False

        # RBAC enforcement
        self.required_role = os.environ.get("CONNECTOR_RBAC_ROLE", "Operator")

    def check_rbac(self) -> bool:
        """Check if user has required role for connector operations.

        Returns:
            True if user has sufficient role, False otherwise
        """
        # Use team role (tenant_id as team_id for now)
        user_role = get_team_role(self.user_id, self.tenant_id)
        if not user_role:
            return False

        # Role hierarchy: Viewer(0) < Author(1) < Operator(2) < Auditor(3) < Compliance(4) < Admin(5)
        role_levels = {
            "Viewer": 0,
            "Author": 1,
            "Operator": 2,
            "Auditor": 3,
            "Compliance": 4,
            "Admin": 5,
        }

        user_level = role_levels.get(user_role, 0)
        required_level = role_levels.get(self.required_role, 2)

        return user_level >= required_level

    @abstractmethod
    def connect(self) -> ConnectorResult:
        """Establish connection to external system.

        Returns:
            ConnectorResult with status and message
        """
        pass

    @abstractmethod
    def disconnect(self) -> ConnectorResult:
        """Disconnect from external system.

        Returns:
            ConnectorResult with status and message
        """
        pass

    @abstractmethod
    def list_resources(self, resource_type: str, filters: Optional[dict[str, Any]] = None) -> ConnectorResult:
        """List resources of given type.

        Args:
            resource_type: Type of resource to list (e.g., "messages", "channels")
            filters: Optional filters to apply

        Returns:
            ConnectorResult with list of resources in data field
        """
        pass

    @abstractmethod
    def get_resource(self, resource_type: str, resource_id: str) -> ConnectorResult:
        """Get specific resource by ID.

        Args:
            resource_type: Type of resource
            resource_id: Unique resource identifier

        Returns:
            ConnectorResult with resource data
        """
        pass

    @abstractmethod
    def create_resource(self, resource_type: str, payload: dict[str, Any]) -> ConnectorResult:
        """Create new resource.

        Args:
            resource_type: Type of resource to create
            payload: Resource data

        Returns:
            ConnectorResult with created resource data
        """
        pass

    @abstractmethod
    def update_resource(self, resource_type: str, resource_id: str, payload: dict[str, Any]) -> ConnectorResult:
        """Update existing resource.

        Args:
            resource_type: Type of resource
            resource_id: Resource identifier
            payload: Updated data

        Returns:
            ConnectorResult with updated resource data
        """
        pass

    @abstractmethod
    def delete_resource(self, resource_type: str, resource_id: str) -> ConnectorResult:
        """Delete resource.

        Args:
            resource_type: Type of resource
            resource_id: Resource identifier

        Returns:
            ConnectorResult with deletion status
        """
        pass
