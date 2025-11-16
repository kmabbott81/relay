"""
Classification module for data labeling and access control.

Sprint 33B: Label-based access control with clearances.
"""

from .labels import can_access, effective_label, parse_labels
from .policy import export_allowed, label_for_artifact, redact_for_label

__all__ = [
    "parse_labels",
    "can_access",
    "effective_label",
    "label_for_artifact",
    "export_allowed",
    "redact_for_label",
]
