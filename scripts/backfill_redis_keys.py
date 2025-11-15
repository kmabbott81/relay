"""Sprint 60 Phase 3: Backfill old→new Redis keys with zero-downtime migration.

Migrates jobs from old schema (ai:jobs:{job_id}) to new schema (ai:job:{workspace_id}:{job_id}).
Idempotent, resumable, rate-limited, and fully observable.

Usage:
    python -m scripts.backfill_redis_keys --dry-run --rps 200
    python -m scripts.backfill_redis_keys --execute --rps 100 --batch 500
"""

import argparse
import logging
import os
import re
import sys
import time
from typing import Any

import redis

# Workspace ID validation (matches Sprint 60 Phase 1 pattern)
_WORKSPACE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")

_LOG = logging.getLogger(__name__)


def _validate_workspace_id(workspace_id: str) -> bool:
    """Validate workspace_id format (Sprint 60 Phase 1 compatibility)."""
    return bool(workspace_id and _WORKSPACE_ID_PATTERN.fullmatch(workspace_id))


def _record_telemetry(metric: str, workspace_id: str, **labels: str) -> None:
    """Record telemetry with bounded workspace labels (best-effort)."""
    try:
        from relay_ai.telemetry.prom import (
            backfill_errors_total,
            backfill_migrated_total,
            backfill_scanned_total,
            backfill_skipped_total,
        )

        if metric == "scanned":
            backfill_scanned_total.labels(workspace_id=workspace_id).inc()
        elif metric == "migrated":
            backfill_migrated_total.labels(workspace_id=workspace_id).inc()
        elif metric == "skipped":
            reason = labels.get("reason", "unknown")
            backfill_skipped_total.labels(workspace_id=workspace_id, reason=reason).inc()
        elif metric == "errors":
            backfill_errors_total.labels(workspace_id=workspace_id).inc()
    except Exception as exc:
        _LOG.debug("Telemetry recording failed: %s", exc)


def backfill_keys(
    redis_url: str,
    dry_run: bool,
    rps: int,
    batch: int,
    cursor: str,
    max_keys: int | None,
    workspace_filter: str | None,
    progress_key_prefix: str,
) -> dict[str, Any]:
    """
    Backfill old schema keys to new schema with rate limiting and resumability.

    Args:
        redis_url: Redis connection URL
        dry_run: If True, count migrations without writing
        rps: Rate limit (requests per second)
        batch: SCAN count parameter (batch size)
        cursor: Starting cursor position (0 or composite format)
        max_keys: Optional maximum keys to process
        workspace_filter: Optional workspace ID to restrict migration
        progress_key_prefix: Redis key prefix for progress tracking

    Returns:
        Statistics dict with scanned/migrated/skipped/errors counts
    """
    client = redis.from_url(redis_url, decode_responses=True)

    # Parse starting cursor
    scan_cursor = int(cursor) if cursor.isdigit() else 0

    # Initialize statistics
    stats = {
        "scanned": 0,
        "migrated": 0,
        "skipped_exists": 0,
        "skipped_invalid": 0,
        "errors": 0,
        "last_job_id": None,
    }

    # Try to resume from stored progress
    stored_cursor_key = f"{progress_key_prefix}:cursor"
    stored_last_job_key = f"{progress_key_prefix}:last_job"

    if scan_cursor == 0:
        stored_cursor = client.get(stored_cursor_key)
        if stored_cursor:
            scan_cursor = int(stored_cursor)
            stats["last_job_id"] = client.get(stored_last_job_key)
            _LOG.info("Resuming from stored cursor=%d, last_job=%s", scan_cursor, stats["last_job_id"])

    _LOG.info(
        "Starting backfill: dry_run=%s, rps=%d, batch=%d, cursor=%d, max_keys=%s, workspace=%s",
        dry_run,
        rps,
        batch,
        scan_cursor,
        max_keys or "unlimited",
        workspace_filter or "all",
    )

    sleep_interval = 1.0 / rps if rps > 0 else 0
    last_log_time = time.time()
    start_time = time.time()

    try:
        while True:
            # SCAN old schema keys
            scan_cursor, keys = client.scan(scan_cursor, match="ai:jobs:*", count=batch)

            for key in keys:
                # Check max_keys limit
                if max_keys and stats["scanned"] >= max_keys:
                    _LOG.info("Reached max_keys=%d, stopping", max_keys)
                    break

                stats["scanned"] += 1

                # Extract job_id from key
                job_id = key.split(":")[-1]

                # Fetch job data from old schema
                job_data = client.hgetall(key)
                if not job_data:
                    stats["skipped_invalid"] += 1
                    _record_telemetry("skipped", "unknown", reason="invalid")
                    continue

                # Validate workspace_id
                workspace_id = job_data.get("workspace_id")
                if not workspace_id or not _validate_workspace_id(workspace_id):
                    stats["skipped_invalid"] += 1
                    _record_telemetry("skipped", workspace_id or "unknown", reason="invalid")
                    _LOG.debug("Skipped job_id=%s: invalid workspace_id=%s", job_id, workspace_id)
                    continue

                # Apply workspace filter if specified
                if workspace_filter and workspace_id != workspace_filter:
                    continue

                # Record telemetry
                _record_telemetry("scanned", workspace_id)

                # Build new schema key
                new_key = f"ai:job:{workspace_id}:{job_id}"

                # Check if new key already exists
                if client.exists(new_key):
                    # Verify data matches (idempotency check)
                    existing_data = client.hgetall(new_key)
                    if existing_data == job_data:
                        stats["skipped_exists"] += 1
                        _record_telemetry("skipped", workspace_id, reason="exists")
                        continue

                # Migrate to new schema
                if not dry_run:
                    try:
                        # Use pipeline for atomicity
                        pipe = client.pipeline()
                        pipe.hset(new_key, mapping=job_data)
                        pipe.execute()

                        # Verify write succeeded
                        if not client.exists(new_key):
                            raise ValueError(f"Write verification failed for {new_key}")

                        stats["migrated"] += 1
                        _record_telemetry("migrated", workspace_id)
                    except Exception as exc:
                        stats["errors"] += 1
                        _record_telemetry("errors", workspace_id)
                        _LOG.error("Migration failed for job_id=%s: %s", job_id, exc)
                        continue
                else:
                    # Dry-run: just count
                    stats["migrated"] += 1

                stats["last_job_id"] = job_id

                # Rate limiting
                if sleep_interval > 0:
                    time.sleep(sleep_interval)

                # Progress logging every 5k jobs
                if stats["scanned"] % 5000 == 0:
                    elapsed = time.time() - last_log_time
                    current_rps = 5000 / elapsed if elapsed > 0 else 0
                    _LOG.info(
                        "Progress: scanned=%d, migrated=%d, skipped_exists=%d, skipped_invalid=%d, errors=%d, rps=%.1f",
                        stats["scanned"],
                        stats["migrated"],
                        stats["skipped_exists"],
                        stats["skipped_invalid"],
                        stats["errors"],
                        current_rps,
                    )
                    last_log_time = time.time()

            # Store progress for resumability
            if not dry_run:
                client.set(stored_cursor_key, str(scan_cursor), ex=86400)  # 24h TTL
                if stats["last_job_id"]:
                    client.set(stored_last_job_key, stats["last_job_id"], ex=86400)

            # Check if SCAN completed
            if scan_cursor == 0:
                break

    except KeyboardInterrupt:
        _LOG.warning("Interrupted by user at cursor=%d", scan_cursor)
        raise

    duration = time.time() - start_time

    _LOG.info(
        "Backfill complete: scanned=%d, migrated=%d, skipped_exists=%d, skipped_invalid=%d, errors=%d, duration=%.2fs",
        stats["scanned"],
        stats["migrated"],
        stats["skipped_exists"],
        stats["skipped_invalid"],
        stats["errors"],
        duration,
    )

    # Record duration telemetry
    try:
        from relay_ai.telemetry.prom import backfill_duration_seconds

        backfill_duration_seconds.observe(duration)
    except Exception:
        pass

    return stats


def main() -> int:
    """CLI entry point for backfill script."""
    parser = argparse.ArgumentParser(
        description="Sprint 60 Phase 3: Backfill old→new Redis keys",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Required: exactly one of --dry-run or --execute
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--dry-run", action="store_true", help="Count migrations without writing")
    mode_group.add_argument("--execute", action="store_true", help="Execute migrations")

    # Optional parameters
    parser.add_argument("--rps", type=int, default=100, help="Rate limit (requests per second, default 100)")
    parser.add_argument("--batch", type=int, default=500, help="SCAN batch size (default 500)")
    parser.add_argument("--cursor", type=str, default="0", help="Starting cursor (default 0)")
    parser.add_argument("--max-keys", type=int, help="Optional maximum keys to process")
    parser.add_argument("--workspace", type=str, help="Optional workspace ID filter")
    parser.add_argument(
        "--progress-key", type=str, default="ai:backfill", help="Progress key prefix (default ai:backfill)"
    )
    parser.add_argument("--redis-url", type=str, help="Redis URL (default from REDIS_URL env)")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Get Redis URL
    redis_url = args.redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")

    # Validate workspace filter if provided
    if args.workspace and not _validate_workspace_id(args.workspace):
        _LOG.error("Invalid workspace ID format: %s", args.workspace)
        return 1

    try:
        stats = backfill_keys(
            redis_url=redis_url,
            dry_run=args.dry_run,
            rps=args.rps,
            batch=args.batch,
            cursor=args.cursor,
            max_keys=args.max_keys,
            workspace_filter=args.workspace,
            progress_key_prefix=args.progress_key,
        )

        print("\n=== Backfill Summary ===")
        print(f"Scanned:        {stats['scanned']}")
        print(f"Migrated:       {stats['migrated']}")
        print(f"Skipped (exist):{stats['skipped_exists']}")
        print(f"Skipped (invalid):{stats['skipped_invalid']}")
        print(f"Errors:         {stats['errors']}")

        return 0

    except KeyboardInterrupt:
        _LOG.warning("Backfill interrupted")
        return 130
    except Exception as exc:
        _LOG.error("Backfill failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
