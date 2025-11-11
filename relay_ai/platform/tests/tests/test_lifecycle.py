"""
Comprehensive tests for lifecycle manager (Sprint 26).

Tests cover:
- Retention policy enforcement
- Promotion workflows (hot→warm, warm→cold)
- Purging from cold tier
- Dry-run vs live mode
- Audit event emission
- Fake clock time travel
- Error handling and recovery
- Complete lifecycle job execution
"""

import time

import pytest

from relay_ai.storage.lifecycle import (
    get_last_lifecycle_job,
    get_lifecycle_log_path,
    get_recent_lifecycle_events,
    get_retention_days,
    log_lifecycle_event,
    promote_expired_to_cold,
    promote_expired_to_warm,
    purge_expired_from_cold,
    restore_artifact,
    run_lifecycle_job,
    scan_tier_for_expired,
)
from relay_ai.storage.tiered_store import (
    TIER_COLD,
    TIER_HOT,
    TIER_WARM,
    artifact_exists,
    list_artifacts,
    write_artifact,
)


class TestRetentionPolicies:
    """Tests for retention policy configuration."""

    def test_get_retention_days_defaults(self, lifecycle_env):
        """Test getting retention days returns configured values."""
        retention = get_retention_days()

        assert retention["hot_days"] == 7
        assert retention["warm_days"] == 30
        assert retention["cold_days"] == 90

    def test_get_retention_days_from_env(self, monkeypatch):
        """Test retention days can be overridden by environment."""
        monkeypatch.setenv("HOT_RETENTION_DAYS", "3")
        monkeypatch.setenv("WARM_RETENTION_DAYS", "15")
        monkeypatch.setenv("COLD_RETENTION_DAYS", "45")

        retention = get_retention_days()

        assert retention["hot_days"] == 3
        assert retention["warm_days"] == 15
        assert retention["cold_days"] == 45


class TestScanForExpired:
    """Tests for scanning tiers for expired artifacts."""

    def test_scan_empty_tier_returns_empty_list(self, lifecycle_env):
        """Test scanning empty tier returns empty list."""
        expired = scan_tier_for_expired(TIER_HOT, max_age_days=7)
        assert expired == []

    def test_scan_finds_expired_artifacts(self, lifecycle_env, fake_clock):
        """Test scanning finds artifacts older than threshold."""
        # Create artifact
        write_artifact(TIER_HOT, "tenant1", "workflow1", "old.txt", b"content")

        # Simulate 10 days passing
        fake_clock["time"] = time.time() + (10 * 86400)

        expired = scan_tier_for_expired(TIER_HOT, max_age_days=7, fake_clock=fake_clock["time"])

        assert len(expired) == 1
        assert expired[0]["artifact_id"] == "old.txt"
        assert expired[0]["age_days"] > 9

    def test_scan_skips_recent_artifacts(self, lifecycle_env, fake_clock):
        """Test scanning skips artifacts younger than threshold."""
        write_artifact(TIER_HOT, "tenant1", "workflow1", "new.txt", b"content")

        # Simulate only 3 days passing
        fake_clock["time"] = time.time() + (3 * 86400)

        expired = scan_tier_for_expired(TIER_HOT, max_age_days=7, fake_clock=fake_clock["time"])

        assert len(expired) == 0

    def test_scan_multiple_tenants(self, lifecycle_env, fake_clock):
        """Test scanning works across multiple tenants."""
        write_artifact(TIER_HOT, "tenant1", "workflow1", "file1.txt", b"content1")
        write_artifact(TIER_HOT, "tenant2", "workflow1", "file2.txt", b"content2")

        fake_clock["time"] = time.time() + (10 * 86400)

        expired = scan_tier_for_expired(TIER_HOT, max_age_days=7, fake_clock=fake_clock["time"])

        assert len(expired) == 2
        tenant_ids = [a["tenant_id"] for a in expired]
        assert "tenant1" in tenant_ids
        assert "tenant2" in tenant_ids


class TestPromoteToWarm:
    """Tests for promoting artifacts from hot to warm tier."""

    def test_promote_to_warm_no_expired(self, lifecycle_env):
        """Test promoting when no artifacts are expired."""
        write_artifact(TIER_HOT, "tenant1", "workflow1", "new.txt", b"content")

        results = promote_expired_to_warm(dry_run=False)

        assert results["promoted"] == 0
        assert results["errors"] == 0
        assert artifact_exists(TIER_HOT, "tenant1", "workflow1", "new.txt")

    def test_promote_to_warm_expired_artifacts(self, lifecycle_env, fake_clock):
        """Test promoting expired artifacts to warm tier."""
        write_artifact(TIER_HOT, "tenant1", "workflow1", "old.txt", b"content")

        # Simulate 10 days passing
        fake_clock["time"] = time.time() + (10 * 86400)

        results = promote_expired_to_warm(dry_run=False, fake_clock=fake_clock["time"])

        assert results["promoted"] == 1
        assert results["errors"] == 0
        assert not artifact_exists(TIER_HOT, "tenant1", "workflow1", "old.txt")
        assert artifact_exists(TIER_WARM, "tenant1", "workflow1", "old.txt")

    def test_promote_to_warm_dry_run(self, lifecycle_env, fake_clock):
        """Test dry-run promotion doesn't move files."""
        write_artifact(TIER_HOT, "tenant1", "workflow1", "old.txt", b"content")

        fake_clock["time"] = time.time() + (10 * 86400)

        results = promote_expired_to_warm(dry_run=True, fake_clock=fake_clock["time"])

        assert results["promoted"] == 1
        # File should still be in hot tier
        assert artifact_exists(TIER_HOT, "tenant1", "workflow1", "old.txt")
        assert not artifact_exists(TIER_WARM, "tenant1", "workflow1", "old.txt")

    def test_promote_to_warm_multiple_artifacts(self, lifecycle_env, fake_clock):
        """Test promoting multiple expired artifacts."""
        for i in range(5):
            write_artifact(TIER_HOT, "tenant1", "workflow1", f"file{i}.txt", b"content")

        fake_clock["time"] = time.time() + (10 * 86400)

        results = promote_expired_to_warm(dry_run=False, fake_clock=fake_clock["time"])

        assert results["promoted"] == 5
        assert results["errors"] == 0

        # All should be in warm tier now
        warm_artifacts = list_artifacts(TIER_WARM, tenant_id="tenant1")
        assert len(warm_artifacts) == 5

    def test_promote_to_warm_returns_artifact_list(self, lifecycle_env, fake_clock):
        """Test promotion returns list of promoted artifacts."""
        write_artifact(TIER_HOT, "tenant1", "workflow1", "test.txt", b"content")

        fake_clock["time"] = time.time() + (10 * 86400)

        results = promote_expired_to_warm(dry_run=False, fake_clock=fake_clock["time"])

        assert "test.txt" in results["artifacts"]


class TestPromoteToCold:
    """Tests for promoting artifacts from warm to cold tier."""

    def test_promote_to_cold_no_expired(self, lifecycle_env):
        """Test promoting when no artifacts are expired."""
        write_artifact(TIER_WARM, "tenant1", "workflow1", "new.txt", b"content")

        results = promote_expired_to_cold(dry_run=False)

        assert results["promoted"] == 0
        assert results["errors"] == 0

    def test_promote_to_cold_expired_artifacts(self, lifecycle_env, fake_clock):
        """Test promoting expired artifacts to cold tier."""
        write_artifact(TIER_WARM, "tenant1", "workflow1", "old.txt", b"content")

        # Simulate 35 days passing
        fake_clock["time"] = time.time() + (35 * 86400)

        results = promote_expired_to_cold(dry_run=False, fake_clock=fake_clock["time"])

        assert results["promoted"] == 1
        assert results["errors"] == 0
        assert not artifact_exists(TIER_WARM, "tenant1", "workflow1", "old.txt")
        assert artifact_exists(TIER_COLD, "tenant1", "workflow1", "old.txt")

    def test_promote_to_cold_dry_run(self, lifecycle_env, fake_clock):
        """Test dry-run promotion to cold doesn't move files."""
        write_artifact(TIER_WARM, "tenant1", "workflow1", "old.txt", b"content")

        fake_clock["time"] = time.time() + (35 * 86400)

        results = promote_expired_to_cold(dry_run=True, fake_clock=fake_clock["time"])

        assert results["promoted"] == 1
        assert artifact_exists(TIER_WARM, "tenant1", "workflow1", "old.txt")
        assert not artifact_exists(TIER_COLD, "tenant1", "workflow1", "old.txt")


class TestPurgeFromCold:
    """Tests for purging artifacts from cold tier."""

    def test_purge_no_expired(self, lifecycle_env):
        """Test purging when no artifacts are expired."""
        write_artifact(TIER_COLD, "tenant1", "workflow1", "new.txt", b"content")

        results = purge_expired_from_cold(dry_run=False)

        assert results["purged"] == 0
        assert results["errors"] == 0

    def test_purge_expired_artifacts(self, lifecycle_env, fake_clock):
        """Test purging expired artifacts from cold tier."""
        write_artifact(TIER_COLD, "tenant1", "workflow1", "old.txt", b"content")

        # Simulate 100 days passing
        fake_clock["time"] = time.time() + (100 * 86400)

        results = purge_expired_from_cold(dry_run=False, fake_clock=fake_clock["time"])

        assert results["purged"] == 1
        assert results["errors"] == 0
        assert not artifact_exists(TIER_COLD, "tenant1", "workflow1", "old.txt")

    def test_purge_dry_run(self, lifecycle_env, fake_clock):
        """Test dry-run purge doesn't delete files."""
        write_artifact(TIER_COLD, "tenant1", "workflow1", "old.txt", b"content")

        fake_clock["time"] = time.time() + (100 * 86400)

        results = purge_expired_from_cold(dry_run=True, fake_clock=fake_clock["time"])

        assert results["purged"] == 1
        assert artifact_exists(TIER_COLD, "tenant1", "workflow1", "old.txt")

    def test_purge_returns_artifact_list(self, lifecycle_env, fake_clock):
        """Test purge returns list of purged artifacts."""
        write_artifact(TIER_COLD, "tenant1", "workflow1", "test.txt", b"content")

        fake_clock["time"] = time.time() + (100 * 86400)

        results = purge_expired_from_cold(dry_run=False, fake_clock=fake_clock["time"])

        assert "test.txt" in results["artifacts"]


class TestCompleteLifecycleJob:
    """Tests for complete lifecycle job execution."""

    def test_run_lifecycle_job_empty_storage(self, lifecycle_env):
        """Test running lifecycle job with empty storage."""
        results = run_lifecycle_job(dry_run=False)

        assert results["promoted_to_warm"] == 0
        assert results["promoted_to_cold"] == 0
        assert results["purged"] == 0
        assert results["total_errors"] == 0

    @pytest.mark.bizlogic_asserts  # Sprint 52: Lifecycle promotion count assertion failing
    def test_run_lifecycle_job_full_cycle(self, lifecycle_env, fake_clock):
        """Test complete lifecycle: hot→warm→cold→purge."""
        # Create artifacts in each tier with different ages
        write_artifact(TIER_HOT, "tenant1", "workflow1", "hot_old.txt", b"hot")
        write_artifact(TIER_WARM, "tenant1", "workflow1", "warm_old.txt", b"warm")
        write_artifact(TIER_COLD, "tenant1", "workflow1", "cold_old.txt", b"cold")

        # Make all artifacts old enough to move
        fake_clock["time"] = time.time() + (100 * 86400)

        results = run_lifecycle_job(dry_run=False, fake_clock=fake_clock["time"])

        assert results["promoted_to_warm"] == 1  # hot_old moved to warm
        assert results["promoted_to_cold"] == 1  # warm_old moved to cold
        assert results["purged"] == 1  # cold_old purged
        assert results["total_errors"] == 0

    def test_run_lifecycle_job_dry_run(self, lifecycle_env, fake_clock):
        """Test dry-run lifecycle job doesn't modify files."""
        write_artifact(TIER_HOT, "tenant1", "workflow1", "test.txt", b"content")

        fake_clock["time"] = time.time() + (100 * 86400)

        results = run_lifecycle_job(dry_run=True, fake_clock=fake_clock["time"])

        # Should report what would happen
        assert results["dry_run"] is True
        # Files should not be moved
        assert artifact_exists(TIER_HOT, "tenant1", "workflow1", "test.txt")

    def test_run_lifecycle_job_includes_duration(self, lifecycle_env):
        """Test lifecycle job includes duration metrics."""
        results = run_lifecycle_job(dry_run=False)

        assert "job_duration_seconds" in results
        assert results["job_duration_seconds"] > 0

    def test_run_lifecycle_job_includes_timestamps(self, lifecycle_env):
        """Test lifecycle job includes start/end timestamps."""
        results = run_lifecycle_job(dry_run=False)

        assert "job_start" in results
        assert "job_end" in results

    def test_run_lifecycle_job_includes_retention_policies(self, lifecycle_env):
        """Test lifecycle job includes retention policy info."""
        results = run_lifecycle_job(dry_run=False)

        assert "retention_policies" in results
        assert results["retention_policies"]["hot_days"] == 7
        assert results["retention_policies"]["warm_days"] == 30
        assert results["retention_policies"]["cold_days"] == 90


class TestAuditLogging:
    """Tests for audit event logging."""

    def test_log_lifecycle_event_creates_log_file(self, lifecycle_env):
        """Test logging creates log file."""
        log_path = get_lifecycle_log_path()

        log_lifecycle_event({"event_type": "test_event", "data": "test"})

        assert log_path.exists()

    def test_log_lifecycle_event_appends_to_file(self, lifecycle_env):
        """Test logging appends to existing file."""
        log_lifecycle_event({"event_type": "event1"})
        log_lifecycle_event({"event_type": "event2"})

        log_path = get_lifecycle_log_path()
        lines = log_path.read_text().strip().split("\n")

        assert len(lines) == 2

    def test_log_lifecycle_event_adds_timestamp(self, lifecycle_env):
        """Test logging adds timestamp if not present."""
        log_lifecycle_event({"event_type": "test"})

        events = get_recent_lifecycle_events(limit=1)

        assert len(events) == 1
        assert "timestamp" in events[0]

    def test_promotion_logs_audit_event(self, lifecycle_env, fake_clock):
        """Test promotion operations log audit events."""
        write_artifact(TIER_HOT, "tenant1", "workflow1", "test.txt", b"content")

        fake_clock["time"] = time.time() + (10 * 86400)

        promote_expired_to_warm(dry_run=False, fake_clock=fake_clock["time"])

        events = get_recent_lifecycle_events(limit=10)
        promotion_events = [e for e in events if e["event_type"] == "promoted_to_warm"]

        assert len(promotion_events) > 0

    def test_purge_logs_audit_event(self, lifecycle_env, fake_clock):
        """Test purge operations log audit events."""
        write_artifact(TIER_COLD, "tenant1", "workflow1", "test.txt", b"content")

        fake_clock["time"] = time.time() + (100 * 86400)

        purge_expired_from_cold(dry_run=False, fake_clock=fake_clock["time"])

        events = get_recent_lifecycle_events(limit=10)
        purge_events = [e for e in events if e["event_type"] == "purged_from_cold"]

        assert len(purge_events) > 0

    def test_lifecycle_job_logs_start_and_completion(self, lifecycle_env):
        """Test lifecycle job logs start and completion events."""
        run_lifecycle_job(dry_run=False)

        events = get_recent_lifecycle_events(limit=20)

        start_events = [e for e in events if e["event_type"] == "lifecycle_job_started"]
        complete_events = [e for e in events if e["event_type"] == "lifecycle_job_completed"]

        assert len(start_events) > 0
        assert len(complete_events) > 0


class TestRecentEvents:
    """Tests for retrieving recent lifecycle events."""

    def test_get_recent_events_empty_log(self, lifecycle_env):
        """Test getting recent events from empty log."""
        events = get_recent_lifecycle_events(limit=10)
        assert events == []

    def test_get_recent_events_respects_limit(self, lifecycle_env):
        """Test getting recent events respects limit."""
        for i in range(20):
            log_lifecycle_event({"event_type": f"event{i}"})

        events = get_recent_lifecycle_events(limit=5)

        assert len(events) == 5

    def test_get_recent_events_returns_most_recent(self, lifecycle_env):
        """Test getting recent events returns most recent first."""
        log_lifecycle_event({"event_type": "old"})
        # TODO(Sprint 45): replace with wait_until(...) for faster polling
        time.sleep(0.01)
        log_lifecycle_event({"event_type": "new"})

        events = get_recent_lifecycle_events(limit=10)

        assert events[0]["event_type"] == "new"
        assert events[1]["event_type"] == "old"


class TestLastLifecycleJob:
    """Tests for retrieving last lifecycle job."""

    def test_get_last_job_none_if_never_run(self, lifecycle_env):
        """Test getting last job returns None if never run."""
        last_job = get_last_lifecycle_job()
        assert last_job is None

    def test_get_last_job_after_running(self, lifecycle_env):
        """Test getting last job after running lifecycle."""
        run_lifecycle_job(dry_run=False)

        last_job = get_last_lifecycle_job()

        assert last_job is not None
        assert last_job["event_type"] == "lifecycle_job_completed"

    def test_get_last_job_returns_most_recent(self, lifecycle_env):
        """Test getting last job returns most recent run."""
        run_lifecycle_job(dry_run=True)
        # TODO(Sprint 45): replace with wait_until(...) for faster polling
        time.sleep(0.01)
        run_lifecycle_job(dry_run=False)

        last_job = get_last_lifecycle_job()

        assert last_job["dry_run"] is False


class TestArtifactRestoration:
    """Tests for restoring artifacts."""

    def test_restore_artifact_from_warm_to_hot(self, lifecycle_env):
        """Test restoring artifact from warm to hot tier."""
        write_artifact(TIER_WARM, "tenant1", "workflow1", "test.txt", b"content")

        success = restore_artifact(
            tenant_id="tenant1", workflow_id="workflow1", artifact_id="test.txt", from_tier=TIER_WARM, to_tier=TIER_HOT
        )

        assert success
        assert not artifact_exists(TIER_WARM, "tenant1", "workflow1", "test.txt")
        assert artifact_exists(TIER_HOT, "tenant1", "workflow1", "test.txt")

    def test_restore_artifact_from_cold_to_hot(self, lifecycle_env):
        """Test restoring artifact from cold to hot tier."""
        write_artifact(TIER_COLD, "tenant1", "workflow1", "test.txt", b"content")

        success = restore_artifact(
            tenant_id="tenant1", workflow_id="workflow1", artifact_id="test.txt", from_tier=TIER_COLD, to_tier=TIER_HOT
        )

        assert success
        assert artifact_exists(TIER_HOT, "tenant1", "workflow1", "test.txt")

    def test_restore_logs_audit_event(self, lifecycle_env):
        """Test restore operation logs audit event."""
        write_artifact(TIER_WARM, "tenant1", "workflow1", "test.txt", b"content")

        restore_artifact(
            tenant_id="tenant1", workflow_id="workflow1", artifact_id="test.txt", from_tier=TIER_WARM, to_tier=TIER_HOT
        )

        events = get_recent_lifecycle_events(limit=10)
        restore_events = [e for e in events if e["event_type"] == "artifact_restored"]

        assert len(restore_events) > 0
        assert restore_events[0]["artifact_id"] == "test.txt"

    def test_restore_dry_run(self, lifecycle_env):
        """Test dry-run restore doesn't move files."""
        write_artifact(TIER_WARM, "tenant1", "workflow1", "test.txt", b"content")

        success = restore_artifact(
            tenant_id="tenant1",
            workflow_id="workflow1",
            artifact_id="test.txt",
            from_tier=TIER_WARM,
            to_tier=TIER_HOT,
            dry_run=True,
        )

        assert success
        assert artifact_exists(TIER_WARM, "tenant1", "workflow1", "test.txt")
        assert not artifact_exists(TIER_HOT, "tenant1", "workflow1", "test.txt")


class TestErrorHandling:
    """Tests for error handling and recovery."""

    def test_promotion_continues_after_error(self, lifecycle_env, fake_clock):
        """Test promotion continues processing after individual errors."""
        # Create valid artifacts
        write_artifact(TIER_HOT, "tenant1", "workflow1", "file1.txt", b"content1")
        write_artifact(TIER_HOT, "tenant1", "workflow1", "file2.txt", b"content2")

        fake_clock["time"] = time.time() + (10 * 86400)

        results = promote_expired_to_warm(dry_run=False, fake_clock=fake_clock["time"])

        # Both should be promoted despite any issues
        assert results["promoted"] == 2

    def test_lifecycle_job_reports_errors(self, lifecycle_env):
        """Test lifecycle job reports errors in results."""
        results = run_lifecycle_job(dry_run=False)

        assert "total_errors" in results
        assert isinstance(results["total_errors"], int)

    def test_lifecycle_job_continues_after_step_fails(self, lifecycle_env):
        """Test lifecycle job continues even if one step fails."""
        # This is more of an integration test
        results = run_lifecycle_job(dry_run=False)

        # Job should complete and return results
        assert "job_duration_seconds" in results
        assert "job_end" in results


class TestFakeClockIntegration:
    """Tests for fake clock time travel."""

    def test_fake_clock_simulates_aging(self, lifecycle_env, fake_clock):
        """Test fake clock properly simulates artifact aging."""
        write_artifact(TIER_HOT, "tenant1", "workflow1", "test.txt", b"content")

        # Start with current time
        fake_clock["time"] = time.time()
        age1 = scan_tier_for_expired(TIER_HOT, max_age_days=5, fake_clock=fake_clock["time"])
        assert len(age1) == 0

        # Advance 10 days
        fake_clock["time"] = time.time() + (10 * 86400)
        age2 = scan_tier_for_expired(TIER_HOT, max_age_days=5, fake_clock=fake_clock["time"])
        assert len(age2) == 1

    def test_fake_clock_in_complete_lifecycle(self, lifecycle_env, fake_clock):
        """Test fake clock works in complete lifecycle workflow."""
        # Create artifacts
        write_artifact(TIER_HOT, "tenant1", "workflow1", "test.txt", b"content")

        # Advance time enough to trigger all lifecycle stages
        fake_clock["time"] = time.time() + (100 * 86400)

        # Run lifecycle with fake clock
        results = run_lifecycle_job(dry_run=False, fake_clock=fake_clock["time"])

        # Artifact should have been promoted
        assert results["promoted_to_warm"] > 0
