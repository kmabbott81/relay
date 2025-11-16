"""
Compliance Module - Sprint 33A

Provides GDPR-style data export, deletion, legal holds, and retention enforcement.
All operations are tenant-scoped, RBAC-enforced, and fully audited.
"""

from .api import delete_tenant, enforce_retention, export_tenant
from .holds import apply_legal_hold, current_holds, is_on_hold, release_legal_hold

__all__ = [
    "export_tenant",
    "delete_tenant",
    "enforce_retention",
    "apply_legal_hold",
    "release_legal_hold",
    "is_on_hold",
    "current_holds",
]
