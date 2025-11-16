"""
Legal Hold Store - Sprint 33A

Append-only JSONL log of legal hold events for tenant data preservation.
Prevents deletion of tenant data when holds are active.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path


def get_holds_path() -> Path:
    """Get path to legal holds log."""
    path_str = os.getenv("LOGS_LEGAL_HOLDS_PATH", "logs/legal_holds.jsonl")
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def apply_legal_hold(tenant: str, reason: str) -> dict:
    """
    Apply legal hold to tenant data.

    Args:
        tenant: Tenant ID
        reason: Reason for hold (required)

    Returns:
        Event dict with timestamp, tenant, reason

    Raises:
        ValueError: If reason is empty
    """
    if not reason or not reason.strip():
        raise ValueError("Legal hold reason is required")

    event = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": "hold_applied",
        "tenant": tenant,
        "reason": reason.strip(),
    }

    holds_path = get_holds_path()
    with open(holds_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")

    return event


def release_legal_hold(tenant: str) -> dict:
    """
    Release legal hold on tenant data.

    Args:
        tenant: Tenant ID

    Returns:
        Event dict with timestamp, tenant

    Raises:
        ValueError: If no active hold exists
    """
    if not is_on_hold(tenant):
        raise ValueError(f"No active legal hold for tenant: {tenant}")

    event = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": "hold_released",
        "tenant": tenant,
    }

    holds_path = get_holds_path()
    with open(holds_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")

    return event


def is_on_hold(tenant: str) -> bool:
    """
    Check if tenant has active legal hold.

    Args:
        tenant: Tenant ID

    Returns:
        True if tenant has active hold, False otherwise
    """
    holds_path = get_holds_path()
    if not holds_path.exists():
        return False

    # Track hold state by counting apply/release events
    hold_count = 0

    with open(holds_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
                if event.get("tenant") != tenant:
                    continue

                event_type = event.get("event")
                if event_type == "hold_applied":
                    hold_count += 1
                elif event_type == "hold_released":
                    hold_count -= 1
            except (json.JSONDecodeError, KeyError):
                continue

    return hold_count > 0


def current_holds() -> list[dict]:
    """
    Get list of all tenants with active holds.

    Returns:
        List of dicts with tenant, reason, applied_at for each active hold
    """
    holds_path = get_holds_path()
    if not holds_path.exists():
        return []

    # Track holds by tenant
    tenant_holds: dict[str, dict] = {}

    with open(holds_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
                tenant = event.get("tenant")
                if not tenant:
                    continue

                event_type = event.get("event")
                if event_type == "hold_applied":
                    tenant_holds[tenant] = {
                        "tenant": tenant,
                        "reason": event.get("reason", ""),
                        "applied_at": event.get("timestamp"),
                    }
                elif event_type == "hold_released":
                    tenant_holds.pop(tenant, None)
            except (json.JSONDecodeError, KeyError):
                continue

    return list(tenant_holds.values())
