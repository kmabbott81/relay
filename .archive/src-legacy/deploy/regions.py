"""Multi-region configuration and routing logic.

Provides tenant-aware region selection, failover policies, and sticky routing
for active/active multi-region deployments.
"""

import hashlib
import os


class RegionConfigError(Exception):
    """Raised when region configuration is invalid."""

    pass


def active_regions() -> list[str]:
    """
    Get list of active regions from REGIONS environment variable.

    Returns:
        List of region identifiers (e.g., ['us-east', 'us-west', 'eu-west'])

    Raises:
        RegionConfigError: If REGIONS not configured
    """
    regions_str = os.getenv("REGIONS", "")
    regions = [r.strip() for r in regions_str.split(",") if r.strip()]

    if not regions:
        raise RegionConfigError("REGIONS environment variable not configured")

    return regions


def get_primary_region() -> str:
    """
    Get primary region from PRIMARY_REGION environment variable.

    Returns:
        Primary region identifier

    Raises:
        RegionConfigError: If PRIMARY_REGION not configured or not in REGIONS
    """
    primary = os.getenv("PRIMARY_REGION", "")

    if not primary:
        raise RegionConfigError("PRIMARY_REGION environment variable not configured")

    regions = active_regions()
    if primary not in regions:
        raise RegionConfigError(f"PRIMARY_REGION '{primary}' not found in REGIONS {regions}")

    return primary


def get_failover_policy() -> str:
    """
    Get failover policy from FAILOVER_POLICY environment variable.

    Returns:
        'ordered' or 'round_robin' (default: 'ordered')
    """
    policy = os.getenv("FAILOVER_POLICY", "ordered").lower()

    if policy not in ["ordered", "round_robin"]:
        policy = "ordered"

    return policy


def preferred_region(tenant_id: str) -> str:
    """
    Determine preferred region for a tenant.

    Uses TENANT_STICKY strategy:
    - 'hash': Hash-based consistent routing (tenant always routes to same region)
    - Other: Always prefer PRIMARY_REGION

    Args:
        tenant_id: Tenant identifier

    Returns:
        Preferred region identifier

    Raises:
        RegionConfigError: If region configuration invalid
    """
    sticky_strategy = os.getenv("TENANT_STICKY", "").lower()

    if sticky_strategy == "hash":
        # Hash-based sticky routing
        regions = active_regions()
        tenant_hash = int(hashlib.md5(tenant_id.encode()).hexdigest(), 16)
        region_index = tenant_hash % len(regions)
        return regions[region_index]
    else:
        # Default to primary region
        return get_primary_region()


def next_failover(current_region: str) -> str:
    """
    Determine next failover region based on FAILOVER_POLICY.

    Args:
        current_region: Currently active region

    Returns:
        Next region to failover to

    Raises:
        RegionConfigError: If no alternative regions available
    """
    regions = active_regions()
    policy = get_failover_policy()

    if len(regions) == 1:
        raise RegionConfigError(f"No failover available: only one region configured ({regions[0]})")

    if policy == "ordered":
        # Ordered failover: use next region in list, or wrap to first
        try:
            current_index = regions.index(current_region)
            next_index = (current_index + 1) % len(regions)
            return regions[next_index]
        except ValueError:
            # Current region not in list, return primary
            return get_primary_region()

    elif policy == "round_robin":
        # Round robin: use next region in list, or wrap to first
        try:
            current_index = regions.index(current_region)
            next_index = (current_index + 1) % len(regions)
            return regions[next_index]
        except ValueError:
            # Current region not in list, return first region
            return regions[0]

    else:
        # Fallback to primary
        return get_primary_region()


def validate_region_config() -> dict:
    """
    Validate current region configuration.

    Returns:
        Dictionary with validation results:
        {
            "valid": bool,
            "regions": list,
            "primary": str,
            "policy": str,
            "errors": list
        }
    """
    errors = []
    regions = []
    primary = ""
    policy = ""

    try:
        regions = active_regions()
    except RegionConfigError as e:
        errors.append(str(e))

    try:
        primary = get_primary_region()
    except RegionConfigError as e:
        errors.append(str(e))

    try:
        policy = get_failover_policy()
    except Exception as e:
        errors.append(f"Invalid failover policy: {e}")

    return {
        "valid": len(errors) == 0,
        "regions": regions,
        "primary": primary,
        "policy": policy,
        "errors": errors,
    }
