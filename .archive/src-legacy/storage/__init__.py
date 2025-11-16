"""
Storage module for Sprint 26.

Provides three-tier storage system with automated lifecycle management.
"""

from .lifecycle import (
    get_last_lifecycle_job,
    get_recent_lifecycle_events,
    get_retention_days,
    log_lifecycle_event,
    promote_expired_to_cold,
    promote_expired_to_warm,
    purge_expired_from_cold,
    restore_artifact,
    run_lifecycle_job,
)
from .tiered_store import (
    TIER_COLD,
    TIER_HOT,
    TIER_WARM,
    ArtifactNotFoundError,
    InvalidTenantPathError,
    StorageError,
    artifact_exists,
    get_all_tier_stats,
    get_artifact_age_days,
    get_tier_stats,
    list_artifacts,
    promote_artifact,
    purge_artifact,
    read_artifact,
    write_artifact,
)

__all__ = [
    # Tier constants
    "TIER_HOT",
    "TIER_WARM",
    "TIER_COLD",
    # Storage operations
    "write_artifact",
    "read_artifact",
    "artifact_exists",
    "promote_artifact",
    "list_artifacts",
    "get_artifact_age_days",
    "purge_artifact",
    "get_tier_stats",
    "get_all_tier_stats",
    # Lifecycle operations
    "get_retention_days",
    "run_lifecycle_job",
    "promote_expired_to_warm",
    "promote_expired_to_cold",
    "purge_expired_from_cold",
    "restore_artifact",
    "log_lifecycle_event",
    "get_recent_lifecycle_events",
    "get_last_lifecycle_job",
    # Exceptions
    "ArtifactNotFoundError",
    "StorageError",
    "InvalidTenantPathError",
]
