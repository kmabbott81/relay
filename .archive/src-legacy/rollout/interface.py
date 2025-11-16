"""Rollout gate interface (stable contract).

Sprint 54: Protocol for feature rollout gating.

This interface defines the stable call surface for rollout decisions.
Implementations can be swapped (MinimalGate → ControllerGate) without
touching callers.
"""

from typing import Protocol


class RolloutGate(Protocol):
    """Protocol for feature rollout gating.

    Implementations provide:
    - allow(): Boolean decision for a single request
    - percent(): Current rollout percentage for a feature

    Example:
        gate = MinimalGate(redis_client)

        # Check if feature is enabled for this request
        if gate.allow("google", {"actor_id": "user_123"}):
            execute_gmail_send(...)
        else:
            raise ValueError("Feature not rolled out to this user")

        # Get current rollout percentage
        pct = gate.percent("google")
        print(f"Gmail rollout: {pct}%")
    """

    def allow(self, feature: str, context: dict) -> bool:
        """Decide if feature is allowed for this request.

        Args:
            feature: Feature name (e.g., "google")
            context: Request context (e.g., {"actor_id": "..."})

        Returns:
            True if feature should be enabled for this request
        """
        ...

    def percent(self, feature: str) -> int:
        """Get current rollout percentage for feature.

        Args:
            feature: Feature name (e.g., "google")

        Returns:
            Current rollout percentage (0-100)
        """
        ...
