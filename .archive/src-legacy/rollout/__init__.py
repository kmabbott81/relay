"""Rollout management for gradual feature deployment.

Sprint 54: Rollout seams for Gmail rich email features.

This module provides a clean interface for percentage-based feature rollout
with SLO-based policy decisions and audit logging.
"""

from .audit import append_rollout_log
from .interface import RolloutGate
from .minimal_gate import MinimalGate
from .policy import Recommendation, gmail_policy

__all__ = [
    "RolloutGate",
    "MinimalGate",
    "Recommendation",
    "gmail_policy",
    "append_rollout_log",
]
