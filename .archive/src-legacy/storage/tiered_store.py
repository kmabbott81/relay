"""
Tiered Storage System for Sprint 26

Implements three-tier storage (hot/warm/cold) with tenant isolation,
atomic writes, metadata management, and promotion capabilities.

Architecture:
- Hot tier: artifacts/hot/{tenant_id}/{workflow_id}/{artifact_id}
- Warm tier: artifacts/warm/{tenant_id}/{workflow_id}/{artifact_id}
- Cold tier: artifacts/cold/{tenant_id}/{workflow_id}/{artifact_id}

Each artifact has:
- Content file: {artifact_id}
- Metadata file: {artifact_id}.metadata.json
"""

import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class StorageError(Exception):
    """Base exception for storage operations."""

    pass


class ArtifactNotFoundError(StorageError):
    """Raised when an artifact cannot be found."""

    pass


class InvalidTenantPathError(StorageError):
    """Raised when tenant path contains invalid characters or escape sequences."""

    pass


# Storage tier names
TIER_HOT = "hot"
TIER_WARM = "warm"
TIER_COLD = "cold"
VALID_TIERS = [TIER_HOT, TIER_WARM, TIER_COLD]


def get_base_storage_path() -> Path:
    """
    Get the base storage path from environment or use default.

    Returns:
        Path: Base storage directory
    """
    base = os.getenv("STORAGE_BASE_PATH", "artifacts")
    return Path(base).resolve()


def validate_tenant_id(tenant_id: str) -> None:
    """
    Validate tenant ID to prevent path traversal attacks.

    Args:
        tenant_id: Tenant identifier

    Raises:
        InvalidTenantPathError: If tenant ID contains invalid characters
    """
    if not tenant_id:
        raise InvalidTenantPathError("Tenant ID cannot be empty")

    # Prevent path traversal
    if ".." in tenant_id or "/" in tenant_id or "\\" in tenant_id:
        raise InvalidTenantPathError(f"Invalid tenant ID: {tenant_id}")

    # Prevent absolute paths
    if tenant_id.startswith("/") or tenant_id.startswith("\\"):
        raise InvalidTenantPathError(f"Tenant ID cannot be absolute path: {tenant_id}")

    # Check for other suspicious characters
    if any(c in tenant_id for c in [":", "*", "?", '"', "<", ">", "|"]):
        raise InvalidTenantPathError(f"Tenant ID contains invalid characters: {tenant_id}")


def validate_workflow_id(workflow_id: str) -> None:
    """
    Validate workflow ID to prevent path traversal attacks.

    Args:
        workflow_id: Workflow identifier

    Raises:
        InvalidTenantPathError: If workflow ID contains invalid characters
    """
    if not workflow_id:
        raise InvalidTenantPathError("Workflow ID cannot be empty")

    # Same validation as tenant ID
    if ".." in workflow_id or "/" in workflow_id or "\\" in workflow_id:
        raise InvalidTenantPathError(f"Invalid workflow ID: {workflow_id}")

    if workflow_id.startswith("/") or workflow_id.startswith("\\"):
        raise InvalidTenantPathError(f"Workflow ID cannot be absolute path: {workflow_id}")

    if any(c in workflow_id for c in [":", "*", "?", '"', "<", ">", "|"]):
        raise InvalidTenantPathError(f"Workflow ID contains invalid characters: {workflow_id}")


def validate_artifact_id(artifact_id: str) -> None:
    """
    Validate artifact ID to prevent path traversal attacks.

    Args:
        artifact_id: Artifact identifier

    Raises:
        InvalidTenantPathError: If artifact ID contains invalid characters
    """
    if not artifact_id:
        raise InvalidTenantPathError("Artifact ID cannot be empty")

    # Same validation as tenant ID
    if ".." in artifact_id or "/" in artifact_id or "\\" in artifact_id:
        raise InvalidTenantPathError(f"Invalid artifact ID: {artifact_id}")

    if artifact_id.startswith("/") or artifact_id.startswith("\\"):
        raise InvalidTenantPathError(f"Artifact ID cannot be absolute path: {artifact_id}")

    if any(c in artifact_id for c in [":", "*", "?", '"', "<", ">", "|"]):
        raise InvalidTenantPathError(f"Artifact ID contains invalid characters: {artifact_id}")


def validate_tier(tier: str) -> None:
    """
    Validate storage tier name.

    Args:
        tier: Tier name (hot/warm/cold)

    Raises:
        StorageError: If tier is invalid
    """
    if tier not in VALID_TIERS:
        raise StorageError(f"Invalid tier: {tier}. Must be one of {VALID_TIERS}")


def get_artifact_path(tier: str, tenant_id: str, workflow_id: str, artifact_id: str) -> Path:
    """
    Get the full path for an artifact.

    Args:
        tier: Storage tier (hot/warm/cold)
        tenant_id: Tenant identifier
        workflow_id: Workflow identifier
        artifact_id: Artifact identifier

    Returns:
        Path: Full path to artifact

    Raises:
        StorageError: If parameters are invalid
    """
    validate_tier(tier)
    validate_tenant_id(tenant_id)
    validate_workflow_id(workflow_id)
    validate_artifact_id(artifact_id)

    base = get_base_storage_path()
    return base / tier / tenant_id / workflow_id / artifact_id


def get_metadata_path(artifact_path: Path) -> Path:
    """
    Get the metadata file path for an artifact.

    Args:
        artifact_path: Path to artifact content file

    Returns:
        Path: Path to metadata file
    """
    return artifact_path.parent / f"{artifact_path.name}.metadata.json"


def write_artifact(
    tier: str,
    tenant_id: str,
    workflow_id: str,
    artifact_id: str,
    content: bytes,
    metadata: Optional[dict[str, Any]] = None,
) -> Path:
    """
    Write an artifact to storage with atomic write operation.

    Args:
        tier: Storage tier (hot/warm/cold)
        tenant_id: Tenant identifier
        workflow_id: Workflow identifier
        artifact_id: Artifact identifier
        content: Artifact content as bytes
        metadata: Optional metadata dictionary

    Returns:
        Path: Path to written artifact

    Raises:
        StorageError: If write fails
    """
    artifact_path = get_artifact_path(tier, tenant_id, workflow_id, artifact_id)
    metadata_path = get_metadata_path(artifact_path)

    # Ensure parent directory exists
    artifact_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Write content atomically using temp file + rename
        temp_content = artifact_path.parent / f".{artifact_path.name}.tmp"
        temp_content.write_bytes(content)
        temp_content.replace(artifact_path)

        # Write metadata
        if metadata is None:
            metadata = {}

        # Add system metadata
        metadata["_created_at"] = datetime.utcnow().isoformat()
        metadata["_tier"] = tier
        metadata["_tenant_id"] = tenant_id
        metadata["_workflow_id"] = workflow_id
        metadata["_artifact_id"] = artifact_id
        metadata["_size_bytes"] = len(content)

        temp_metadata = metadata_path.parent / f".{metadata_path.name}.tmp"
        temp_metadata.write_text(json.dumps(metadata, indent=2))
        temp_metadata.replace(metadata_path)

        return artifact_path

    except Exception as e:
        raise StorageError(f"Failed to write artifact {artifact_id}: {e}") from e


def read_artifact(tier: str, tenant_id: str, workflow_id: str, artifact_id: str) -> tuple[bytes, dict[str, Any]]:
    """
    Read an artifact and its metadata from storage.

    Args:
        tier: Storage tier (hot/warm/cold)
        tenant_id: Tenant identifier
        workflow_id: Workflow identifier
        artifact_id: Artifact identifier

    Returns:
        Tuple of (content bytes, metadata dict)

    Raises:
        ArtifactNotFoundError: If artifact doesn't exist
        StorageError: If read fails
    """
    artifact_path = get_artifact_path(tier, tenant_id, workflow_id, artifact_id)
    metadata_path = get_metadata_path(artifact_path)

    if not artifact_path.exists():
        raise ArtifactNotFoundError(f"Artifact not found: {tier}/{tenant_id}/{workflow_id}/{artifact_id}")

    try:
        content = artifact_path.read_bytes()

        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())
        else:
            metadata = {}

        return content, metadata

    except ArtifactNotFoundError:
        raise
    except Exception as e:
        raise StorageError(f"Failed to read artifact {artifact_id}: {e}") from e


def artifact_exists(tier: str, tenant_id: str, workflow_id: str, artifact_id: str) -> bool:
    """
    Check if an artifact exists in storage.

    Args:
        tier: Storage tier (hot/warm/cold)
        tenant_id: Tenant identifier
        workflow_id: Workflow identifier
        artifact_id: Artifact identifier

    Returns:
        bool: True if artifact exists
    """
    try:
        artifact_path = get_artifact_path(tier, tenant_id, workflow_id, artifact_id)
        return artifact_path.exists()
    except StorageError:
        return False


def promote_artifact(
    tenant_id: str, workflow_id: str, artifact_id: str, from_tier: str, to_tier: str, dry_run: bool = False
) -> bool:
    """
    Promote (or demote) an artifact from one tier to another.

    Args:
        tenant_id: Tenant identifier
        workflow_id: Workflow identifier
        artifact_id: Artifact identifier
        from_tier: Source tier
        to_tier: Destination tier
        dry_run: If True, don't actually move files

    Returns:
        bool: True if promotion succeeded

    Raises:
        ArtifactNotFoundError: If source artifact doesn't exist
        StorageError: If promotion fails
    """
    validate_tier(from_tier)
    validate_tier(to_tier)

    if from_tier == to_tier:
        raise StorageError(f"Source and destination tiers are the same: {from_tier}")

    source_path = get_artifact_path(from_tier, tenant_id, workflow_id, artifact_id)
    source_metadata_path = get_metadata_path(source_path)

    if not source_path.exists():
        raise ArtifactNotFoundError(f"Source artifact not found: {from_tier}/{tenant_id}/{workflow_id}/{artifact_id}")

    dest_path = get_artifact_path(to_tier, tenant_id, workflow_id, artifact_id)
    dest_metadata_path = get_metadata_path(dest_path)

    if dry_run:
        return True

    try:
        # Ensure destination directory exists
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy content
        shutil.copy2(source_path, dest_path)

        # Copy and update metadata
        if source_metadata_path.exists():
            metadata = json.loads(source_metadata_path.read_text())
            metadata["_tier"] = to_tier
            metadata["_promoted_from"] = from_tier
            metadata["_promoted_at"] = datetime.utcnow().isoformat()
            dest_metadata_path.write_text(json.dumps(metadata, indent=2))

        # Remove source files
        source_path.unlink()
        if source_metadata_path.exists():
            source_metadata_path.unlink()

        # Clean up empty directories
        try:
            source_path.parent.rmdir()
        except OSError:
            pass  # Directory not empty

        return True

    except Exception as e:
        raise StorageError(f"Failed to promote artifact {artifact_id}: {e}") from e


def list_artifacts(tier: str, tenant_id: Optional[str] = None) -> list[dict[str, Any]]:
    """
    List all artifacts in a tier, optionally filtered by tenant.

    Args:
        tier: Storage tier (hot/warm/cold)
        tenant_id: Optional tenant filter

    Returns:
        List of artifact info dictionaries

    Raises:
        StorageError: If listing fails
    """
    validate_tier(tier)

    base = get_base_storage_path()
    tier_path = base / tier

    if not tier_path.exists():
        return []

    artifacts = []

    try:
        # Iterate through tenant directories
        if tenant_id:
            validate_tenant_id(tenant_id)
            tenant_dirs = [tier_path / tenant_id]
        else:
            tenant_dirs = [d for d in tier_path.iterdir() if d.is_dir()]

        for tenant_dir in tenant_dirs:
            if not tenant_dir.exists():
                continue

            current_tenant_id = tenant_dir.name

            # Iterate through workflow directories
            for workflow_dir in tenant_dir.iterdir():
                if not workflow_dir.is_dir():
                    continue

                workflow_id = workflow_dir.name

                # Iterate through artifacts
                for artifact_path in workflow_dir.iterdir():
                    # Skip metadata files
                    if artifact_path.suffix == ".json" and ".metadata" in artifact_path.name:
                        continue

                    if not artifact_path.is_file():
                        continue

                    artifact_id = artifact_path.name
                    metadata_path = get_metadata_path(artifact_path)

                    stat = artifact_path.stat()

                    artifact_info = {
                        "tier": tier,
                        "tenant_id": current_tenant_id,
                        "workflow_id": workflow_id,
                        "artifact_id": artifact_id,
                        "path": str(artifact_path),
                        "size_bytes": stat.st_size,
                        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    }

                    # Add metadata if available
                    if metadata_path.exists():
                        try:
                            metadata = json.loads(metadata_path.read_text())
                            artifact_info["metadata"] = metadata
                        except Exception:
                            pass  # Skip corrupted metadata

                    artifacts.append(artifact_info)

        return artifacts

    except Exception as e:
        raise StorageError(f"Failed to list artifacts in tier {tier}: {e}") from e


def get_artifact_age_days(
    tier: str, tenant_id: str, workflow_id: str, artifact_id: str, fake_clock: Optional[float] = None
) -> float:
    """
    Get the age of an artifact in days based on modification time.

    Args:
        tier: Storage tier (hot/warm/cold)
        tenant_id: Tenant identifier
        workflow_id: Workflow identifier
        artifact_id: Artifact identifier
        fake_clock: Optional fake current time for testing (Unix timestamp)

    Returns:
        float: Age in days

    Raises:
        ArtifactNotFoundError: If artifact doesn't exist
    """
    artifact_path = get_artifact_path(tier, tenant_id, workflow_id, artifact_id)

    if not artifact_path.exists():
        raise ArtifactNotFoundError(f"Artifact not found: {tier}/{tenant_id}/{workflow_id}/{artifact_id}")

    stat = artifact_path.stat()
    mtime = stat.st_mtime

    current_time = fake_clock if fake_clock is not None else time.time()
    age_seconds = current_time - mtime
    age_days = age_seconds / 86400.0

    return age_days


def purge_artifact(tier: str, tenant_id: str, workflow_id: str, artifact_id: str, dry_run: bool = False) -> bool:
    """
    Permanently delete an artifact and its metadata.

    Args:
        tier: Storage tier (hot/warm/cold)
        tenant_id: Tenant identifier
        workflow_id: Workflow identifier
        artifact_id: Artifact identifier
        dry_run: If True, don't actually delete files

    Returns:
        bool: True if purge succeeded

    Raises:
        ArtifactNotFoundError: If artifact doesn't exist
        StorageError: If purge fails
    """
    artifact_path = get_artifact_path(tier, tenant_id, workflow_id, artifact_id)
    metadata_path = get_metadata_path(artifact_path)

    if not artifact_path.exists():
        raise ArtifactNotFoundError(f"Artifact not found: {tier}/{tenant_id}/{workflow_id}/{artifact_id}")

    if dry_run:
        return True

    try:
        # Delete content file
        artifact_path.unlink()

        # Delete metadata file if it exists
        if metadata_path.exists():
            metadata_path.unlink()

        # Try to clean up empty directories
        try:
            artifact_path.parent.rmdir()  # workflow dir
            artifact_path.parent.parent.rmdir()  # tenant dir
        except OSError:
            pass  # Directories not empty

        return True

    except Exception as e:
        raise StorageError(f"Failed to purge artifact {artifact_id}: {e}") from e


def get_tier_stats(tier: str) -> dict[str, Any]:
    """
    Get statistics for a storage tier.

    Args:
        tier: Storage tier (hot/warm/cold)

    Returns:
        Dict with stats: count, total_bytes, tenants
    """
    validate_tier(tier)

    artifacts = list_artifacts(tier)

    total_bytes = sum(a["size_bytes"] for a in artifacts)
    tenants = {a["tenant_id"] for a in artifacts}

    return {
        "tier": tier,
        "artifact_count": len(artifacts),
        "total_bytes": total_bytes,
        "tenant_count": len(tenants),
        "tenants": sorted(tenants),
    }


def get_all_tier_stats() -> dict[str, dict[str, Any]]:
    """
    Get statistics for all storage tiers.

    Returns:
        Dict mapping tier name to stats
    """
    return {tier: get_tier_stats(tier) for tier in VALID_TIERS}
