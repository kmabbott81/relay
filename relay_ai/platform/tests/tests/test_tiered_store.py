"""
Comprehensive tests for tiered storage system (Sprint 26).

Tests cover:
- Write/read operations across all tiers
- Tenant isolation and security
- Metadata handling
- Artifact promotion between tiers
- Age calculation
- Error cases and validation
- Path traversal prevention
- Atomic writes
"""

import time

import pytest

from relay_ai.storage.tiered_store import (
    TIER_COLD,
    TIER_HOT,
    TIER_WARM,
    ArtifactNotFoundError,
    InvalidTenantPathError,
    StorageError,
    artifact_exists,
    get_all_tier_stats,
    get_artifact_age_days,
    get_artifact_path,
    get_tier_stats,
    list_artifacts,
    promote_artifact,
    purge_artifact,
    read_artifact,
    validate_artifact_id,
    validate_tenant_id,
    validate_workflow_id,
    write_artifact,
)


class TestBasicWriteRead:
    """Tests for basic write and read operations."""

    def test_write_artifact_to_hot_tier(self, temp_tier_paths):
        """Test writing an artifact to hot tier."""
        content = b"Test content"
        metadata = {"type": "test", "version": 1}

        path = write_artifact(
            tier=TIER_HOT,
            tenant_id="tenant1",
            workflow_id="workflow1",
            artifact_id="test.txt",
            content=content,
            metadata=metadata,
        )

        assert path.exists()
        assert path.read_bytes() == content

    def test_write_artifact_to_warm_tier(self, temp_tier_paths):
        """Test writing an artifact to warm tier."""
        content = b"Warm content"

        path = write_artifact(
            tier=TIER_WARM, tenant_id="tenant1", workflow_id="workflow1", artifact_id="warm.txt", content=content
        )

        assert path.exists()
        assert TIER_WARM in str(path)

    def test_write_artifact_to_cold_tier(self, temp_tier_paths):
        """Test writing an artifact to cold tier."""
        content = b"Cold content"

        path = write_artifact(
            tier=TIER_COLD, tenant_id="tenant1", workflow_id="workflow1", artifact_id="cold.txt", content=content
        )

        assert path.exists()
        assert TIER_COLD in str(path)

    def test_read_artifact_returns_content_and_metadata(self, temp_tier_paths):
        """Test reading artifact returns both content and metadata."""
        content = b"Test content"
        metadata = {"key": "value"}

        write_artifact(
            tier=TIER_HOT,
            tenant_id="tenant1",
            workflow_id="workflow1",
            artifact_id="test.txt",
            content=content,
            metadata=metadata,
        )

        read_content, read_metadata = read_artifact(
            tier=TIER_HOT, tenant_id="tenant1", workflow_id="workflow1", artifact_id="test.txt"
        )

        assert read_content == content
        assert read_metadata["key"] == "value"
        assert "_created_at" in read_metadata
        assert "_tier" in read_metadata

    def test_read_nonexistent_artifact_raises_error(self, temp_tier_paths):
        """Test reading non-existent artifact raises ArtifactNotFoundError."""
        with pytest.raises(ArtifactNotFoundError):
            read_artifact(tier=TIER_HOT, tenant_id="tenant1", workflow_id="workflow1", artifact_id="missing.txt")

    def test_artifact_exists_returns_true_for_existing(self, temp_tier_paths):
        """Test artifact_exists returns True for existing artifacts."""
        write_artifact(
            tier=TIER_HOT, tenant_id="tenant1", workflow_id="workflow1", artifact_id="exists.txt", content=b"content"
        )

        assert artifact_exists(TIER_HOT, "tenant1", "workflow1", "exists.txt")

    def test_artifact_exists_returns_false_for_missing(self, temp_tier_paths):
        """Test artifact_exists returns False for missing artifacts."""
        assert not artifact_exists(TIER_HOT, "tenant1", "workflow1", "missing.txt")


class TestMetadataHandling:
    """Tests for metadata management."""

    def test_write_creates_metadata_file(self, temp_tier_paths):
        """Test that write creates separate metadata file."""
        write_artifact(
            tier=TIER_HOT,
            tenant_id="tenant1",
            workflow_id="workflow1",
            artifact_id="test.txt",
            content=b"content",
            metadata={"custom": "data"},
        )

        path = get_artifact_path(TIER_HOT, "tenant1", "workflow1", "test.txt")
        metadata_path = path.parent / f"{path.name}.metadata.json"

        assert metadata_path.exists()

    def test_metadata_includes_system_fields(self, temp_tier_paths):
        """Test that metadata includes system-generated fields."""
        write_artifact(
            tier=TIER_HOT, tenant_id="tenant1", workflow_id="workflow1", artifact_id="test.txt", content=b"content"
        )

        _, metadata = read_artifact(TIER_HOT, "tenant1", "workflow1", "test.txt")

        assert "_created_at" in metadata
        assert "_tier" in metadata
        assert "_tenant_id" in metadata
        assert "_workflow_id" in metadata
        assert "_artifact_id" in metadata
        assert "_size_bytes" in metadata

    def test_metadata_preserves_custom_fields(self, temp_tier_paths):
        """Test that custom metadata fields are preserved."""
        custom_metadata = {"author": "Alice", "version": "1.0.0", "tags": ["important", "test"]}

        write_artifact(
            tier=TIER_HOT,
            tenant_id="tenant1",
            workflow_id="workflow1",
            artifact_id="test.txt",
            content=b"content",
            metadata=custom_metadata,
        )

        _, metadata = read_artifact(TIER_HOT, "tenant1", "workflow1", "test.txt")

        assert metadata["author"] == "Alice"
        assert metadata["version"] == "1.0.0"
        assert metadata["tags"] == ["important", "test"]

    def test_write_without_metadata_creates_empty_metadata(self, temp_tier_paths):
        """Test writing without metadata creates empty metadata dict."""
        write_artifact(
            tier=TIER_HOT, tenant_id="tenant1", workflow_id="workflow1", artifact_id="test.txt", content=b"content"
        )

        _, metadata = read_artifact(TIER_HOT, "tenant1", "workflow1", "test.txt")

        # Should still have system fields
        assert "_created_at" in metadata
        assert "_tier" in metadata


class TestTenantIsolation:
    """Tests for tenant isolation and security."""

    def test_different_tenants_isolated(self, temp_tier_paths):
        """Test that different tenants cannot access each other's artifacts."""
        write_artifact(
            tier=TIER_HOT,
            tenant_id="tenant1",
            workflow_id="workflow1",
            artifact_id="secret.txt",
            content=b"tenant1 secret",
        )

        write_artifact(
            tier=TIER_HOT,
            tenant_id="tenant2",
            workflow_id="workflow1",
            artifact_id="secret.txt",
            content=b"tenant2 secret",
        )

        content1, _ = read_artifact(TIER_HOT, "tenant1", "workflow1", "secret.txt")
        content2, _ = read_artifact(TIER_HOT, "tenant2", "workflow1", "secret.txt")

        assert content1 == b"tenant1 secret"
        assert content2 == b"tenant2 secret"

    def test_path_traversal_in_tenant_id_blocked(self, temp_tier_paths):
        """Test that path traversal in tenant ID is blocked."""
        with pytest.raises(InvalidTenantPathError):
            write_artifact(
                tier=TIER_HOT,
                tenant_id="../../../etc",
                workflow_id="workflow1",
                artifact_id="passwd",
                content=b"hacker",
            )

    def test_path_traversal_in_workflow_id_blocked(self, temp_tier_paths):
        """Test that path traversal in workflow ID is blocked."""
        with pytest.raises(InvalidTenantPathError):
            write_artifact(
                tier=TIER_HOT, tenant_id="tenant1", workflow_id="../../../tmp", artifact_id="exploit", content=b"hacker"
            )

    def test_path_traversal_in_artifact_id_blocked(self, temp_tier_paths):
        """Test that path traversal in artifact ID is blocked."""
        with pytest.raises(InvalidTenantPathError):
            write_artifact(
                tier=TIER_HOT,
                tenant_id="tenant1",
                workflow_id="workflow1",
                artifact_id="../../secrets.txt",
                content=b"hacker",
            )

    def test_absolute_path_in_tenant_id_blocked(self, temp_tier_paths):
        """Test that absolute paths in tenant ID are blocked."""
        with pytest.raises(InvalidTenantPathError):
            write_artifact(
                tier=TIER_HOT,
                tenant_id="/etc/passwd",
                workflow_id="workflow1",
                artifact_id="test.txt",
                content=b"hacker",
            )

    def test_invalid_characters_in_tenant_id_blocked(self, temp_tier_paths):
        """Test that invalid characters in tenant ID are blocked."""
        invalid_chars = [":", "*", "?", '"', "<", ">", "|"]

        for char in invalid_chars:
            with pytest.raises(InvalidTenantPathError):
                write_artifact(
                    tier=TIER_HOT,
                    tenant_id=f"tenant{char}1",
                    workflow_id="workflow1",
                    artifact_id="test.txt",
                    content=b"content",
                )


class TestArtifactPromotion:
    """Tests for promoting artifacts between tiers."""

    def test_promote_from_hot_to_warm(self, temp_tier_paths):
        """Test promoting artifact from hot to warm tier."""
        content = b"Test content"

        write_artifact(
            tier=TIER_HOT, tenant_id="tenant1", workflow_id="workflow1", artifact_id="test.txt", content=content
        )

        success = promote_artifact(
            tenant_id="tenant1", workflow_id="workflow1", artifact_id="test.txt", from_tier=TIER_HOT, to_tier=TIER_WARM
        )

        assert success
        assert not artifact_exists(TIER_HOT, "tenant1", "workflow1", "test.txt")
        assert artifact_exists(TIER_WARM, "tenant1", "workflow1", "test.txt")

        # Verify content preserved
        read_content, _ = read_artifact(TIER_WARM, "tenant1", "workflow1", "test.txt")
        assert read_content == content

    def test_promote_from_warm_to_cold(self, temp_tier_paths):
        """Test promoting artifact from warm to cold tier."""
        write_artifact(
            tier=TIER_WARM, tenant_id="tenant1", workflow_id="workflow1", artifact_id="test.txt", content=b"content"
        )

        success = promote_artifact(
            tenant_id="tenant1", workflow_id="workflow1", artifact_id="test.txt", from_tier=TIER_WARM, to_tier=TIER_COLD
        )

        assert success
        assert not artifact_exists(TIER_WARM, "tenant1", "workflow1", "test.txt")
        assert artifact_exists(TIER_COLD, "tenant1", "workflow1", "test.txt")

    def test_promote_updates_metadata(self, temp_tier_paths):
        """Test that promotion updates metadata fields."""
        write_artifact(
            tier=TIER_HOT, tenant_id="tenant1", workflow_id="workflow1", artifact_id="test.txt", content=b"content"
        )

        promote_artifact(
            tenant_id="tenant1", workflow_id="workflow1", artifact_id="test.txt", from_tier=TIER_HOT, to_tier=TIER_WARM
        )

        _, metadata = read_artifact(TIER_WARM, "tenant1", "workflow1", "test.txt")

        assert metadata["_tier"] == TIER_WARM
        assert metadata["_promoted_from"] == TIER_HOT
        assert "_promoted_at" in metadata

    def test_promote_nonexistent_artifact_raises_error(self, temp_tier_paths):
        """Test promoting non-existent artifact raises error."""
        with pytest.raises(ArtifactNotFoundError):
            promote_artifact(
                tenant_id="tenant1",
                workflow_id="workflow1",
                artifact_id="missing.txt",
                from_tier=TIER_HOT,
                to_tier=TIER_WARM,
            )

    def test_promote_same_tier_raises_error(self, temp_tier_paths):
        """Test promoting to same tier raises error."""
        write_artifact(
            tier=TIER_HOT, tenant_id="tenant1", workflow_id="workflow1", artifact_id="test.txt", content=b"content"
        )

        with pytest.raises(StorageError):
            promote_artifact(
                tenant_id="tenant1",
                workflow_id="workflow1",
                artifact_id="test.txt",
                from_tier=TIER_HOT,
                to_tier=TIER_HOT,
            )

    def test_promote_dry_run_doesnt_move_files(self, temp_tier_paths):
        """Test dry-run promotion doesn't actually move files."""
        write_artifact(
            tier=TIER_HOT, tenant_id="tenant1", workflow_id="workflow1", artifact_id="test.txt", content=b"content"
        )

        success = promote_artifact(
            tenant_id="tenant1",
            workflow_id="workflow1",
            artifact_id="test.txt",
            from_tier=TIER_HOT,
            to_tier=TIER_WARM,
            dry_run=True,
        )

        assert success
        # File should still be in hot tier
        assert artifact_exists(TIER_HOT, "tenant1", "workflow1", "test.txt")
        assert not artifact_exists(TIER_WARM, "tenant1", "workflow1", "test.txt")

    def test_promote_cold_to_hot_restoration(self, temp_tier_paths):
        """Test promoting from cold back to hot (restoration)."""
        content = b"Important content"

        write_artifact(
            tier=TIER_COLD, tenant_id="tenant1", workflow_id="workflow1", artifact_id="test.txt", content=content
        )

        promote_artifact(
            tenant_id="tenant1", workflow_id="workflow1", artifact_id="test.txt", from_tier=TIER_COLD, to_tier=TIER_HOT
        )

        assert artifact_exists(TIER_HOT, "tenant1", "workflow1", "test.txt")
        read_content, _ = read_artifact(TIER_HOT, "tenant1", "workflow1", "test.txt")
        assert read_content == content


class TestListingArtifacts:
    """Tests for listing artifacts."""

    def test_list_artifacts_empty_tier(self, temp_tier_paths):
        """Test listing empty tier returns empty list."""
        artifacts = list_artifacts(TIER_HOT)
        assert artifacts == []

    def test_list_artifacts_single_tier(self, temp_tier_paths):
        """Test listing artifacts in a single tier."""
        write_artifact(TIER_HOT, "tenant1", "workflow1", "file1.txt", b"content1")
        write_artifact(TIER_HOT, "tenant1", "workflow1", "file2.txt", b"content2")

        artifacts = list_artifacts(TIER_HOT)

        assert len(artifacts) == 2
        artifact_ids = [a["artifact_id"] for a in artifacts]
        assert "file1.txt" in artifact_ids
        assert "file2.txt" in artifact_ids

    def test_list_artifacts_filtered_by_tenant(self, temp_tier_paths):
        """Test listing artifacts filtered by tenant."""
        write_artifact(TIER_HOT, "tenant1", "workflow1", "file1.txt", b"content1")
        write_artifact(TIER_HOT, "tenant2", "workflow1", "file2.txt", b"content2")

        artifacts = list_artifacts(TIER_HOT, tenant_id="tenant1")

        assert len(artifacts) == 1
        assert artifacts[0]["artifact_id"] == "file1.txt"
        assert artifacts[0]["tenant_id"] == "tenant1"

    def test_list_artifacts_includes_metadata(self, temp_tier_paths):
        """Test that listed artifacts include metadata."""
        write_artifact(TIER_HOT, "tenant1", "workflow1", "test.txt", b"content")

        artifacts = list_artifacts(TIER_HOT)

        assert len(artifacts) == 1
        artifact = artifacts[0]

        assert "tier" in artifact
        assert "tenant_id" in artifact
        assert "workflow_id" in artifact
        assert "artifact_id" in artifact
        assert "path" in artifact
        assert "size_bytes" in artifact
        assert "modified_at" in artifact
        assert "created_at" in artifact

    def test_list_artifacts_multiple_workflows(self, temp_tier_paths):
        """Test listing artifacts across multiple workflows."""
        write_artifact(TIER_HOT, "tenant1", "workflow1", "file1.txt", b"content1")
        write_artifact(TIER_HOT, "tenant1", "workflow2", "file2.txt", b"content2")

        artifacts = list_artifacts(TIER_HOT, tenant_id="tenant1")

        assert len(artifacts) == 2
        workflow_ids = [a["workflow_id"] for a in artifacts]
        assert "workflow1" in workflow_ids
        assert "workflow2" in workflow_ids


class TestAgeCalculation:
    """Tests for artifact age calculation."""

    def test_get_artifact_age_days_new_artifact(self, temp_tier_paths):
        """Test age calculation for newly created artifact."""
        write_artifact(TIER_HOT, "tenant1", "workflow1", "new.txt", b"content")

        age = get_artifact_age_days(TIER_HOT, "tenant1", "workflow1", "new.txt")

        assert age < 0.1  # Less than 0.1 days (few hours)

    def test_get_artifact_age_days_with_fake_clock(self, temp_tier_paths):
        """Test age calculation with fake clock."""
        write_artifact(TIER_HOT, "tenant1", "workflow1", "old.txt", b"content")

        # Simulate 10 days passing
        fake_clock = time.time() + (10 * 86400)
        age = get_artifact_age_days(TIER_HOT, "tenant1", "workflow1", "old.txt", fake_clock=fake_clock)

        assert 9.9 < age < 10.1  # ~10 days

    def test_get_artifact_age_nonexistent_raises_error(self, temp_tier_paths):
        """Test getting age of non-existent artifact raises error."""
        with pytest.raises(ArtifactNotFoundError):
            get_artifact_age_days(TIER_HOT, "tenant1", "workflow1", "missing.txt")


class TestPurgeArtifact:
    """Tests for purging artifacts."""

    def test_purge_artifact_deletes_files(self, temp_tier_paths):
        """Test purging artifact deletes content and metadata."""
        write_artifact(TIER_COLD, "tenant1", "workflow1", "old.txt", b"content")

        success = purge_artifact(TIER_COLD, "tenant1", "workflow1", "old.txt")

        assert success
        assert not artifact_exists(TIER_COLD, "tenant1", "workflow1", "old.txt")

    def test_purge_nonexistent_artifact_raises_error(self, temp_tier_paths):
        """Test purging non-existent artifact raises error."""
        with pytest.raises(ArtifactNotFoundError):
            purge_artifact(TIER_COLD, "tenant1", "workflow1", "missing.txt")

    def test_purge_dry_run_doesnt_delete(self, temp_tier_paths):
        """Test dry-run purge doesn't actually delete files."""
        write_artifact(TIER_COLD, "tenant1", "workflow1", "test.txt", b"content")

        success = purge_artifact(TIER_COLD, "tenant1", "workflow1", "test.txt", dry_run=True)

        assert success
        assert artifact_exists(TIER_COLD, "tenant1", "workflow1", "test.txt")


class TestStatistics:
    """Tests for storage statistics."""

    def test_get_tier_stats_empty(self, temp_tier_paths):
        """Test getting stats for empty tier."""
        stats = get_tier_stats(TIER_HOT)

        assert stats["tier"] == TIER_HOT
        assert stats["artifact_count"] == 0
        assert stats["total_bytes"] == 0
        assert stats["tenant_count"] == 0

    def test_get_tier_stats_with_artifacts(self, temp_tier_paths):
        """Test getting stats with artifacts present."""
        write_artifact(TIER_HOT, "tenant1", "workflow1", "file1.txt", b"a" * 100)
        write_artifact(TIER_HOT, "tenant1", "workflow1", "file2.txt", b"b" * 200)
        write_artifact(TIER_HOT, "tenant2", "workflow1", "file3.txt", b"c" * 150)

        stats = get_tier_stats(TIER_HOT)

        assert stats["artifact_count"] == 3
        assert stats["total_bytes"] == 450
        assert stats["tenant_count"] == 2
        assert set(stats["tenants"]) == {"tenant1", "tenant2"}

    def test_get_all_tier_stats(self, temp_tier_paths):
        """Test getting stats for all tiers."""
        write_artifact(TIER_HOT, "tenant1", "workflow1", "hot.txt", b"hot")
        write_artifact(TIER_WARM, "tenant1", "workflow1", "warm.txt", b"warm")
        write_artifact(TIER_COLD, "tenant1", "workflow1", "cold.txt", b"cold")

        all_stats = get_all_tier_stats()

        assert TIER_HOT in all_stats
        assert TIER_WARM in all_stats
        assert TIER_COLD in all_stats
        assert all_stats[TIER_HOT]["artifact_count"] == 1
        assert all_stats[TIER_WARM]["artifact_count"] == 1
        assert all_stats[TIER_COLD]["artifact_count"] == 1


class TestValidation:
    """Tests for input validation."""

    def test_validate_tenant_id_empty_raises_error(self):
        """Test empty tenant ID raises error."""
        with pytest.raises(InvalidTenantPathError):
            validate_tenant_id("")

    def test_validate_workflow_id_empty_raises_error(self):
        """Test empty workflow ID raises error."""
        with pytest.raises(InvalidTenantPathError):
            validate_workflow_id("")

    def test_validate_artifact_id_empty_raises_error(self):
        """Test empty artifact ID raises error."""
        with pytest.raises(InvalidTenantPathError):
            validate_artifact_id("")

    def test_invalid_tier_name_raises_error(self, temp_tier_paths):
        """Test invalid tier name raises error."""
        with pytest.raises(StorageError):
            write_artifact(
                tier="invalid_tier",
                tenant_id="tenant1",
                workflow_id="workflow1",
                artifact_id="test.txt",
                content=b"content",
            )


class TestAtomicWrites:
    """Tests for atomic write operations."""

    def test_write_uses_temp_file(self, temp_tier_paths):
        """Test that writes use temporary files for atomicity."""
        # This is more of a behavioral test - we verify the final state
        write_artifact(TIER_HOT, "tenant1", "workflow1", "test.txt", b"content")

        # Verify no temp files left behind
        path = get_artifact_path(TIER_HOT, "tenant1", "workflow1", "test.txt")
        parent_dir = path.parent

        temp_files = [f for f in parent_dir.iterdir() if f.name.startswith(".")]
        assert len(temp_files) == 0

    def test_concurrent_writes_different_artifacts(self, temp_tier_paths):
        """Test concurrent writes to different artifacts."""
        # Simulate concurrent writes
        write_artifact(TIER_HOT, "tenant1", "workflow1", "file1.txt", b"content1")
        write_artifact(TIER_HOT, "tenant1", "workflow1", "file2.txt", b"content2")

        assert artifact_exists(TIER_HOT, "tenant1", "workflow1", "file1.txt")
        assert artifact_exists(TIER_HOT, "tenant1", "workflow1", "file2.txt")
