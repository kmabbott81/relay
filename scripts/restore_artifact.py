#!/usr/bin/env python3
"""
Artifact Restore Script

Restore artifacts from warm or cold tiers back to hot tier.
Enforces tenant isolation and logs all restore operations.

Usage:
    python scripts/restore_artifact.py --tenant acme --from-tier warm --list
    python scripts/restore_artifact.py --tenant acme --workflow wf1 --artifact doc.txt --from-tier warm
    python scripts/restore_artifact.py --tenant acme --from-tier warm --auto-select
    python scripts/restore_artifact.py --tenant acme --workflow wf1 --artifact doc.txt --from-tier warm --dry-run
"""

import argparse
import sys
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from relay_ai.storage.lifecycle import log_lifecycle_event  # noqa: E402
from relay_ai.storage.tiered_store import (  # noqa: E402
    TIER_HOT,
    ArtifactNotFoundError,
    InvalidTenantPathError,
    StorageError,
    list_artifacts,
    promote_artifact,
    read_artifact,
)


def list_restorable_artifacts(tenant_id: str, from_tier: str) -> list[dict[str, Any]]:
    """
    List all artifacts available for restoration from a tier.

    Args:
        tenant_id: Tenant identifier
        from_tier: Source tier (warm or cold)

    Returns:
        List of artifact dictionaries
    """
    try:
        artifacts = list_artifacts(from_tier, tenant_id=tenant_id)
        return artifacts
    except StorageError as e:
        print(f"Error listing artifacts: {e}")
        return []


def print_artifact_list(artifacts: list[dict[str, Any]], from_tier: str) -> None:
    """
    Print a formatted list of artifacts.

    Args:
        artifacts: List of artifact dictionaries
        from_tier: Source tier name
    """
    if not artifacts:
        print(f"No artifacts found in {from_tier} tier")
        return

    print(f"\n{'=' * 80}")
    print(f"RESTORABLE ARTIFACTS IN {from_tier.upper()} TIER ({len(artifacts)} total)")
    print("=" * 80)
    print(f"{'#':3s} {'Workflow ID':20s} {'Artifact ID':30s} {'Size':>10s} {'Modified':19s}")
    print("-" * 80)

    for i, artifact in enumerate(artifacts, 1):
        workflow_id = artifact.get("workflow_id", "?")[:20]
        artifact_id = artifact.get("artifact_id", "?")[:30]
        size_bytes = artifact.get("size_bytes", 0)
        modified = artifact.get("modified_at", "?")[:19]

        if size_bytes < 1024:
            size_str = f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            size_str = f"{size_bytes / 1024:.1f} KB"
        else:
            size_str = f"{size_bytes / (1024 * 1024):.1f} MB"

        print(f"{i:3d} {workflow_id:20s} {artifact_id:30s} {size_str:>10s} {modified:19s}")

    print("=" * 80)


def restore_artifact_interactive(
    tenant_id: str, workflow_id: str, artifact_id: str, from_tier: str, to_tier: str = TIER_HOT, dry_run: bool = False
) -> bool:
    """
    Restore an artifact with interactive confirmation.

    Args:
        tenant_id: Tenant identifier
        workflow_id: Workflow identifier
        artifact_id: Artifact identifier
        from_tier: Source tier (warm or cold)
        to_tier: Destination tier (default: hot)
        dry_run: If True, don't actually restore

    Returns:
        True if restore succeeded
    """
    print("\n" + "=" * 80)
    print(f"{'[DRY-RUN] ' if dry_run else ''}ARTIFACT RESTORE")
    print("=" * 80)
    print(f"Tenant:   {tenant_id}")
    print(f"Workflow: {workflow_id}")
    print(f"Artifact: {artifact_id}")
    print(f"From:     {from_tier} tier")
    print(f"To:       {to_tier} tier")
    print("=" * 80)

    # Verify artifact exists
    try:
        content, metadata = read_artifact(from_tier, tenant_id, workflow_id, artifact_id)
        size_bytes = len(content)
        created_at = metadata.get("_created_at", "unknown")
        modified_at = metadata.get("_modified_at", "unknown")

        print("\nArtifact Details:")
        print(f"  Size: {size_bytes:,} bytes ({size_bytes / 1024:.2f} KB)")
        print(f"  Created: {created_at}")
        print(f"  Modified: {modified_at}")

    except ArtifactNotFoundError:
        print(f"\n Error: Artifact not found in {from_tier} tier")
        return False
    except StorageError as e:
        print(f"\n Error reading artifact: {e}")
        return False

    if dry_run:
        print(f"\n[DRY-RUN] Would restore artifact to {to_tier} tier")
        log_lifecycle_event(
            {
                "event_type": "artifact_restore_dry_run",
                "tenant_id": tenant_id,
                "workflow_id": workflow_id,
                "artifact_id": artifact_id,
                "from_tier": from_tier,
                "to_tier": to_tier,
                "dry_run": True,
            }
        )
        return True

    # Perform restore
    try:
        print("\n= Restoring artifact...")
        success = promote_artifact(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            artifact_id=artifact_id,
            from_tier=from_tier,
            to_tier=to_tier,
            dry_run=False,
        )

        if success:
            print(f" Artifact successfully restored to {to_tier} tier")
            log_lifecycle_event(
                {
                    "event_type": "artifact_restored",
                    "tenant_id": tenant_id,
                    "workflow_id": workflow_id,
                    "artifact_id": artifact_id,
                    "from_tier": from_tier,
                    "to_tier": to_tier,
                    "size_bytes": size_bytes,
                }
            )
            return True
        else:
            print(" Restore failed (see logs for details)")
            return False

    except StorageError as e:
        print(f" Error during restore: {e}")
        return False


def auto_select_and_restore(tenant_id: str, from_tier: str, to_tier: str = TIER_HOT, dry_run: bool = False) -> bool:
    """
    Auto-select the first available artifact and restore it.

    Args:
        tenant_id: Tenant identifier
        from_tier: Source tier
        to_tier: Destination tier
        dry_run: If True, don't actually restore

    Returns:
        True if restore succeeded
    """
    artifacts = list_restorable_artifacts(tenant_id, from_tier)

    if not artifacts:
        print(f" No artifacts found in {from_tier} tier for tenant {tenant_id}")
        return False

    # Select first artifact
    artifact = artifacts[0]
    print("Auto-selected artifact:")
    print(f"  Workflow: {artifact['workflow_id']}")
    print(f"  Artifact: {artifact['artifact_id']}")

    return restore_artifact_interactive(
        tenant_id=tenant_id,
        workflow_id=artifact["workflow_id"],
        artifact_id=artifact["artifact_id"],
        from_tier=from_tier,
        to_tier=to_tier,
        dry_run=dry_run,
    )


def main():
    """Main entry point for restore script."""
    parser = argparse.ArgumentParser(
        description="Restore artifacts from warm/cold tiers back to hot tier",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all restorable artifacts for a tenant
  python scripts/restore_artifact.py --tenant acme --from-tier warm --list

  # Restore specific artifact
  python scripts/restore_artifact.py \\
    --tenant acme \\
    --workflow important_project \\
    --artifact critical_doc.pdf \\
    --from-tier warm

  # Auto-select and restore first artifact
  python scripts/restore_artifact.py --tenant acme --from-tier cold --auto-select

  # Dry run
  python scripts/restore_artifact.py \\
    --tenant acme \\
    --workflow wf1 \\
    --artifact doc.txt \\
    --from-tier warm \\
    --dry-run

Security Notes:
  - Tenant isolation enforced - cannot restore across tenants
  - All restore operations are audit logged
  - Cross-tenant access is blocked by path validation
        """,
    )

    parser.add_argument("--tenant", required=True, help="Tenant ID (required for isolation)")

    parser.add_argument("--from-tier", required=True, choices=["warm", "cold"], help="Source tier to restore from")

    parser.add_argument("--to-tier", default="hot", choices=["hot"], help="Destination tier (default: hot)")

    parser.add_argument("--workflow", help="Workflow ID")

    parser.add_argument("--artifact", help="Artifact ID")

    parser.add_argument("--list", action="store_true", help="List all restorable artifacts and exit")

    parser.add_argument("--auto-select", action="store_true", help="Auto-select first artifact and restore it")

    parser.add_argument(
        "--dry-run", action="store_true", help="Dry run - show what would happen without making changes"
    )

    args = parser.parse_args()

    # Validate tenant ID
    try:
        from relay_ai.storage.tiered_store import validate_tenant_id

        validate_tenant_id(args.tenant)
    except InvalidTenantPathError as e:
        print(f" Invalid tenant ID: {e}")
        return 1

    # List mode
    if args.list:
        artifacts = list_restorable_artifacts(args.tenant, args.from_tier)
        print_artifact_list(artifacts, args.from_tier)
        return 0

    # Auto-select mode
    if args.auto_select:
        success = auto_select_and_restore(
            tenant_id=args.tenant, from_tier=args.from_tier, to_tier=args.to_tier, dry_run=args.dry_run
        )
        return 0 if success else 1

    # Manual restore mode - require workflow and artifact
    if not args.workflow or not args.artifact:
        print(" Error: --workflow and --artifact are required (or use --list or --auto-select)")
        parser.print_help()
        return 1

    success = restore_artifact_interactive(
        tenant_id=args.tenant,
        workflow_id=args.workflow,
        artifact_id=args.artifact,
        from_tier=args.from_tier,
        to_tier=args.to_tier,
        dry_run=args.dry_run,
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
