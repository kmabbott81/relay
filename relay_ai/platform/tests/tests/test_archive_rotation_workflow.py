"""
Tests for Archive Rotation Demo Workflow

Verifies artifact generation, lifecycle promotion, and restore operations
using temp directories and fake clock for CI-safe testing.
"""

import tempfile
import time
from pathlib import Path

import pytest

# Sprint 52: Quarantine marker - needs create_artifacts function
pytestmark = pytest.mark.needs_artifacts


@pytest.fixture
def temp_storage(monkeypatch):
    """Create temporary storage directories for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Set up temp storage paths
        hot_dir = tmpdir_path / "hot"
        warm_dir = tmpdir_path / "warm"
        cold_dir = tmpdir_path / "cold"
        logs_dir = tmpdir_path / "logs"

        hot_dir.mkdir()
        warm_dir.mkdir()
        cold_dir.mkdir()
        logs_dir.mkdir()

        # Override environment variables
        monkeypatch.setenv("STORAGE_BASE_PATH", str(tmpdir_path))
        monkeypatch.setenv("LOG_DIR", str(logs_dir))
        monkeypatch.setenv("HOT_RETENTION_DAYS", "7")
        monkeypatch.setenv("WARM_RETENTION_DAYS", "30")
        monkeypatch.setenv("COLD_RETENTION_DAYS", "365")

        yield {
            "base": tmpdir_path,
            "hot": hot_dir,
            "warm": warm_dir,
            "cold": cold_dir,
            "logs": logs_dir,
        }


@pytest.fixture
def fake_clock():
    """Provide fake clock time for simulating artifact age."""
    return time.time() + (10 * 86400)  # 10 days in future


def test_generate_markdown_artifact():
    """Test markdown artifact generation with checksum."""
    from src.workflows.stress.archive_rotation_demo import generate_markdown_artifact

    artifact_id, content = generate_markdown_artifact(1, "test_tenant", include_checksum=True)

    assert artifact_id == "demo_doc_0001.md"
    assert b"# Archive Demo Document 1" in content
    assert b"**Tenant:** test_tenant" in content
    assert b"Checksum (SHA-256)" in content
    assert len(content) > 500  # Should have substantial content


def test_generate_markdown_artifact_without_checksum():
    """Test markdown artifact generation without checksum."""
    from src.workflows.stress.archive_rotation_demo import generate_markdown_artifact

    artifact_id, content = generate_markdown_artifact(5, "test_tenant", include_checksum=False)

    assert artifact_id == "demo_doc_0005.md"
    assert b"Checksum (SHA-256)" not in content


def test_create_artifacts_dry_run(temp_storage, capsys):
    """Test artifact creation in dry-run mode."""
    from src.workflows.stress.archive_rotation_demo import create_artifacts

    created = create_artifacts("test_tenant", count=5, dry_run=True)

    captured = capsys.readouterr()
    assert "Would create: demo_doc_0001.md" in captured.out
    assert created == 0  # Dry run doesn't create files


def test_create_artifacts_live(temp_storage):
    """Test actual artifact creation."""
    from src.storage.tiered_store import TIER_HOT, list_artifacts
    from src.workflows.stress.archive_rotation_demo import create_artifacts

    created = create_artifacts("test_tenant", count=10, dry_run=False)

    assert created == 10

    # Verify artifacts exist in hot tier
    artifacts = list_artifacts(TIER_HOT, tenant_id="test_tenant")
    assert len(artifacts) == 10

    # Check first artifact
    assert artifacts[0]["workflow_id"] == "archive_demo"
    assert "demo_doc_" in artifacts[0]["artifact_id"]


def test_show_tier_counts(temp_storage, capsys):
    """Test tier statistics display."""
    from src.workflows.stress.archive_rotation_demo import create_artifacts, show_tier_counts

    # Create some artifacts
    create_artifacts("test_tenant", count=5, dry_run=False)

    # Show counts
    counts = show_tier_counts("test_tenant")

    captured = capsys.readouterr()
    assert "TIER STATISTICS" in captured.out
    assert "HOT" in captured.out
    assert counts["hot"] == 5
    assert counts["warm"] == 0
    assert counts["cold"] == 0


def test_lifecycle_promotion_with_fake_clock(temp_storage, fake_clock):
    """Test lifecycle promotion using fake clock to simulate age."""
    from src.storage.tiered_store import TIER_HOT, TIER_WARM, list_artifacts
    from src.workflows.stress.archive_rotation_demo import create_artifacts, demo_lifecycle_promotion

    # Create artifacts
    create_artifacts("test_tenant", count=5, dry_run=False)

    # Verify in hot tier
    hot_artifacts = list_artifacts(TIER_HOT, tenant_id="test_tenant")
    assert len(hot_artifacts) == 5

    # Run lifecycle with force-aging (10 days old)
    results = demo_lifecycle_promotion("test_tenant", force_age_days=10, dry_run=False)

    # Should promote to warm (>7 day retention)
    assert results["promoted_to_warm"] == 5
    assert results["promoted_to_cold"] == 0
    assert results["purged"] == 0

    # Verify artifacts moved to warm
    warm_artifacts = list_artifacts(TIER_WARM, tenant_id="test_tenant")
    assert len(warm_artifacts) == 5

    hot_artifacts_after = list_artifacts(TIER_HOT, tenant_id="test_tenant")
    assert len(hot_artifacts_after) == 0


def test_lifecycle_promotion_dry_run(temp_storage, fake_clock, capsys):
    """Test lifecycle promotion dry run."""
    from src.workflows.stress.archive_rotation_demo import create_artifacts, demo_lifecycle_promotion

    create_artifacts("test_tenant", count=3, dry_run=False)

    results = demo_lifecycle_promotion("test_tenant", force_age_days=10, dry_run=True)

    captured = capsys.readouterr()
    assert "[DRY-RUN]" in captured.out

    # Dry run doesn't actually move artifacts
    assert results["promoted_to_warm"] == 0


def test_demo_restore(temp_storage):
    """Test artifact restoration from warm to hot."""
    from src.storage.tiered_store import TIER_HOT, TIER_WARM, list_artifacts
    from src.workflows.stress.archive_rotation_demo import create_artifacts, demo_lifecycle_promotion, demo_restore

    # Create and promote to warm
    create_artifacts("test_tenant", count=3, dry_run=False)
    demo_lifecycle_promotion("test_tenant", force_age_days=10, dry_run=False)

    # Verify in warm
    warm_artifacts = list_artifacts(TIER_WARM, tenant_id="test_tenant")
    assert len(warm_artifacts) == 3

    # Restore one artifact
    success = demo_restore("test_tenant", dry_run=False)

    assert success is True

    # Verify artifact restored to hot
    hot_artifacts = list_artifacts(TIER_HOT, tenant_id="test_tenant")
    assert len(hot_artifacts) == 1

    warm_artifacts_after = list_artifacts(TIER_WARM, tenant_id="test_tenant")
    assert len(warm_artifacts_after) == 2


def test_demo_restore_dry_run(temp_storage, capsys):
    """Test restore dry run."""
    from src.workflows.stress.archive_rotation_demo import create_artifacts, demo_lifecycle_promotion, demo_restore

    create_artifacts("test_tenant", count=2, dry_run=False)
    demo_lifecycle_promotion("test_tenant", force_age_days=10, dry_run=False)

    _success = demo_restore("test_tenant", dry_run=True)

    captured = capsys.readouterr()
    assert "[DRY-RUN]" in captured.out
    assert "Would restore:" in captured.out


def test_full_lifecycle_workflow(temp_storage, fake_clock):
    """Test complete end-to-end workflow."""
    from src.workflows.stress.archive_rotation_demo import (
        create_artifacts,
        demo_lifecycle_promotion,
        demo_restore,
        show_tier_counts,
    )

    # 1. Create artifacts
    created = create_artifacts("test_tenant", count=10, dry_run=False)
    assert created == 10

    # 2. Check initial state
    counts = show_tier_counts("test_tenant")
    assert counts["hot"] == 10
    assert counts["warm"] == 0

    # 3. Promote hot -> warm (force age 10 days)
    results = demo_lifecycle_promotion("test_tenant", force_age_days=10, dry_run=False)
    assert results["promoted_to_warm"] == 10

    # 4. Check after first promotion
    counts = show_tier_counts("test_tenant")
    assert counts["hot"] == 0
    assert counts["warm"] == 10

    # 5. Promote warm -> cold (force age 35 days)
    results = demo_lifecycle_promotion("test_tenant", force_age_days=35, dry_run=False)
    assert results["promoted_to_cold"] == 10

    # 6. Check after second promotion
    counts = show_tier_counts("test_tenant")
    assert counts["warm"] == 0
    assert counts["cold"] == 10

    # 7. Restore one from cold
    success = demo_restore("test_tenant", dry_run=False)
    assert success is True

    # 8. Final state
    counts = show_tier_counts("test_tenant")
    assert counts["hot"] == 1
    assert counts["cold"] == 9


def test_tenant_isolation(temp_storage):
    """Test that tenants are properly isolated."""
    from src.storage.tiered_store import TIER_HOT, list_artifacts
    from src.workflows.stress.archive_rotation_demo import create_artifacts

    # Create artifacts for two tenants
    create_artifacts("tenant_a", count=5, dry_run=False)
    create_artifacts("tenant_b", count=3, dry_run=False)

    # Verify tenant A only sees their artifacts
    tenant_a_artifacts = list_artifacts(TIER_HOT, tenant_id="tenant_a")
    assert len(tenant_a_artifacts) == 5
    assert all(a["tenant_id"] == "tenant_a" for a in tenant_a_artifacts)

    # Verify tenant B only sees their artifacts
    tenant_b_artifacts = list_artifacts(TIER_HOT, tenant_id="tenant_b")
    assert len(tenant_b_artifacts) == 3
    assert all(a["tenant_id"] == "tenant_b" for a in tenant_b_artifacts)


def test_artifact_metadata(temp_storage):
    """Test artifact metadata is properly stored."""
    from src.storage.tiered_store import TIER_HOT, read_artifact
    from src.workflows.stress.archive_rotation_demo import create_artifacts

    create_artifacts("test_tenant", count=1, dry_run=False)

    # Read artifact with metadata
    content, metadata = read_artifact(TIER_HOT, "test_tenant", "archive_demo", "demo_doc_0001.md")

    assert metadata["demo_index"] == 1
    assert metadata["created_by"] == "archive_rotation_demo"
    assert metadata["checksum_included"] is True
    assert "_created_at" in metadata
    assert "_modified_at" in metadata


def test_purge_simulation(temp_storage, fake_clock):
    """Test purge simulation with extreme aging."""
    from src.storage.tiered_store import TIER_COLD, list_artifacts
    from src.workflows.stress.archive_rotation_demo import create_artifacts, demo_lifecycle_promotion

    # Create, age, and promote through all tiers
    create_artifacts("test_tenant", count=2, dry_run=False)

    # Hot -> Warm (10 days)
    demo_lifecycle_promotion("test_tenant", force_age_days=10, dry_run=False)

    # Warm -> Cold (35 days)
    demo_lifecycle_promotion("test_tenant", force_age_days=35, dry_run=False)

    # Cold -> Purge (400 days, exceeds 365 day retention)
    results = demo_lifecycle_promotion("test_tenant", force_age_days=400, dry_run=False)

    # Should purge from cold
    assert results["purged"] == 2

    # Verify artifacts gone
    cold_artifacts = list_artifacts(TIER_COLD, tenant_id="test_tenant")
    assert len(cold_artifacts) == 0


def test_lifecycle_events_logged(temp_storage):
    """Test that lifecycle events are logged."""
    from src.storage.lifecycle import get_recent_lifecycle_events
    from src.workflows.stress.archive_rotation_demo import create_artifacts

    create_artifacts("test_tenant", count=3, dry_run=False)

    # Check audit log
    events = get_recent_lifecycle_events(limit=10)

    assert len(events) > 0
    assert any(e["event_type"] == "demo_artifacts_created" for e in events)
    assert any(e["tenant_id"] == "test_tenant" for e in events)
