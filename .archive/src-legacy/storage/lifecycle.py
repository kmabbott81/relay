"""
Storage Lifecycle Manager for Sprint 26

Implements automated lifecycle management with retention policies,
promotion between tiers, and audit logging.

Lifecycle flow:
1. Hot tier: Recently created/accessed artifacts
2. Warm tier: Artifacts older than HOT_RETENTION_DAYS
3. Cold tier: Artifacts older than WARM_RETENTION_DAYS
4. Purged: Artifacts older than COLD_RETENTION_DAYS

All operations emit audit events to logs/lifecycle_events.jsonl
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .tiered_store import (
    TIER_COLD,
    TIER_HOT,
    TIER_WARM,
    get_artifact_age_days,
    list_artifacts,
    promote_artifact,
    purge_artifact,
)

# Default retention policies (in days)
DEFAULT_HOT_RETENTION_DAYS = 7
DEFAULT_WARM_RETENTION_DAYS = 30
DEFAULT_COLD_RETENTION_DAYS = 90


def get_retention_days() -> dict[str, int]:
    """
    Get retention policies from environment or use defaults.

    Returns:
        Dict with hot_days, warm_days, cold_days
    """
    return {
        "hot_days": int(os.getenv("HOT_RETENTION_DAYS", DEFAULT_HOT_RETENTION_DAYS)),
        "warm_days": int(os.getenv("WARM_RETENTION_DAYS", DEFAULT_WARM_RETENTION_DAYS)),
        "cold_days": int(os.getenv("COLD_RETENTION_DAYS", DEFAULT_COLD_RETENTION_DAYS)),
    }


def get_lifecycle_log_path() -> Path:
    """
    Get the path to the lifecycle events log file.

    Returns:
        Path: Path to logs/lifecycle_events.jsonl
    """
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "lifecycle_events.jsonl"


def log_lifecycle_event(event: dict[str, Any]) -> None:
    """
    Log a lifecycle event to the audit log.

    Args:
        event: Event dictionary containing event details
    """
    log_path = get_lifecycle_log_path()

    # Add timestamp if not present
    if "timestamp" not in event:
        event["timestamp"] = datetime.utcnow().isoformat()

    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except Exception as e:
        # Don't fail the operation if logging fails
        print(f"Warning: Failed to log lifecycle event: {e}")


def scan_tier_for_expired(tier: str, max_age_days: int, fake_clock: Optional[float] = None) -> list[dict[str, Any]]:
    """
    Scan a tier for artifacts older than max_age_days.

    Args:
        tier: Storage tier to scan (hot/warm/cold)
        max_age_days: Maximum age threshold in days
        fake_clock: Optional fake current time for testing (Unix timestamp)

    Returns:
        List of expired artifact info dictionaries
    """
    expired = []

    try:
        artifacts = list_artifacts(tier)

        for artifact in artifacts:
            try:
                age_days = get_artifact_age_days(
                    tier, artifact["tenant_id"], artifact["workflow_id"], artifact["artifact_id"], fake_clock=fake_clock
                )

                if age_days > max_age_days:
                    artifact["age_days"] = age_days
                    expired.append(artifact)

            except Exception as e:
                # Log error but continue scanning
                log_lifecycle_event(
                    {
                        "event_type": "scan_error",
                        "tier": tier,
                        "artifact": artifact.get("artifact_id", "unknown"),
                        "error": str(e),
                    }
                )

        return expired

    except Exception as e:
        log_lifecycle_event(
            {
                "event_type": "scan_tier_failed",
                "tier": tier,
                "error": str(e),
            }
        )
        return []


def promote_expired_to_warm(dry_run: bool = False, fake_clock: Optional[float] = None) -> dict[str, Any]:
    """
    Promote expired artifacts from hot to warm tier.

    Args:
        dry_run: If True, don't actually move files
        fake_clock: Optional fake current time for testing

    Returns:
        Dict with stats: promoted, errors, artifacts
    """
    retention = get_retention_days()
    max_age_days = retention["hot_days"]

    expired = scan_tier_for_expired(TIER_HOT, max_age_days, fake_clock=fake_clock)

    promoted = 0
    errors = []
    promoted_artifacts = []

    for artifact in expired:
        try:
            tenant_id = artifact["tenant_id"]
            workflow_id = artifact["workflow_id"]
            artifact_id = artifact["artifact_id"]

            success = promote_artifact(
                tenant_id, workflow_id, artifact_id, from_tier=TIER_HOT, to_tier=TIER_WARM, dry_run=dry_run
            )

            if success:
                promoted += 1
                promoted_artifacts.append(artifact_id)

                log_lifecycle_event(
                    {
                        "event_type": "promoted_to_warm",
                        "tenant_id": tenant_id,
                        "workflow_id": workflow_id,
                        "artifact_id": artifact_id,
                        "age_days": artifact.get("age_days"),
                        "dry_run": dry_run,
                    }
                )

        except Exception as e:
            error_msg = f"Failed to promote {artifact['artifact_id']}: {e}"
            errors.append(error_msg)

            log_lifecycle_event(
                {
                    "event_type": "promotion_error",
                    "from_tier": TIER_HOT,
                    "to_tier": TIER_WARM,
                    "artifact_id": artifact["artifact_id"],
                    "error": str(e),
                    "dry_run": dry_run,
                }
            )

    return {
        "promoted": promoted,
        "errors": len(errors),
        "error_details": errors,
        "artifacts": promoted_artifacts,
        "scanned": len(expired),
        "max_age_days": max_age_days,
    }


def promote_expired_to_cold(dry_run: bool = False, fake_clock: Optional[float] = None) -> dict[str, Any]:
    """
    Promote expired artifacts from warm to cold tier.

    Args:
        dry_run: If True, don't actually move files
        fake_clock: Optional fake current time for testing

    Returns:
        Dict with stats: promoted, errors, artifacts
    """
    retention = get_retention_days()
    max_age_days = retention["warm_days"]

    expired = scan_tier_for_expired(TIER_WARM, max_age_days, fake_clock=fake_clock)

    promoted = 0
    errors = []
    promoted_artifacts = []

    for artifact in expired:
        try:
            tenant_id = artifact["tenant_id"]
            workflow_id = artifact["workflow_id"]
            artifact_id = artifact["artifact_id"]

            success = promote_artifact(
                tenant_id, workflow_id, artifact_id, from_tier=TIER_WARM, to_tier=TIER_COLD, dry_run=dry_run
            )

            if success:
                promoted += 1
                promoted_artifacts.append(artifact_id)

                log_lifecycle_event(
                    {
                        "event_type": "promoted_to_cold",
                        "tenant_id": tenant_id,
                        "workflow_id": workflow_id,
                        "artifact_id": artifact_id,
                        "age_days": artifact.get("age_days"),
                        "dry_run": dry_run,
                    }
                )

        except Exception as e:
            error_msg = f"Failed to promote {artifact['artifact_id']}: {e}"
            errors.append(error_msg)

            log_lifecycle_event(
                {
                    "event_type": "promotion_error",
                    "from_tier": TIER_WARM,
                    "to_tier": TIER_COLD,
                    "artifact_id": artifact["artifact_id"],
                    "error": str(e),
                    "dry_run": dry_run,
                }
            )

    return {
        "promoted": promoted,
        "errors": len(errors),
        "error_details": errors,
        "artifacts": promoted_artifacts,
        "scanned": len(expired),
        "max_age_days": max_age_days,
    }


def purge_expired_from_cold(dry_run: bool = False, fake_clock: Optional[float] = None) -> dict[str, Any]:
    """
    Purge expired artifacts from cold tier.

    Args:
        dry_run: If True, don't actually delete files
        fake_clock: Optional fake current time for testing

    Returns:
        Dict with stats: purged, errors, artifacts
    """
    retention = get_retention_days()
    max_age_days = retention["cold_days"]

    expired = scan_tier_for_expired(TIER_COLD, max_age_days, fake_clock=fake_clock)

    purged = 0
    errors = []
    purged_artifacts = []

    for artifact in expired:
        try:
            tenant_id = artifact["tenant_id"]
            workflow_id = artifact["workflow_id"]
            artifact_id = artifact["artifact_id"]

            success = purge_artifact(TIER_COLD, tenant_id, workflow_id, artifact_id, dry_run=dry_run)

            if success:
                purged += 1
                purged_artifacts.append(artifact_id)

                log_lifecycle_event(
                    {
                        "event_type": "purged_from_cold",
                        "tenant_id": tenant_id,
                        "workflow_id": workflow_id,
                        "artifact_id": artifact_id,
                        "age_days": artifact.get("age_days"),
                        "size_bytes": artifact.get("size_bytes"),
                        "dry_run": dry_run,
                    }
                )

        except Exception as e:
            error_msg = f"Failed to purge {artifact['artifact_id']}: {e}"
            errors.append(error_msg)

            log_lifecycle_event(
                {
                    "event_type": "purge_error",
                    "tier": TIER_COLD,
                    "artifact_id": artifact["artifact_id"],
                    "error": str(e),
                    "dry_run": dry_run,
                }
            )

    return {
        "purged": purged,
        "errors": len(errors),
        "error_details": errors,
        "artifacts": purged_artifacts,
        "scanned": len(expired),
        "max_age_days": max_age_days,
    }


def run_lifecycle_job(dry_run: bool = False, fake_clock: Optional[float] = None) -> dict[str, Any]:
    """
    Run complete lifecycle job: promote hot→warm, warm→cold, purge cold.

    Args:
        dry_run: If True, don't actually move or delete files
        fake_clock: Optional fake current time for testing

    Returns:
        Dict with complete job stats
    """
    job_start = time.time()
    retention = get_retention_days()

    log_lifecycle_event(
        {
            "event_type": "lifecycle_job_started",
            "dry_run": dry_run,
            "retention_policies": retention,
        }
    )

    results = {
        "job_start": datetime.utcnow().isoformat(),
        "dry_run": dry_run,
        "retention_policies": retention,
    }

    # Step 1: Promote hot → warm
    try:
        warm_results = promote_expired_to_warm(dry_run=dry_run, fake_clock=fake_clock)
        results["promoted_to_warm"] = warm_results["promoted"]
        results["warm_errors"] = warm_results["errors"]
        results["warm_details"] = warm_results
    except Exception as e:
        results["promoted_to_warm"] = 0
        results["warm_errors"] = 1
        results["warm_error_message"] = str(e)

        log_lifecycle_event(
            {
                "event_type": "lifecycle_step_failed",
                "step": "promote_to_warm",
                "error": str(e),
            }
        )

    # Step 2: Promote warm → cold
    try:
        cold_results = promote_expired_to_cold(dry_run=dry_run, fake_clock=fake_clock)
        results["promoted_to_cold"] = cold_results["promoted"]
        results["cold_errors"] = cold_results["errors"]
        results["cold_details"] = cold_results
    except Exception as e:
        results["promoted_to_cold"] = 0
        results["cold_errors"] = 1
        results["cold_error_message"] = str(e)

        log_lifecycle_event(
            {
                "event_type": "lifecycle_step_failed",
                "step": "promote_to_cold",
                "error": str(e),
            }
        )

    # Step 3: Purge from cold
    try:
        purge_results = purge_expired_from_cold(dry_run=dry_run, fake_clock=fake_clock)
        results["purged"] = purge_results["purged"]
        results["purge_errors"] = purge_results["errors"]
        results["purge_details"] = purge_results
    except Exception as e:
        results["purged"] = 0
        results["purge_errors"] = 1
        results["purge_error_message"] = str(e)

        log_lifecycle_event(
            {
                "event_type": "lifecycle_step_failed",
                "step": "purge_from_cold",
                "error": str(e),
            }
        )

    # Calculate totals
    job_duration = time.time() - job_start
    results["job_end"] = datetime.utcnow().isoformat()
    results["job_duration_seconds"] = job_duration

    total_errors = results.get("warm_errors", 0) + results.get("cold_errors", 0) + results.get("purge_errors", 0)
    results["total_errors"] = total_errors

    # Log completion
    log_lifecycle_event(
        {
            "event_type": "lifecycle_job_completed",
            "dry_run": dry_run,
            "promoted_to_warm": results.get("promoted_to_warm", 0),
            "promoted_to_cold": results.get("promoted_to_cold", 0),
            "purged": results.get("purged", 0),
            "total_errors": total_errors,
            "duration_seconds": job_duration,
        }
    )

    return results


def get_recent_lifecycle_events(limit: int = 20) -> list[dict[str, Any]]:
    """
    Get recent lifecycle events from the log.

    Args:
        limit: Maximum number of events to return

    Returns:
        List of event dictionaries (most recent first)
    """
    log_path = get_lifecycle_log_path()

    if not log_path.exists():
        return []

    events = []

    try:
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        event = json.loads(line)
                        events.append(event)
                    except json.JSONDecodeError:
                        pass  # Skip corrupted lines

        # Return most recent events first
        return events[-limit:][::-1]

    except Exception as e:
        print(f"Warning: Failed to read lifecycle events: {e}")
        return []


def get_last_lifecycle_job() -> Optional[dict[str, Any]]:
    """
    Get the most recent lifecycle job completion event.

    Returns:
        Event dict or None if no jobs found
    """
    events = get_recent_lifecycle_events(limit=100)

    for event in events:
        if event.get("event_type") == "lifecycle_job_completed":
            return event

    return None


def restore_artifact(
    tenant_id: str, workflow_id: str, artifact_id: str, from_tier: str, to_tier: str = TIER_HOT, dry_run: bool = False
) -> bool:
    """
    Restore an artifact from a lower tier back to a higher tier.

    Args:
        tenant_id: Tenant identifier
        workflow_id: Workflow identifier
        artifact_id: Artifact identifier
        from_tier: Source tier (warm or cold)
        to_tier: Destination tier (default: hot)
        dry_run: If True, don't actually move files

    Returns:
        bool: True if restore succeeded

    Raises:
        ArtifactNotFoundError: If source artifact doesn't exist
        StorageError: If restore fails
    """
    success = promote_artifact(
        tenant_id, workflow_id, artifact_id, from_tier=from_tier, to_tier=to_tier, dry_run=dry_run
    )

    if success:
        log_lifecycle_event(
            {
                "event_type": "artifact_restored",
                "tenant_id": tenant_id,
                "workflow_id": workflow_id,
                "artifact_id": artifact_id,
                "from_tier": from_tier,
                "to_tier": to_tier,
                "dry_run": dry_run,
            }
        )

    return success
