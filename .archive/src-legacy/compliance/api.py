"""
Compliance API - Sprint 33A + 33B

Core compliance operations: export, delete, retention enforcement.
All operations are tenant-scoped, RBAC-enforced, and audited.

Sprint 33B: Added classification and encryption support.
"""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from relay_ai.classify.policy import export_allowed

from .holds import is_on_hold


def check_rbac(operation: str, required_role: str = "Compliance") -> None:
    """
    Check RBAC for compliance operations.

    Args:
        operation: Operation name for error messages
        required_role: Minimum required role

    Raises:
        PermissionError: If user lacks required role
    """
    user_role = os.getenv("USER_RBAC_ROLE", "Viewer")
    compliance_role = os.getenv("COMPLIANCE_RBAC_ROLE", "Compliance")

    # Role hierarchy: Viewer < Author < Operator < Auditor < Compliance < Admin
    roles = {
        "Viewer": 0,
        "Author": 1,
        "Operator": 2,
        "Auditor": 3,
        "Compliance": 4,
        "Admin": 5,
    }

    user_level = roles.get(user_role, 0)
    required_level = roles.get(compliance_role if required_role == "Compliance" else required_role, 4)

    # For read operations, allow Auditor+
    if operation in ["export", "list_holds"]:
        if user_level < roles.get("Auditor", 3):
            raise PermissionError(f"{operation} requires Auditor role or higher, but user has {user_role}")
        return

    # For mutating operations, require Compliance+
    if user_level < required_level:
        raise PermissionError(f"{operation} requires {required_role} role or higher, but user has {user_role}")


def export_tenant(tenant: str, out_dir: Path) -> dict:
    """
    Export all tenant-scoped data to deterministic bundle.

    Collects data from:
    - Tiered storage artifacts (hot/warm/cold)
    - Orchestrator events and state
    - Queue events and DLQ
    - Approvals and checkpoints
    - Cost and governance events
    - Template registry entries

    Args:
        tenant: Tenant ID
        out_dir: Output directory for export bundle

    Returns:
        Dict with export summary and counts

    Raises:
        PermissionError: If user lacks Auditor+ role
    """
    check_rbac("export", "Auditor")

    # Create export bundle directory
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d")
    export_path = out_dir / f"{tenant}-export-{timestamp}"
    export_path.mkdir(parents=True, exist_ok=True)

    counts = {}

    # 1. Export tiered storage artifacts (by reference, not copies)
    artifact_refs = _collect_artifact_refs(tenant)
    if artifact_refs:
        with open(export_path / "artifacts.json", "w", encoding="utf-8") as f:
            json.dump(artifact_refs, f, indent=2)
    counts["artifacts"] = len(artifact_refs)

    # 2. Export orchestrator events
    orch_events = _collect_jsonl_entries(
        Path(os.getenv("ORCH_EVENTS_PATH", "logs/orchestrator_events.jsonl")),
        tenant_filter=tenant,
    )
    if orch_events:
        with open(export_path / "orchestrator_events.jsonl", "w", encoding="utf-8") as f:
            for event in orch_events:
                f.write(json.dumps(event) + "\n")
    counts["orch_events"] = len(orch_events)

    # 3. Export queue events
    queue_events = _collect_jsonl_entries(
        Path(os.getenv("QUEUE_EVENTS_PATH", "logs/queue_events.jsonl")),
        tenant_filter=tenant,
    )
    if queue_events:
        with open(export_path / "queue_events.jsonl", "w", encoding="utf-8") as f:
            for event in queue_events:
                f.write(json.dumps(event) + "\n")
    counts["queue_events"] = len(queue_events)

    # 4. Export cost events
    cost_events = _collect_jsonl_entries(
        Path(os.getenv("COST_LOG_PATH", "logs/cost_events.jsonl")),
        tenant_filter=tenant,
    )
    if cost_events:
        with open(export_path / "cost_events.jsonl", "w", encoding="utf-8") as f:
            for event in cost_events:
                f.write(json.dumps(event) + "\n")
    counts["cost_events"] = len(cost_events)

    # 5. Export approval/checkpoint events
    approval_events = _collect_jsonl_entries(
        Path(os.getenv("APPROVALS_LOG_PATH", "logs/approvals.jsonl")),
        tenant_filter=tenant,
    )
    if approval_events:
        with open(export_path / "approval_events.jsonl", "w", encoding="utf-8") as f:
            for event in approval_events:
                f.write(json.dumps(event) + "\n")
    counts["approval_events"] = len(approval_events)

    # 6. Export governance events
    gov_events = _collect_jsonl_entries(
        Path(os.getenv("GOV_EVENTS_PATH", "logs/governance_events.jsonl")),
        tenant_filter=tenant,
    )
    if gov_events:
        with open(export_path / "governance_events.jsonl", "w", encoding="utf-8") as f:
            for event in gov_events:
                f.write(json.dumps(event) + "\n")
    counts["gov_events"] = len(gov_events)

    # Write export manifest
    manifest = {
        "tenant": tenant,
        "export_date": datetime.now(UTC).isoformat(),
        "export_path": str(export_path),
        "counts": counts,
        "total_items": sum(counts.values()),
    }

    with open(export_path / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return manifest


def delete_tenant(tenant: str, *, dry_run: bool = False, respect_legal_hold: bool = True) -> dict:
    """
    Delete all tenant-scoped data.

    Args:
        tenant: Tenant ID
        dry_run: If True, report what would be deleted without deleting
        respect_legal_hold: If True (default), block deletion if hold active

    Returns:
        Dict with deletion summary and counts

    Raises:
        PermissionError: If user lacks Compliance+ role
        ValueError: If legal hold active and respect_legal_hold=True
    """
    check_rbac("delete", "Compliance")

    # Check legal hold
    if respect_legal_hold and is_on_hold(tenant):
        raise ValueError(f"Cannot delete tenant {tenant}: active legal hold")

    counts = {}

    # 1. Delete tiered storage artifacts
    artifact_count = _delete_artifacts(tenant, dry_run=dry_run)
    counts["artifacts"] = artifact_count

    # 2. Delete orchestrator events
    orch_count = _delete_jsonl_entries(
        Path(os.getenv("ORCH_EVENTS_PATH", "logs/orchestrator_events.jsonl")),
        tenant_filter=tenant,
        dry_run=dry_run,
    )
    counts["orch_events"] = orch_count

    # 3. Delete queue events
    queue_count = _delete_jsonl_entries(
        Path(os.getenv("QUEUE_EVENTS_PATH", "logs/queue_events.jsonl")),
        tenant_filter=tenant,
        dry_run=dry_run,
    )
    counts["queue_events"] = queue_count

    # 4. Delete cost events
    cost_count = _delete_jsonl_entries(
        Path(os.getenv("COST_LOG_PATH", "logs/cost_events.jsonl")),
        tenant_filter=tenant,
        dry_run=dry_run,
    )
    counts["cost_events"] = cost_count

    # 5. Delete approval/checkpoint events
    approval_count = _delete_jsonl_entries(
        Path(os.getenv("APPROVALS_LOG_PATH", "logs/approvals.jsonl")),
        tenant_filter=tenant,
        dry_run=dry_run,
    )
    counts["approval_events"] = approval_count

    # 6. Delete governance events
    gov_count = _delete_jsonl_entries(
        Path(os.getenv("GOV_EVENTS_PATH", "logs/governance_events.jsonl")),
        tenant_filter=tenant,
        dry_run=dry_run,
    )
    counts["gov_events"] = gov_count

    return {
        "tenant": tenant,
        "dry_run": dry_run,
        "deleted_at": None if dry_run else datetime.now(UTC).isoformat(),
        "counts": counts,
        "total_items": sum(counts.values()),
    }


def enforce_retention(now: datetime | None = None) -> dict:
    """
    Enforce retention policies across all event stores.

    Uses environment variables for retention windows (in days):
    - RETAIN_ORCH_EVENTS_DAYS (default: 90)
    - RETAIN_STATE_EVENTS_DAYS (default: 90)
    - RETAIN_QUEUE_EVENTS_DAYS (default: 60)
    - RETAIN_DLQ_DAYS (default: 30)
    - RETAIN_CHECKPOINTS_DAYS (default: 90)
    - RETAIN_COST_EVENTS_DAYS (default: 180)
    - RETAIN_GOV_EVENTS_DAYS (default: 365)

    Args:
        now: Current time (defaults to UTC now, overridable for testing)

    Returns:
        Dict with retention summary and counts

    Raises:
        PermissionError: If user lacks Compliance+ role
    """
    check_rbac("enforce_retention", "Compliance")

    if now is None:
        now = datetime.now(UTC)

    counts = {}

    # Define retention windows
    retention_configs = [
        ("RETAIN_ORCH_EVENTS_DAYS", "logs/orchestrator_events.jsonl", 90),
        ("RETAIN_QUEUE_EVENTS_DAYS", "logs/queue_events.jsonl", 60),
        ("RETAIN_COST_EVENTS_DAYS", "logs/cost_events.jsonl", 180),
        ("RETAIN_GOV_EVENTS_DAYS", "logs/governance_events.jsonl", 365),
        ("RETAIN_CHECKPOINTS_DAYS", "logs/approvals.jsonl", 90),
    ]

    for env_var, default_path, default_days in retention_configs:
        days = int(os.getenv(env_var, str(default_days)))
        cutoff = now - timedelta(days=days)

        # Get path from env or use default
        if "ORCH" in env_var:
            path = Path(os.getenv("ORCH_EVENTS_PATH", default_path))
        elif "QUEUE" in env_var:
            path = Path(os.getenv("QUEUE_EVENTS_PATH", default_path))
        elif "COST" in env_var:
            path = Path(os.getenv("COST_LOG_PATH", default_path))
        elif "GOV" in env_var:
            path = Path(os.getenv("GOV_EVENTS_PATH", default_path))
        else:
            path = Path(os.getenv("APPROVALS_LOG_PATH", default_path))

        purged = _prune_jsonl_by_date(path, cutoff)
        counts[env_var] = purged

    return {
        "enforced_at": now.isoformat(),
        "counts": counts,
        "total_purged": sum(counts.values()),
    }


# Helper functions


def _collect_artifact_refs(tenant: str, user_clearance: str | None = None) -> list[dict]:
    """
    Collect artifact file references for tenant (not full copies).

    Sprint 33B: Added classification and export policy enforcement.

    Args:
        tenant: Tenant ID to filter
        user_clearance: User clearance for export policy (None = use USER_CLEARANCE env)

    Returns:
        List of artifact references with metadata
    """
    refs = []
    denied_count = 0
    storage_base = Path(os.getenv("STORAGE_BASE_PATH", "artifacts"))

    if user_clearance is None:
        user_clearance = os.getenv("USER_CLEARANCE", "Operator")

    require_labels = os.getenv("REQUIRE_LABELS_FOR_EXPORT", "false").lower() in ("true", "1", "yes")
    export_policy = os.getenv("EXPORT_POLICY", "deny")  # deny|redact

    for tier in ["hot", "warm", "cold"]:
        tier_path = storage_base / tier
        if not tier_path.exists():
            continue

        # Scan for tenant artifacts
        for artifact_file in tier_path.rglob("*.md"):
            # Check if artifact belongs to tenant (simple heuristic: tenant in path or metadata)
            if tenant in str(artifact_file):
                # Check for classification metadata
                sidecar_path = artifact_file.with_suffix(artifact_file.suffix + ".json")
                label = None
                if sidecar_path.exists():
                    try:
                        meta = json.loads(sidecar_path.read_text(encoding="utf-8"))
                        label = meta.get("label")
                    except (json.JSONDecodeError, OSError):
                        pass

                # Check export policy
                if not export_allowed(label, user_clearance, require_labels):
                    denied_count += 1
                    # Log governance event for denied export
                    _log_governance_event(
                        {
                            "event": "export_denied",
                            "tenant": tenant,
                            "artifact": str(artifact_file),
                            "label": label,
                            "user_clearance": user_clearance,
                            "reason": "unlabeled" if label is None else "insufficient_clearance",
                            "policy": export_policy,
                        }
                    )

                    if export_policy == "deny":
                        continue  # Skip this artifact
                    # elif export_policy == "redact": include with redacted flag

                ref = {
                    "path": str(artifact_file.relative_to(storage_base)),
                    "tier": tier,
                    "size_bytes": artifact_file.stat().st_size if artifact_file.exists() else 0,
                }

                # Include label if present
                if label:
                    ref["label"] = label

                # Mark as redacted if policy is redact
                if export_policy == "redact" and label and not export_allowed(label, user_clearance, False):
                    ref["redacted"] = True

                refs.append(ref)

    # Log denied count if any
    if denied_count > 0:
        _log_governance_event(
            {
                "event": "export_artifacts_denied",
                "tenant": tenant,
                "denied_count": denied_count,
                "user_clearance": user_clearance,
                "require_labels": require_labels,
                "export_policy": export_policy,
            }
        )

    return refs


def _collect_jsonl_entries(path: Path, tenant_filter: str | None = None) -> list[dict]:
    """Collect JSONL entries, optionally filtered by tenant."""
    if not path.exists():
        return []

    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
                if tenant_filter is None or entry.get("tenant") == tenant_filter:
                    entries.append(entry)
            except json.JSONDecodeError:
                continue

    return entries


def _delete_artifacts(tenant: str, dry_run: bool = False) -> int:
    """Delete tenant artifacts from tiered storage."""
    count = 0
    storage_base = Path(os.getenv("STORAGE_BASE_PATH", "artifacts"))

    for tier in ["hot", "warm", "cold"]:
        tier_path = storage_base / tier
        if not tier_path.exists():
            continue

        for artifact_file in tier_path.rglob("*.md"):
            if tenant in str(artifact_file):
                count += 1
                if not dry_run:
                    artifact_file.unlink()

    return count


def _delete_jsonl_entries(path: Path, tenant_filter: str, dry_run: bool = False) -> int:
    """Delete JSONL entries matching tenant filter."""
    if not path.exists():
        return 0

    # Collect entries to keep
    keep_entries = []
    delete_count = 0

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
                if entry.get("tenant") == tenant_filter:
                    delete_count += 1
                else:
                    keep_entries.append(line)
            except json.JSONDecodeError:
                keep_entries.append(line)

    # Rewrite file without deleted entries
    if not dry_run and delete_count > 0:
        temp_path = path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            for line in keep_entries:
                f.write(line + "\n")
        temp_path.replace(path)

    return delete_count


def _prune_jsonl_by_date(path: Path, cutoff: datetime) -> int:
    """Prune JSONL entries older than cutoff date."""
    if not path.exists():
        return 0

    keep_entries = []
    purged_count = 0

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
                timestamp_str = entry.get("timestamp")
                if timestamp_str:
                    # Parse timestamp (handle both with and without Z suffix)
                    ts_str = timestamp_str.rstrip("Z")
                    if "+" in ts_str:
                        entry_time = datetime.fromisoformat(ts_str)
                    else:
                        entry_time = datetime.fromisoformat(ts_str).replace(tzinfo=UTC)

                    if entry_time < cutoff:
                        purged_count += 1
                        continue

                keep_entries.append(line)
            except (json.JSONDecodeError, ValueError, KeyError):
                # Keep malformed entries to avoid data loss
                keep_entries.append(line)

    # Rewrite file
    if purged_count > 0:
        temp_path = path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            for line in keep_entries:
                f.write(line + "\n")
        temp_path.replace(path)

    return purged_count


def _log_governance_event(event: dict) -> None:
    """
    Log governance event for audit trail.

    Sprint 33B: Used for classification and export policy enforcement.
    """
    gov_path = Path(os.getenv("GOV_EVENTS_PATH", "logs/governance_events.jsonl"))
    gov_path.parent.mkdir(parents=True, exist_ok=True)

    event_with_timestamp = {
        "timestamp": datetime.now(UTC).isoformat(),
        **event,
    }

    with open(gov_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event_with_timestamp) + "\n")
