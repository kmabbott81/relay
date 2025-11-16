"""Blue/Green deployment traffic manager with canary releases.

Manages deployment slots, canary weight progression, and rollback logic with
full audit trail and RBAC enforcement.
"""

import json
import os
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path


class DeploymentState(str, Enum):
    """Deployment state machine states."""

    IDLE = "idle"
    GREEN_PROVISIONED = "green_provisioned"
    CANARY = "canary"
    GREEN_LIVE = "green_live"
    ROLLBACK_IN_PROGRESS = "rollback_in_progress"


class DeploymentError(Exception):
    """Raised when deployment operation fails."""

    pass


class TrafficManager:
    """Manages blue/green deployment traffic splitting and state."""

    def __init__(self):
        """Initialize traffic manager."""
        self.state = DeploymentState.IDLE
        self.blue_image = None
        self.green_image = None
        self.canary_weight = 0
        self.audit_log_path = Path("logs/deploy_audit.log")
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)

        # RBAC check
        self._check_deploy_permission()

    def _check_deploy_permission(self):
        """Verify user has deploy permissions via DEPLOY_RBAC_ROLE."""
        deploy_role = os.getenv("DEPLOY_RBAC_ROLE", "")
        if deploy_role not in ["Deployer", "Admin"]:
            raise PermissionError(
                f"DEPLOY_RBAC_ROLE '{deploy_role}' not authorized for deployments. " f"Must be 'Deployer' or 'Admin'."
            )

    def _audit(self, action: str, metadata: dict):
        """Write audit event to log file and stdout."""
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "state": self.state,
            "blue_image": self.blue_image,
            "green_image": self.green_image,
            "canary_weight": self.canary_weight,
            "user": os.getenv("USER", "unknown"),
            "deploy_role": os.getenv("DEPLOY_RBAC_ROLE", "unknown"),
            **metadata,
        }

        # Write to file
        with open(self.audit_log_path, "a") as f:
            f.write(json.dumps(event) + "\n")

        # Write to stdout
        print(json.dumps(event), file=sys.stdout)

    def provision_green(self, image_tag: str):
        """
        Provision green deployment slot with new image.

        Args:
            image_tag: Docker image tag for green deployment

        Raises:
            DeploymentError: If state invalid or provisioning fails
        """
        if self.state not in [DeploymentState.IDLE, DeploymentState.GREEN_LIVE]:
            raise DeploymentError(f"Cannot provision green from state {self.state}")

        # If green is live, it becomes the new blue
        if self.state == DeploymentState.GREEN_LIVE:
            self.blue_image = self.green_image

        self.green_image = image_tag
        self.state = DeploymentState.GREEN_PROVISIONED
        self.canary_weight = 0

        self._audit("provision_green", {"image_tag": image_tag})

    def start_canary(self, weight: int):
        """
        Start canary release with specified traffic weight.

        Args:
            weight: Percentage of traffic to route to green (0-100)

        Raises:
            DeploymentError: If state invalid or weight invalid
        """
        if self.state != DeploymentState.GREEN_PROVISIONED:
            raise DeploymentError(f"Cannot start canary from state {self.state}")

        if not 0 <= weight <= 100:
            raise DeploymentError(f"Invalid canary weight {weight} (must be 0-100)")

        self.canary_weight = weight
        self.state = DeploymentState.CANARY

        self._audit("start_canary", {"weight": weight})

    def increase_weight(self, weight: int):
        """
        Increase canary traffic weight.

        Args:
            weight: New percentage of traffic to route to green (0-100)

        Raises:
            DeploymentError: If state invalid or weight invalid
        """
        if self.state != DeploymentState.CANARY:
            raise DeploymentError(f"Cannot increase weight from state {self.state}")

        if weight <= self.canary_weight:
            raise DeploymentError(f"New weight {weight}% must be greater than current {self.canary_weight}%")

        if not 0 <= weight <= 100:
            raise DeploymentError(f"Invalid canary weight {weight} (must be 0-100)")

        old_weight = self.canary_weight
        self.canary_weight = weight

        self._audit("increase_weight", {"old_weight": old_weight, "new_weight": weight})

    def promote_green(self):
        """
        Promote green to live (100% traffic).

        Raises:
            DeploymentError: If state invalid
        """
        if self.state != DeploymentState.CANARY:
            raise DeploymentError(f"Cannot promote green from state {self.state}")

        self.blue_image = self.green_image  # Old green becomes new blue
        self.canary_weight = 100
        self.state = DeploymentState.GREEN_LIVE

        self._audit("promote_green", {"new_blue": self.blue_image})

    def rollback_to_blue(self, reason: str):
        """
        Rollback to blue deployment (0% traffic to green).

        Args:
            reason: Reason for rollback

        Raises:
            DeploymentError: If state invalid
        """
        if self.state not in [DeploymentState.CANARY, DeploymentState.GREEN_PROVISIONED]:
            raise DeploymentError(f"Cannot rollback from state {self.state}")

        old_state = self.state
        old_weight = self.canary_weight

        self.state = DeploymentState.ROLLBACK_IN_PROGRESS
        self.canary_weight = 0

        self._audit("rollback_to_blue", {"reason": reason, "old_state": old_state, "old_weight": old_weight})

        # Return to idle after rollback
        self.state = DeploymentState.IDLE
        self.green_image = None

    def get_status(self) -> dict:
        """
        Get current deployment status.

        Returns:
            Dictionary with current state and configuration
        """
        return {
            "state": self.state,
            "blue_image": self.blue_image,
            "green_image": self.green_image,
            "canary_weight": self.canary_weight,
            "traffic_split": {
                "blue": 100 - self.canary_weight,
                "green": self.canary_weight,
            },
        }
