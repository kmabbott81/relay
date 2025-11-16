"""
Checkpoint Store (Sprint 31 + 34A)

Manages human-in-the-loop checkpoints for DAG execution.
Records approvals, rejections, and expirations to JSONL.

Sprint 34A: Added multi-sign (M-of-N) approval support.
"""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable


def get_checkpoints_path() -> Path:
    """Get checkpoints log path."""
    return Path(os.getenv("CHECKPOINTS_PATH", "logs/checkpoints.jsonl"))


def get_state_store_path() -> Path:
    """Get orchestrator state store path."""
    return Path(os.getenv("STATE_STORE_PATH", "logs/orchestrator_state.jsonl"))


def get_expiry_hours() -> int:
    """Get approval expiration hours from env."""
    return int(os.getenv("APPROVAL_EXPIRES_H", "72"))


def create_checkpoint(
    checkpoint_id: str,
    dag_run_id: str,
    task_id: str,
    tenant: str,
    prompt: str,
    required_role: str | None = None,
    inputs: dict | None = None,
    required_signers: list[str] | None = None,
    min_signatures: int | None = None,
) -> dict[str, Any]:
    """
    Create a new checkpoint awaiting approval.

    Args:
        checkpoint_id: Unique checkpoint identifier
        dag_run_id: DAG run this checkpoint belongs to
        task_id: Task ID in the DAG
        tenant: Tenant identifier
        prompt: Human-readable approval prompt
        required_role: RBAC role required to approve (single-sign)
        inputs: Expected input schema for approval
        required_signers: List of users/roles required for multi-sign (Sprint 34A)
        min_signatures: Minimum signatures required (M-of-N) (Sprint 34A)

    Returns:
        Checkpoint record
    """
    checkpoints_path = get_checkpoints_path()
    checkpoints_path.parent.mkdir(parents=True, exist_ok=True)

    expires_at = datetime.now(UTC) + timedelta(hours=get_expiry_hours())

    checkpoint = {
        "event": "checkpoint_created",
        "checkpoint_id": checkpoint_id,
        "dag_run_id": dag_run_id,
        "task_id": task_id,
        "tenant": tenant,
        "prompt": prompt,
        "required_role": required_role or os.getenv("APPROVER_RBAC_ROLE", "Operator"),
        "inputs": inputs or {},
        "status": "pending",
        "created_at": datetime.now(UTC).isoformat(),
        "expires_at": expires_at.isoformat(),
        "approved_by": None,
        "approved_at": None,
        "rejected_by": None,
        "rejected_at": None,
        "rejection_reason": None,
        "approval_data": None,
        # Sprint 34A: Multi-sign fields
        "required_signers": required_signers or [],
        "min_signatures": min_signatures or 1,
        "approvals": [],
    }

    with open(checkpoints_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(checkpoint) + "\n")

    return checkpoint


def list_checkpoints(tenant: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    """
    List checkpoints with optional filters.

    Args:
        tenant: Filter by tenant (None for all)
        status: Filter by status (pending, approved, rejected, expired)

    Returns:
        List of checkpoint records (most recent first)
    """
    checkpoints_path = get_checkpoints_path()

    if not checkpoints_path.exists():
        return []

    # Build index: checkpoint_id -> latest record
    checkpoints: dict[str, dict[str, Any]] = {}

    with open(checkpoints_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                record = json.loads(line)
                checkpoint_id = record["checkpoint_id"]

                # Always keep latest record (last one wins in JSONL append-only log)
                checkpoints[checkpoint_id] = record

    # Filter
    results = list(checkpoints.values())

    if tenant:
        results = [c for c in results if c.get("tenant") == tenant]

    if status:
        results = [c for c in results if c.get("status") == status]

    # Sort by created_at descending
    results.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    return results


def get_checkpoint(checkpoint_id: str) -> dict[str, Any] | None:
    """
    Get latest state of a checkpoint.

    Args:
        checkpoint_id: Checkpoint identifier

    Returns:
        Checkpoint record or None if not found
    """
    checkpoints = list_checkpoints()

    for checkpoint in checkpoints:
        if checkpoint["checkpoint_id"] == checkpoint_id:
            return checkpoint

    return None


def approve_checkpoint(checkpoint_id: str, approved_by: str, approval_data: dict | None = None) -> dict[str, Any]:
    """
    Approve a checkpoint.

    Args:
        checkpoint_id: Checkpoint identifier
        approved_by: User/role approving
        approval_data: Optional key-value data provided during approval

    Returns:
        Updated checkpoint record

    Raises:
        ValueError: If checkpoint not found or already approved/rejected/expired
    """
    checkpoint = get_checkpoint(checkpoint_id)

    if not checkpoint:
        raise ValueError(f"Checkpoint {checkpoint_id} not found")

    if checkpoint["status"] != "pending":
        raise ValueError(f"Checkpoint {checkpoint_id} is {checkpoint['status']}, cannot approve")

    # Check expiration
    expires_at = datetime.fromisoformat(checkpoint["expires_at"])
    if datetime.now(UTC) > expires_at:
        raise ValueError(f"Checkpoint {checkpoint_id} has expired")

    checkpoints_path = get_checkpoints_path()

    updated = checkpoint.copy()
    updated["event"] = "checkpoint_approved"
    updated["status"] = "approved"
    updated["approved_by"] = approved_by
    updated["approved_at"] = datetime.now(UTC).isoformat()
    updated["approval_data"] = approval_data or {}

    with open(checkpoints_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(updated) + "\n")

    return updated


def reject_checkpoint(checkpoint_id: str, rejected_by: str, reason: str) -> dict[str, Any]:
    """
    Reject a checkpoint.

    Args:
        checkpoint_id: Checkpoint identifier
        rejected_by: User/role rejecting
        reason: Rejection reason

    Returns:
        Updated checkpoint record

    Raises:
        ValueError: If checkpoint not found or already approved/rejected/expired
    """
    checkpoint = get_checkpoint(checkpoint_id)

    if not checkpoint:
        raise ValueError(f"Checkpoint {checkpoint_id} not found")

    if checkpoint["status"] != "pending":
        raise ValueError(f"Checkpoint {checkpoint_id} is {checkpoint['status']}, cannot reject")

    checkpoints_path = get_checkpoints_path()

    updated = checkpoint.copy()
    updated["event"] = "checkpoint_rejected"
    updated["status"] = "rejected"
    updated["rejected_by"] = rejected_by
    updated["rejected_at"] = datetime.now(UTC).isoformat()
    updated["rejection_reason"] = reason
    updated["reject_reason"] = reason  # Alias for test compatibility

    with open(checkpoints_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(updated) + "\n")

    return updated


def expire_pending(now: datetime | None = None) -> list[dict[str, Any]]:
    """
    Expire pending checkpoints that have passed their expiration time.

    Args:
        now: Current time (defaults to now UTC)

    Returns:
        List of expired checkpoint records
    """
    if now is None:
        now = datetime.now(UTC)

    pending = list_checkpoints(status="pending")
    expired = []

    for checkpoint in pending:
        expires_at_str = checkpoint["expires_at"]
        # Ensure timezone-aware comparison
        expires_at = datetime.fromisoformat(expires_at_str)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        if now >= expires_at:
            checkpoints_path = get_checkpoints_path()

            updated = checkpoint.copy()
            updated["event"] = "checkpoint_expired"
            updated["status"] = "expired"
            updated["expired_at"] = now.isoformat()

            with open(checkpoints_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(updated) + "\n")

            expired.append(updated)

    return expired


def write_resume_token(dag_run_id: str, next_task_id: str, tenant: str) -> None:
    """
    Write a resume token to state store.

    Args:
        dag_run_id: DAG run identifier
        next_task_id: Task to resume from
        tenant: Tenant identifier
    """
    state_store_path = get_state_store_path()
    state_store_path.parent.mkdir(parents=True, exist_ok=True)

    token = {
        "event": "resume_token",
        "dag_run_id": dag_run_id,
        "next_task_id": next_task_id,
        "tenant": tenant,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    with open(state_store_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(token) + "\n")


def get_resume_token(dag_run_id: str) -> dict[str, Any] | None:
    """
    Get resume token for a DAG run.

    Args:
        dag_run_id: DAG run identifier

    Returns:
        Resume token or None if not found
    """
    state_store_path = get_state_store_path()

    if not state_store_path.exists():
        return None

    # Read latest resume token for this dag_run_id
    token = None

    with open(state_store_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                record = json.loads(line)

                if record.get("event") == "resume_token" and record.get("dag_run_id") == dag_run_id:
                    token = record

    return token


def add_signature(checkpoint_id: str, user: str, approval_data: dict | None = None) -> dict[str, Any]:
    """
    Add a signature to a multi-sign checkpoint (Sprint 34A).

    Args:
        checkpoint_id: Checkpoint identifier
        user: User providing signature
        approval_data: Optional data provided with signature

    Returns:
        Updated checkpoint record

    Raises:
        ValueError: If checkpoint not found or not pending

    Example:
        >>> add_signature("chk-001", "alice", {"comment": "LGTM"})
    """
    checkpoint = get_checkpoint(checkpoint_id)

    if not checkpoint:
        raise ValueError(f"Checkpoint {checkpoint_id} not found")

    if checkpoint["status"] != "pending":
        raise ValueError(f"Checkpoint {checkpoint_id} is {checkpoint['status']}, cannot add signature")

    # Check expiration
    expires_at = datetime.fromisoformat(checkpoint["expires_at"])
    if datetime.now(UTC) > expires_at:
        raise ValueError(f"Checkpoint {checkpoint_id} has expired")

    checkpoints_path = get_checkpoints_path()

    # Add signature to approvals list
    approvals = checkpoint.get("approvals", [])

    # Check if user already signed
    if any(a.get("user") == user for a in approvals):
        raise ValueError(f"User {user} has already signed checkpoint {checkpoint_id}")

    approvals.append(
        {
            "user": user,
            "at": datetime.now(UTC).isoformat(),
            "approval_data": approval_data or {},
        }
    )

    updated = checkpoint.copy()
    updated["event"] = "signature_added"
    updated["approvals"] = approvals

    # Check if satisfied
    # Note: we don't automatically mark as approved here
    # The runner will check is_satisfied and mark as approved when threshold met

    with open(checkpoints_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(updated) + "\n")

    return updated


def is_satisfied(
    checkpoint: dict[str, Any], effective_role_fn: Callable[[str, str, str], str | None] | None = None
) -> bool:
    """
    Check if multi-sign checkpoint has sufficient signatures (Sprint 34A).

    Args:
        checkpoint: Checkpoint record
        effective_role_fn: Function to get effective role for user (scope, scope_id, user)
                          Defaults to checking against required_signers

    Returns:
        True if M-of-N signatures satisfied

    Example:
        >>> checkpoint = {"approvals": [...], "min_signatures": 2, "required_signers": ["alice", "bob", "charlie"]}
        >>> is_satisfied(checkpoint)
        True  # If at least 2 of the 3 required signers have approved
    """
    min_signatures = checkpoint.get("min_signatures", 1)
    approvals = checkpoint.get("approvals", [])
    required_signers = checkpoint.get("required_signers", [])

    # If no multi-sign configured, check if we have at least one approval
    if not required_signers or min_signatures <= 1:
        return len(approvals) >= 1

    # Count valid signatures from required signers
    valid_count = 0

    for approval in approvals:
        user = approval.get("user")
        if not user:
            continue

        # Check if user is in required signers (direct match)
        if user in required_signers:
            valid_count += 1
            continue

        # Check if user's role matches a required role
        if effective_role_fn:
            for signer_spec in required_signers:
                # If signer_spec looks like a role (capitalized), check role match
                if signer_spec and signer_spec[0].isupper():
                    # Get effective role for user
                    # Note: This is simplified - in practice would need scope context
                    # For now, we just check direct matches
                    pass

    return valid_count >= min_signatures
