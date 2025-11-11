"""Audit logger with redaction for action preview/execute.

Sprint 51 Phase 1: Secure audit logging.
"""
import hashlib
import json
from typing import Optional
from uuid import UUID

from relay_ai.db.connection import get_connection


def canonical_json(obj) -> str:
    """Convert object to canonical JSON (stable key order, UTF-8).

    Args:
        obj: Python object to serialize

    Returns:
        JSON string with sorted keys
    """
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def sha256_hex(data: str) -> str:
    """Hash string with SHA256 and return hex digest.

    Args:
        data: String to hash

    Returns:
        Hex digest of hash
    """
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


async def write_audit(
    run_id: Optional[str],
    request_id: str,
    workspace_id: UUID,
    actor_type: str,
    actor_id: str,
    provider: str,
    action_id: str,
    preview_id: Optional[str],
    idempotency_key: Optional[str],
    signature_present: bool,
    params: dict,
    status: str,
    error_reason: str,
    http_status: int,
    duration_ms: int,
):
    """Write audit log entry for action preview or execute.

    Implements redaction: only params_hash and params_prefix64 stored.

    Args:
        run_id: Execution run ID (null for preview)
        request_id: X-Request-ID from telemetry middleware
        workspace_id: Workspace UUID
        actor_type: 'api_key' or 'user'
        actor_id: Key ID or user ID
        provider: Action provider (e.g., 'independent')
        action_id: Full action ID (e.g., 'webhook.save')
        preview_id: Preview ID (for execute) or None
        idempotency_key: Idempotency key if provided
        signature_present: Whether X-Signature header was present
        params: Action parameters (will be redacted)
        status: 'ok' or 'error'
        error_reason: Error reason enum value
        http_status: HTTP status code
        duration_ms: Request duration in milliseconds
    """
    # Redaction: hash and prefix only
    params_canonical = canonical_json(params)
    params_hash = sha256_hex(params_canonical)
    params_prefix64 = params_canonical[:64]

    # Hash idempotency key if present
    idempotency_key_hash = sha256_hex(idempotency_key) if idempotency_key else None

    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO action_audit (
                run_id, request_id, workspace_id, actor_type, actor_id,
                provider, action_id, preview_id, idempotency_key_hash,
                signature_present, params_hash, params_prefix64,
                status, error_reason, http_status, duration_ms
            )
            VALUES ($1, $2, $3, $4::actor_type_enum, $5, $6, $7, $8, $9, $10, $11, $12, $13::audit_status_enum, $14::error_reason_enum, $15, $16)
            """,
            run_id,
            request_id,
            workspace_id,
            actor_type,
            actor_id,
            provider,
            action_id,
            preview_id,
            idempotency_key_hash,
            signature_present,
            params_hash,
            params_prefix64,
            status,
            error_reason,
            http_status,
            duration_ms,
        )
