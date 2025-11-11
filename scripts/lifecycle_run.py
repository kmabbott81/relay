#!/usr/bin/env python3
"""
Lifecycle Job Runner

Wrapper script for running storage lifecycle operations with dry-run support.
Promotes artifacts between tiers and purges expired artifacts based on retention policies.

Usage:
    python scripts/lifecycle_run.py --dry-run
    python scripts/lifecycle_run.py --live
    python scripts/lifecycle_run.py --summary
    python scripts/lifecycle_run.py --live --verbose
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from relay_ai.storage.lifecycle import (  # noqa: E402
    get_lifecycle_log_path,
    get_recent_lifecycle_events,
    get_retention_days,
    run_lifecycle_job,
)
from relay_ai.storage.tiered_store import TIER_COLD, TIER_HOT, TIER_WARM, get_all_tier_stats  # noqa: E402


def print_summary_table(results: dict[str, Any]) -> None:
    """
    Print a formatted summary table of lifecycle results.

    Args:
        results: Results dictionary from run_lifecycle_job()
    """
    print("\n" + "=" * 70)
    print("LIFECYCLE JOB SUMMARY")
    print("=" * 70)

    # Job metadata
    print(f"Timestamp:     {results.get('timestamp', 'N/A')}")
    print(f"Mode:          {'DRY RUN' if results.get('dry_run') else 'LIVE'}")
    print(f"Duration:      {results.get('job_duration_seconds', 0):.2f}s")
    print()

    # Operations
    print("Operations:")
    print(f"  Hot -> Warm:  {results.get('promoted_to_warm', 0):4d} artifacts")
    print(f"  Warm -> Cold: {results.get('promoted_to_cold', 0):4d} artifacts")
    print(f"  Cold -> Purge:{results.get('purged', 0):4d} artifacts")
    print()

    # Errors
    errors = results.get("total_errors", 0)
    if errors > 0:
        print(f"� Errors:       {errors} (check logs for details)")
    else:
        print(" No errors")

    print("=" * 70)


def print_tier_stats(verbose: bool = False) -> None:
    """
    Print current tier statistics.

    Args:
        verbose: If True, show detailed breakdown
    """
    print("\n" + "=" * 70)
    print("CURRENT TIER STATISTICS")
    print("=" * 70)

    stats = get_all_tier_stats()

    for tier in [TIER_HOT, TIER_WARM, TIER_COLD]:
        tier_stats = stats.get(tier, {})
        count = tier_stats.get("artifact_count", 0)
        size_bytes = tier_stats.get("total_bytes", 0)
        tenants = tier_stats.get("tenant_count", 0)

        size_mb = size_bytes / (1024 * 1024)
        print(f"{tier.upper():5s} Tier: {count:5d} artifacts, {size_mb:8.2f} MB, {tenants:3d} tenants")

        if verbose and count > 0:
            workflows = tier_stats.get("workflow_count", 0)
            avg_size = size_bytes / count if count > 0 else 0
            print(f"           Workflows: {workflows}, Avg size: {avg_size / 1024:.1f} KB")

    print("=" * 70)


def print_retention_policies() -> None:
    """Print current retention policies."""
    retention = get_retention_days()

    print("\n" + "=" * 70)
    print("RETENTION POLICIES")
    print("=" * 70)
    print(f"Hot tier:  {retention['hot_days']:3d} days (then promote to warm)")
    print(f"Warm tier: {retention['warm_days']:3d} days (then promote to cold)")
    print(f"Cold tier: {retention['cold_days']:3d} days (then purge permanently)")
    print("=" * 70)


def print_recent_events(limit: int = 10) -> None:
    """
    Print recent lifecycle events from the log.

    Args:
        limit: Maximum number of events to show
    """
    print("\n" + "=" * 70)
    print(f"RECENT LIFECYCLE EVENTS (last {limit})")
    print("=" * 70)

    try:
        events = get_recent_lifecycle_events(limit=limit)

        if not events:
            print("No recent events")
        else:
            for i, event in enumerate(events, 1):
                timestamp = event.get("timestamp", "N/A")
                event_type = event.get("event_type", "unknown")
                tenant = event.get("tenant_id", "?")
                artifact = event.get("artifact_id", "?")
                dry_run = " [DRY-RUN]" if event.get("dry_run") else ""

                print(f"{i:2d}. [{timestamp}] {event_type:20s} {tenant}/{artifact}{dry_run}")

    except Exception as e:
        print(f"Error reading events: {e}")

    print("=" * 70)


def main():
    """Main entry point for lifecycle runner."""
    parser = argparse.ArgumentParser(
        description="Storage Lifecycle Job Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would happen
  python scripts/lifecycle_run.py --dry-run

  # Execute lifecycle job
  python scripts/lifecycle_run.py --live

  # Show current state without running
  python scripts/lifecycle_run.py --summary

  # Run with verbose output
  python scripts/lifecycle_run.py --live --verbose

Environment Variables:
  HOT_RETENTION_DAYS=7    # Days before hot � warm
  WARM_RETENTION_DAYS=30  # Days before warm � cold
  COLD_RETENTION_DAYS=90  # Days before cold � purge
  STORAGE_BASE_PATH=artifacts
  LOG_DIR=logs
        """,
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--dry-run", action="store_true", help="Dry run mode - show what would happen without making changes"
    )
    mode_group.add_argument("--live", action="store_true", help="Live mode - execute lifecycle operations")
    mode_group.add_argument("--summary", action="store_true", help="Show current state without running lifecycle job")

    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output with detailed statistics")

    parser.add_argument(
        "--show-events", type=int, default=0, metavar="N", help="Show N recent lifecycle events (default: 0)"
    )

    args = parser.parse_args()

    # Summary mode - just show state
    if args.summary:
        print_retention_policies()
        print_tier_stats(verbose=args.verbose)

        if args.show_events > 0:
            print_recent_events(limit=args.show_events)

        print(f"\nLifecycle log: {get_lifecycle_log_path()}")
        return 0

    # Determine mode
    dry_run = args.dry_run
    mode_str = "DRY RUN" if dry_run else "LIVE"

    print("=" * 70)
    print(f"STORAGE LIFECYCLE JOB - {mode_str} MODE")
    print("=" * 70)
    print(f"Started: {datetime.utcnow().isoformat()}")

    # Show policies
    print_retention_policies()

    # Show pre-job state
    if args.verbose:
        print("\n=� BEFORE:")
        print_tier_stats(verbose=True)

    # Run the job
    print(f"\n= Running lifecycle job ({mode_str})...")
    start_time = time.time()

    try:
        results = run_lifecycle_job(dry_run=dry_run)
        elapsed = time.time() - start_time
        results["job_duration_seconds"] = elapsed

        # Show results
        print_summary_table(results)

        # Show post-job state
        if args.verbose and not dry_run:
            print("\n=� AFTER:")
            print_tier_stats(verbose=True)

        # Show recent events if requested
        if args.show_events > 0:
            print_recent_events(limit=args.show_events)

        # Success message
        total_ops = results.get("promoted_to_warm", 0) + results.get("promoted_to_cold", 0) + results.get("purged", 0)
        if total_ops == 0:
            print("\n9 No artifacts needed promotion or purging")
        else:
            if dry_run:
                print(f"\n Dry run complete - {total_ops} operations would be performed")
            else:
                print(f"\n Lifecycle job complete - {total_ops} operations performed")

        print(f"\nLog file: {get_lifecycle_log_path()}")

        return 0

    except Exception as e:
        print(f"\n ERROR: {e}")
        import traceback

        if args.verbose:
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
