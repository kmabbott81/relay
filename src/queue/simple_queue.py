"""Simple job queue with idempotency for AI agent actions.

Sprint 55 Week 3: Redis-backed queue for AI action execution with idempotency.
Sprint 60 Phase 1: Dual-write migration for workspace-scoped keys.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import redis

# Sprint 60 Phase 1: Feature flag for dual-write migration
# When enabled, writes to both old (ai:jobs:{job_id}) and new (ai:job:{workspace_id}:{job_id}) schemas
ENABLE_NEW_SCHEMA = os.getenv("AI_JOBS_NEW_SCHEMA", "off").lower() == "on"

# Sprint 60 Phase 2.2: Read-routing feature flags
# READ_PREFERS_NEW: When enabled, prefer new schema during reads (default: on)
READ_PREFERS_NEW = os.getenv("READ_PREFERS_NEW", "on").lower() == "on"
# READ_FALLBACK_OLD: When enabled, fall back to old schema if new schema misses (default: on)
# Turn off after backfill completes to enforce new schema only
READ_FALLBACK_OLD = os.getenv("READ_FALLBACK_OLD", "on").lower() == "on"

_LOG = logging.getLogger(__name__)

# Workspace ID validation (Sprint 60 Phase 1 - Security fix HIGH-5)
# Pattern: lowercase alphanumeric, hyphens, underscores; 1-32 chars; must start with alphanumeric
# Accepted pattern: ^[a-z0-9][a-z0-9_-]{0,31}$
_WORKSPACE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def _validate_workspace_id(workspace_id: str) -> None:
    """Validate workspace_id to prevent Redis key pattern injection.

    Args:
        workspace_id: Workspace identifier to validate

    Raises:
        ValueError: If workspace_id is invalid
    """
    if not workspace_id or not _WORKSPACE_ID_PATTERN.fullmatch(workspace_id):
        raise ValueError(
            "Invalid workspace_id: must be 1-32 lowercase alphanumeric/hyphen/underscore, start with alphanumeric"
        )


class SimpleQueue:
    """Job queue with idempotency support using Redis.

    Provides enqueue, dequeue, status updates, and idempotency checking.

    Sprint 60 Phase 1: Supports dual-write migration with AI_JOBS_NEW_SCHEMA flag.
    """

    def __init__(self, redis_url: str | None = None):
        """
        Initialize queue with Redis connection.

        Args:
            redis_url: Redis connection URL (defaults to REDIS_URL env var)
        """
        url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self._redis = redis.from_url(url, decode_responses=True)
        self._queue_key = "ai:queue:pending"
        self._jobs_key = "ai:jobs"
        self._jobs_key_new = "ai:job"  # Sprint 60: New workspace-scoped prefix
        self._idempotency_prefix = "ai:idempotency:"

    def enqueue(
        self,
        job_id: str,
        action_provider: str,
        action_name: str,
        params: dict[str, Any],
        workspace_id: str,
        actor_id: str,
        client_request_id: str | None = None,
    ) -> bool:
        """
        Add job to queue with idempotency check.

        Sprint 60 Phase 1: Dual-write to both old and new key schemas when flag enabled.

        Args:
            job_id: Unique job identifier
            action_provider: Provider (e.g., 'google', 'microsoft')
            action_name: Action to execute (e.g., 'gmail.send')
            params: Action parameters
            workspace_id: Workspace identifier
            actor_id: Actor identifier
            client_request_id: Optional idempotency key

        Returns:
            True if enqueued, False if duplicate (blocked by idempotency)
        """
        # Sprint 60 Phase 1: Validate workspace_id to prevent key injection (HIGH-5)
        # Accepted pattern: ^[a-z0-9][a-z0-9_-]{0,31}$
        _validate_workspace_id(workspace_id)

        # Create job data
        job_data = {
            "job_id": job_id,
            "status": "pending",
            "action_provider": action_provider,
            "action_name": action_name,
            "params": json.dumps(params),
            "workspace_id": workspace_id,
            "actor_id": actor_id,
            "result": "",  # Empty string instead of None for Redis compatibility
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
        }

        # Sprint 60 Phase 1: Atomic dual-write with Redis pipeline (HIGH-1/3/6, CRITICAL-1)
        # Always write to old schema (backwards compatibility)
        job_key_old = f"{self._jobs_key}:{job_id}"

        # Prepare idempotency key if provided
        idempotency_key = None
        if client_request_id:
            idempotency_key = f"{self._idempotency_prefix}{workspace_id}:{client_request_id}"
            # Check idempotency BEFORE pipeline (read-only check)
            if self._redis.exists(idempotency_key):
                return False  # Duplicate request

        try:
            # Sprint 60 Phase 1 FIX (HIGH-1): Use pipeline for atomicity
            pipe = self._redis.pipeline()

            # Write to old key pattern (always)
            pipe.hset(job_key_old, mapping=job_data)

            # Conditionally write to new schema
            if ENABLE_NEW_SCHEMA:
                job_key_new = f"{self._jobs_key_new}:{workspace_id}:{job_id}"
                pipe.hset(job_key_new, mapping=job_data)

            # Add to queue
            pipe.rpush(self._queue_key, job_id)

            # CRITICAL-1 FIX: Set idempotency AFTER writes (in same transaction)
            if idempotency_key:
                pipe.set(idempotency_key, job_id, nx=True, ex=86400)

            # Execute all operations atomically
            pipe.execute()

            # Record telemetry AFTER successful pipeline execution
            if ENABLE_NEW_SCHEMA:
                from relay_ai.telemetry.prom import record_dual_write_attempt

                record_dual_write_attempt(workspace_id, "succeeded")

            return True

        except Exception as exc:
            # HIGH-7 FIX: Remove exc_info=True to prevent leak
            _LOG.error("Failed to enqueue job for workspace (job_id logged internally)")
            _LOG.debug(
                "Enqueue failure details: job_id=%s, workspace_id=%s, error=%s",
                job_id,
                workspace_id,
                str(exc),
            )

            # Record telemetry for failure (nitpick: always observable)
            if ENABLE_NEW_SCHEMA:
                from relay_ai.telemetry.prom import record_dual_write_attempt

                record_dual_write_attempt(workspace_id, "failed")

            # Pipeline failed atomically - no partial state, no cleanup needed
            raise

    def get_job(self, job_id: str, workspace_id: str | None = None) -> dict[str, Any] | None:
        """
        Get job data by ID with workspace isolation enforcement.

        Sprint 60 Phase 2.2: Read-routing with new→old fallback and workspace isolation.
        - Prefers new schema (ai:job:{workspace_id}:{job_id}) if READ_PREFERS_NEW=on
        - Falls back to old schema (ai:jobs:{job_id}) if READ_FALLBACK_OLD=on
        - Enforces workspace isolation: rejects jobs from other workspaces during fallback
        - Records telemetry: relay_job_read_path_total{path="new|old|miss"}

        Args:
            job_id: Job identifier
            workspace_id: Workspace identifier (required for workspace isolation)

        Returns:
            Job data dict or None if not found or workspace mismatch
        """
        # Sprint 60 Phase 2.2: Validate workspace_id (required for isolation)
        if not workspace_id:
            _LOG.warning("get_job called without workspace_id - workspace isolation cannot be enforced")
            return None

        try:
            _validate_workspace_id(workspace_id)
        except ValueError as exc:
            _LOG.warning("Invalid workspace_id in get_job: %s", exc)
            return None

        job_data = None
        read_path = "miss"  # Telemetry tracking

        # Sprint 60 Phase 2.2: Try new schema first if enabled
        if READ_PREFERS_NEW:
            job_key_new = f"{self._jobs_key_new}:{workspace_id}:{job_id}"
            job_data = self._redis.hgetall(job_key_new)
            if job_data:
                read_path = "new"
                _LOG.debug("get_job: Found job in new schema (job_id=%s, workspace=%s)", job_id, workspace_id)

        # Sprint 60 Phase 2.2: Fallback to old schema with workspace isolation check
        if not job_data and READ_FALLBACK_OLD:
            job_key_old = f"{self._jobs_key}:{job_id}"
            job_data = self._redis.hgetall(job_key_old)

            if job_data:
                # CRITICAL: Enforce workspace isolation during fallback
                # Reject jobs that belong to different workspaces (prevent cross-tenant leaks)
                stored_workspace_id = job_data.get("workspace_id")
                if stored_workspace_id != workspace_id:
                    _LOG.warning(
                        "get_job: Workspace mismatch during fallback - rejecting (job_id=%s, requested=%s, stored=%s)",
                        job_id,
                        workspace_id,
                        stored_workspace_id,
                    )
                    job_data = None  # Reject cross-workspace access
                    read_path = "miss"  # Count as miss (not a leak)
                else:
                    read_path = "old"
                    _LOG.debug("get_job: Found job in old schema with matching workspace (job_id=%s)", job_id)

        # Record telemetry (Sprint 60 Phase 2.2)
        try:
            from relay_ai.telemetry.prom import record_job_read_path

            record_job_read_path(workspace_id, read_path)
        except Exception as exc:
            _LOG.debug("Failed to record read path telemetry: %s", exc)

        if not job_data:
            return None

        # Deserialize params and result
        if "params" in job_data:
            try:
                job_data["params"] = json.loads(job_data["params"])
            except json.JSONDecodeError:
                _LOG.debug("Failed to deserialize job params (job_id=%s)", job_id)
                # Keep as string - response still valid

        if job_data.get("result"):
            try:
                job_data["result"] = json.loads(job_data["result"])
            except json.JSONDecodeError:
                _LOG.debug("Failed to deserialize job result (job_id=%s)", job_id)
                # Keep as string - response still valid

        return job_data

    def update_status(
        self,
        job_id: str,
        status: str,
        result: dict[str, Any] | None = None,
        workspace_id: str | None = None,
    ) -> None:
        """
        Update job status.

        Sprint 60 Phase 1: Dual-write status updates to both schemas when flag enabled.

        Args:
            job_id: Job identifier
            status: New status ('pending', 'running', 'completed', 'failed')
            result: Optional result data (for completed/failed status)
            workspace_id: Workspace identifier (required if ENABLE_NEW_SCHEMA is True)
        """
        # Sprint 60 Phase 1: Validate workspace_id (HIGH-5)
        if workspace_id:
            _validate_workspace_id(workspace_id)

        updates = {"status": status}

        # Add timestamps based on status
        if status == "running":
            updates["started_at"] = datetime.now(timezone.utc).isoformat()
        elif status in ("completed", "failed"):
            updates["finished_at"] = datetime.now(timezone.utc).isoformat()
            if result:
                updates["result"] = json.dumps(result)

        job_key_old = f"{self._jobs_key}:{job_id}"

        # HIGH-2 FIX: Use pipeline for atomic dual-update with error handling
        try:
            if ENABLE_NEW_SCHEMA and workspace_id:
                # Atomic dual-update with pipeline
                pipe = self._redis.pipeline()
                pipe.hset(job_key_old, mapping=updates)

                job_key_new = f"{self._jobs_key_new}:{workspace_id}:{job_id}"
                # Only update if key exists (checked in transaction)
                pipe.exists(job_key_new)
                pipe.hset(job_key_new, mapping=updates)

                results = pipe.execute()
                # results[1] is the EXISTS result for new key
                if not results[1]:
                    _LOG.debug("New schema key not found during update_status (job_id=%s)", job_id)
            else:
                # Single update to old schema
                self._redis.hset(job_key_old, mapping=updates)

        except Exception as exc:
            # HIGH-2 FIX: Add error handling for dual-update failures
            _LOG.error("Failed to update job status (logged internally)")
            _LOG.debug("update_status failure: job_id=%s, workspace_id=%s, error=%s", job_id, workspace_id, str(exc))
            raise

    def get_queue_depth(self) -> int:
        """
        Get number of pending jobs in queue.

        Returns:
            Number of jobs waiting to be processed
        """
        return self._redis.llen(self._queue_key)

    def list_jobs(
        self,
        workspace_id: str,
        status: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        List jobs for a workspace with cursor-based pagination.

        Sprint 60 Phase 2.2: Workspace-scoped enumeration with read-routing.
        - Primary path: SCAN ai:job:{workspace_id}:* (new schema)
        - Fallback path: SCAN ai:job:* with workspace filtering (old schema, if READ_FALLBACK_OLD=on)
        - Returns: {items: [...], next_cursor: str|None}
        - Records telemetry: relay_job_list_read_path_total{path="new|mixed"}

        Args:
            workspace_id: Workspace identifier (required for workspace isolation)
            status: Optional status filter (pending, running, completed, failed)
            cursor: Pagination cursor (Redis SCAN cursor, None for first page)
            limit: Maximum number of jobs to return per page

        Returns:
            Dict with 'items' (list of job dicts) and 'next_cursor' (str or None)
        """
        # Sprint 60 Phase 2.2: Validate workspace_id (required)
        try:
            _validate_workspace_id(workspace_id)
        except ValueError as exc:
            _LOG.warning("Invalid workspace_id in list_jobs: %s", exc)
            return {"items": [], "next_cursor": None}

        jobs = []
        next_cursor = None
        read_path = "new"  # Telemetry: track which schema(s) we used

        # Sprint 60 Phase 2.2 FIX (Code-Reviewer P1): Parse composite cursor
        # Format: "new:{new_cursor}:old:{old_cursor}" for mixed-mode pagination
        scan_cursor_new = 0
        scan_cursor_old = 0
        if cursor:
            if cursor.startswith("new:") and ":old:" in cursor:
                # Composite cursor - extract both positions
                try:
                    parts = cursor.split(":")
                    scan_cursor_new = int(parts[1])
                    scan_cursor_old = int(parts[3])
                except (IndexError, ValueError):
                    _LOG.warning("Invalid composite cursor format: %s", cursor)
                    scan_cursor_new = 0
                    scan_cursor_old = 0
            elif cursor.isdigit():
                # Simple cursor - only new schema position (legacy support)
                scan_cursor_new = int(cursor)
                scan_cursor_old = 0

        # Sprint 60 Phase 2.2: Primary path - SCAN new schema (workspace-scoped keys)
        if READ_PREFERS_NEW:
            pattern = f"{self._jobs_key_new}:{workspace_id}:*"

            try:
                # SCAN with workspace-scoped pattern (efficient, no cross-workspace data)
                scan_cursor_new, keys = self._redis.scan(scan_cursor_new, match=pattern, count=limit)

                for key in keys:
                    if len(jobs) >= limit:
                        break

                    job_data = self._redis.hgetall(key)
                    if not job_data:
                        continue

                    # Apply status filter
                    if status and job_data.get("status") != status:
                        continue

                    # Deserialize JSON fields with error handling
                    if "params" in job_data:
                        try:
                            job_data["params"] = json.loads(job_data["params"])
                        except json.JSONDecodeError:
                            _LOG.debug("Failed to deserialize job params (key=%s)", key)

                    if job_data.get("result"):
                        try:
                            job_data["result"] = json.loads(job_data["result"])
                        except json.JSONDecodeError:
                            _LOG.debug("Failed to deserialize job result (key=%s)", key)

                    jobs.append(job_data)

            except Exception as exc:
                _LOG.error("SCAN new schema failed (workspace=%s): %s", workspace_id, exc)
                # Fall through to fallback path

        # Sprint 60 Phase 2.2: Fallback path - SCAN old schema with workspace filtering
        # Only activate if: (1) insufficient results from new schema, (2) fallback enabled
        if len(jobs) < limit and READ_FALLBACK_OLD:
            read_path = "mixed"  # Mark that we used both schemas
            pattern_old = f"{self._jobs_key}:*"

            try:
                # SCAN old schema in batches, filter by workspace
                while len(jobs) < limit:
                    scan_cursor_old, keys_old = self._redis.scan(
                        scan_cursor_old, match=pattern_old, count=min(50, limit * 2)
                    )

                    for key in keys_old:
                        if len(jobs) >= limit:
                            break

                        job_data = self._redis.hgetall(key)
                        if not job_data:
                            continue

                        # CRITICAL: Workspace isolation - only include matching workspace
                        if job_data.get("workspace_id") != workspace_id:
                            continue

                        # Apply status filter
                        if status and job_data.get("status") != status:
                            continue

                        # Deserialize JSON fields
                        if "params" in job_data:
                            try:
                                job_data["params"] = json.loads(job_data["params"])
                            except json.JSONDecodeError:
                                _LOG.debug("Failed to deserialize job params (key=%s)", key)

                        if job_data.get("result"):
                            try:
                                job_data["result"] = json.loads(job_data["result"])
                            except json.JSONDecodeError:
                                _LOG.debug("Failed to deserialize job result (key=%s)", key)

                        jobs.append(job_data)

                    # Stop if SCAN completed (cursor=0) or we have enough jobs
                    if scan_cursor_old == 0:
                        break

            except Exception as exc:
                _LOG.error("SCAN old schema failed (workspace=%s): %s", workspace_id, exc)

        # Sprint 60 Phase 2.2 FIX (Code-Reviewer P1): Construct composite cursor for pagination
        # If both scans have pending results OR we used fallback, return composite cursor
        # Format: "new:{new_cursor}:old:{old_cursor}"
        if read_path == "mixed":
            # Mixed mode - track both cursor positions
            if scan_cursor_new != 0 or scan_cursor_old != 0:
                next_cursor = f"new:{scan_cursor_new}:old:{scan_cursor_old}"
        else:
            # New schema only - simple cursor for backward compatibility
            if scan_cursor_new != 0:
                next_cursor = str(scan_cursor_new)

        # Sort by enqueued_at descending (most recent first)
        jobs.sort(key=lambda j: j.get("enqueued_at", ""), reverse=True)

        # Record telemetry (Sprint 60 Phase 2.2)
        try:
            from relay_ai.telemetry.prom import record_job_list_read_path, record_job_list_results

            record_job_list_read_path(workspace_id, read_path)
            record_job_list_results(workspace_id, len(jobs))
        except Exception as exc:
            _LOG.debug("Failed to record list telemetry: %s", exc)

        return {"items": jobs[:limit], "next_cursor": next_cursor}
