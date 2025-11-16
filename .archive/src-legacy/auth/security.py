"""Authentication and authorization security.

Sprint 51 Phase 1: API key auth + RBAC + scopes.
"""
import json
from functools import wraps
from typing import Optional
from uuid import UUID

import argon2
from fastapi import HTTPException, Request

from relay_ai.db.connection import get_connection

# Role to scopes mapping (matches CLI)
ROLE_SCOPES = {
    "admin": ["actions:preview", "actions:execute", "audit:read"],
    "developer": ["actions:preview", "actions:execute"],
    "viewer": ["actions:preview"],
}


def parse_bearer_token(request: Request) -> Optional[str]:
    """Extract Bearer token from Authorization header.

    Returns:
        Token string or None if not present/malformed
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None

    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    return parts[1]


async def load_api_key(token: str) -> Optional[tuple[UUID, UUID, list[str]]]:
    """Verify API key and load metadata.

    Uses constant-time Argon2 verification for security.

    Args:
        token: Plaintext API key from Authorization header

    Returns:
        Tuple of (key_id, workspace_id, scopes) or None if invalid/revoked
    """
    async with get_connection() as conn:
        # Fetch all non-revoked keys (we need to check hash)
        # In production with many keys, consider adding key_prefix index
        keys = await conn.fetch(
            """
            SELECT id, workspace_id, key_hash, scopes
            FROM api_keys
            WHERE revoked_at IS NULL
            """
        )

    ph = argon2.PasswordHasher()

    # Check each key with constant-time comparison
    for key_record in keys:
        try:
            # Verify hash (raises if mismatch)
            ph.verify(key_record["key_hash"], token)

            # Hash matches - return key metadata
            key_id = key_record["id"]
            workspace_id = key_record["workspace_id"]
            scopes = json.loads(key_record["scopes"])

            return (key_id, workspace_id, scopes)

        except argon2.exceptions.VerifyMismatchError:
            # This key doesn't match - try next
            continue
        except Exception:
            # Unexpected error (corrupt hash?) - skip this key
            continue

    # No matching key found
    return None


async def load_user_scopes(user_id: str, workspace_id: UUID) -> list[str]:
    """Load scopes for a user based on their role assignment.

    Args:
        user_id: User identifier
        workspace_id: Workspace UUID

    Returns:
        List of scopes derived from role, empty list if no role
    """
    async with get_connection() as conn:
        role_record = await conn.fetchrow(
            """
            SELECT role
            FROM roles
            WHERE workspace_id = $1 AND user_id = $2
            LIMIT 1
            """,
            workspace_id,
            user_id,
        )

    if not role_record:
        return []

    role = role_record["role"]
    return ROLE_SCOPES.get(role, [])


def require_scopes(required_scopes: list[str]):
    """Decorator to enforce scope requirements on endpoints.

    Usage:
        @app.post("/actions/preview")
        @require_scopes(["actions:preview"])
        async def preview_action(request: Request, ...):
            ...

    Args:
        required_scopes: List of scopes required (ANY match grants access)

    Raises:
        HTTPException: 401 if no auth, 403 if insufficient scopes
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Find Request object in args/kwargs
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if request is None and "request" in kwargs:
                request = kwargs["request"]

            if request is None:
                raise HTTPException(
                    status_code=500,
                    detail="Internal error: Request object not found in require_scopes",
                )

            # Try API key authentication
            token = parse_bearer_token(request)
            if token:
                # Special case: Allow demo preview key for dev UI (Sprint 55 Week 3)
                # This bypasses database authentication for the action-runner.html dev UI
                if token == "relay_sk_demo_preview_key":
                    # Grant preview-only scopes for demo mode
                    request.state.actor_type = "demo"
                    request.state.actor_id = "demo-user"
                    request.state.workspace_id = "demo-workspace-001"
                    request.state.scopes = ["actions:preview"]

                    # Check if demo key has required scope
                    if not any(scope in ["actions:preview"] for scope in required_scopes):
                        raise HTTPException(
                            status_code=403,
                            detail=f"Demo key only has preview scope. Required: {required_scopes}",
                        )

                    # Authorized - proceed with demo auth
                    return await func(*args, **kwargs)

                # Normal API key authentication
                result = await load_api_key(token)
                if not result:
                    raise HTTPException(
                        status_code=401,
                        detail="Invalid or revoked API key",
                    )

                key_id, workspace_id, scopes = result

                # Store auth context for downstream use (audit logging)
                request.state.actor_type = "api_key"
                request.state.actor_id = str(key_id)
                request.state.workspace_id = workspace_id
                request.state.scopes = scopes

                # Check if any required scope is present
                if not any(scope in scopes for scope in required_scopes):
                    raise HTTPException(
                        status_code=403,
                        detail=f"Insufficient permissions. Required scopes: {required_scopes}",
                    )

                # Authorized - proceed
                return await func(*args, **kwargs)

            # Try session/user authentication (dev/staging)
            # For now, check if user_id exists in request.state (set by session middleware)
            if hasattr(request.state, "user_id") and hasattr(request.state, "workspace_id"):
                user_id = request.state.user_id
                workspace_id = request.state.workspace_id

                # Load user scopes from roles table
                scopes = await load_user_scopes(user_id, workspace_id)

                request.state.actor_type = "user"
                request.state.actor_id = user_id
                request.state.scopes = scopes

                # Check if any required scope is present
                if not any(scope in scopes for scope in required_scopes):
                    raise HTTPException(
                        status_code=403,
                        detail=f"Insufficient permissions. Required scopes: {required_scopes}",
                    )

                # Authorized - proceed
                return await func(*args, **kwargs)

            # No authentication method succeeded
            raise HTTPException(
                status_code=401,
                detail="Missing or invalid authentication. Provide Authorization: Bearer <api_key> header.",
            )

        return wrapper

    return decorator
