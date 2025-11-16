"""Workspace validation and isolation utilities for Sprint 60 Phase 2.

Centralizes workspace ID validation and enforcement to prevent duplication
and ensure consistent security checks across all endpoints.

References:
- SPRINT_60_PHASE_2_EPIC.md: Phase 2 implementation requirements
- SECURITY_TICKET_S60_WEBAPI.md: Workspace isolation vulnerabilities
"""

import re

from fastapi import HTTPException, Request, status

# Workspace ID regex pattern (matches Sprint 60 Phase 1 validation)
# Allows alphanumeric, hyphens, underscores; 1-32 chars; lowercase only
_WORKSPACE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def get_authenticated_workspace(request: Request) -> str:
    """Extract and validate authenticated workspace from request state.

    The @require_scopes decorator populates request.state.workspace_id from
    the API key's metadata. This function validates that it's present and
    properly formatted.

    Args:
        request: FastAPI Request object with populated state

    Returns:
        workspace_id: The authenticated workspace identifier

    Raises:
        HTTPException: 403 Forbidden if workspace missing or invalid

    Sprint 60 Phase 2: Centralized validation for workspace isolation enforcement
    """
    workspace_id = getattr(getattr(request, "state", None), "workspace_id", None)

    if not workspace_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Workspace not found in authentication context"
        )

    # Validate format matches expected pattern
    if not _WORKSPACE_ID_PATTERN.fullmatch(workspace_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid workspace identifier format")

    return workspace_id


def ensure_same_workspace(auth_workspace_id: str, provided_workspace_id: str | None) -> None:
    """Enforce that provided workspace_id matches authenticated workspace.

    If a client provides a workspace_id (via query param or request body),
    it must match the authenticated workspace. This prevents cross-workspace
    access attempts (CRITICAL-2, CRITICAL-3, HIGH-4 vulnerabilities).

    Args:
        auth_workspace_id: Workspace from authentication context
        provided_workspace_id: Optional workspace from request (query/body)

    Raises:
        HTTPException: 403 Forbidden if provided workspace doesn't match auth

    Sprint 60 Phase 2: Centralized RBAC enforcement across endpoints
    """
    if provided_workspace_id and provided_workspace_id != auth_workspace_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Cannot access resources from other workspaces"
        )
