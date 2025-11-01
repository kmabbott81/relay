"""Tests for multi-region routing and failover logic."""

import pytest

from src.deploy.regions import (
    RegionConfigError,
    active_regions,
    get_failover_policy,
    get_primary_region,
    next_failover,
    preferred_region,
    validate_region_config,
)


def test_active_regions_parses_comma_separated_list(monkeypatch):
    """Active regions parses REGIONS env var."""
    monkeypatch.setenv("REGIONS", "us-east,us-west,eu-west")

    regions = active_regions()

    assert regions == ["us-east", "us-west", "eu-west"]


def test_active_regions_strips_whitespace(monkeypatch):
    """Active regions strips whitespace from region names."""
    monkeypatch.setenv("REGIONS", " us-east , us-west , eu-west ")

    regions = active_regions()

    assert regions == ["us-east", "us-west", "eu-west"]


def test_active_regions_raises_when_not_configured(monkeypatch):
    """Active regions raises error when REGIONS not set."""
    monkeypatch.delenv("REGIONS", raising=False)

    with pytest.raises(RegionConfigError, match="REGIONS environment variable not configured"):
        active_regions()


def test_get_primary_region_returns_configured_value(monkeypatch):
    """Get primary region returns PRIMARY_REGION value."""
    monkeypatch.setenv("REGIONS", "us-east,us-west")
    monkeypatch.setenv("PRIMARY_REGION", "us-east")

    primary = get_primary_region()

    assert primary == "us-east"


def test_get_primary_region_raises_when_not_in_regions(monkeypatch):
    """Get primary region raises error when PRIMARY_REGION not in REGIONS."""
    monkeypatch.setenv("REGIONS", "us-east,us-west")
    monkeypatch.setenv("PRIMARY_REGION", "eu-west")  # Not in REGIONS

    with pytest.raises(RegionConfigError, match="PRIMARY_REGION 'eu-west' not found in REGIONS"):
        get_primary_region()


def test_get_failover_policy_defaults_to_ordered(monkeypatch):
    """Get failover policy defaults to 'ordered'."""
    monkeypatch.delenv("FAILOVER_POLICY", raising=False)

    policy = get_failover_policy()

    assert policy == "ordered"


def test_get_failover_policy_accepts_round_robin(monkeypatch):
    """Get failover policy accepts 'round_robin'."""
    monkeypatch.setenv("FAILOVER_POLICY", "round_robin")

    policy = get_failover_policy()

    assert policy == "round_robin"


def test_get_failover_policy_rejects_invalid_values(monkeypatch):
    """Get failover policy falls back to 'ordered' for invalid values."""
    monkeypatch.setenv("FAILOVER_POLICY", "invalid")

    policy = get_failover_policy()

    assert policy == "ordered"


def test_preferred_region_uses_primary_by_default(monkeypatch):
    """Preferred region returns PRIMARY_REGION when TENANT_STICKY not 'hash'."""
    monkeypatch.setenv("REGIONS", "us-east,us-west,eu-west")
    monkeypatch.setenv("PRIMARY_REGION", "us-east")
    monkeypatch.delenv("TENANT_STICKY", raising=False)

    region = preferred_region("tenant1")

    assert region == "us-east"


def test_preferred_region_uses_hash_based_routing(monkeypatch):
    """Preferred region uses hash-based routing when TENANT_STICKY='hash'."""
    monkeypatch.setenv("REGIONS", "us-east,us-west,eu-west")
    monkeypatch.setenv("PRIMARY_REGION", "us-east")
    monkeypatch.setenv("TENANT_STICKY", "hash")

    # Same tenant always routes to same region
    region1 = preferred_region("tenant1")
    region2 = preferred_region("tenant1")
    assert region1 == region2

    # Different tenants may route to different regions
    region3 = preferred_region("tenant2")
    assert region3 in ["us-east", "us-west", "eu-west"]


def test_preferred_region_distributes_tenants_across_regions(monkeypatch):
    """Preferred region distributes different tenants across regions."""
    monkeypatch.setenv("REGIONS", "us-east,us-west,eu-west")
    monkeypatch.setenv("PRIMARY_REGION", "us-east")
    monkeypatch.setenv("TENANT_STICKY", "hash")

    # Generate regions for many tenants
    regions = [preferred_region(f"tenant{i}") for i in range(100)]

    # Should have decent distribution (not all to same region)
    unique_regions = set(regions)
    assert len(unique_regions) >= 2  # At least 2 regions used


def test_next_failover_ordered_policy(monkeypatch):
    """Next failover follows ordered list."""
    monkeypatch.setenv("REGIONS", "us-east,us-west,eu-west")
    monkeypatch.setenv("PRIMARY_REGION", "us-east")
    monkeypatch.setenv("FAILOVER_POLICY", "ordered")

    # us-east -> us-west
    next_region = next_failover("us-east")
    assert next_region == "us-west"

    # us-west -> eu-west
    next_region = next_failover("us-west")
    assert next_region == "eu-west"

    # eu-west -> us-east (wrap around)
    next_region = next_failover("eu-west")
    assert next_region == "us-east"


def test_next_failover_round_robin_policy(monkeypatch):
    """Next failover follows round-robin list."""
    monkeypatch.setenv("REGIONS", "us-east,us-west,eu-west")
    monkeypatch.setenv("PRIMARY_REGION", "us-east")
    monkeypatch.setenv("FAILOVER_POLICY", "round_robin")

    # Same behavior as ordered for round-robin
    next_region = next_failover("us-east")
    assert next_region == "us-west"


def test_next_failover_raises_when_single_region(monkeypatch):
    """Next failover raises error when only one region available."""
    monkeypatch.setenv("REGIONS", "us-east")
    monkeypatch.setenv("PRIMARY_REGION", "us-east")

    with pytest.raises(RegionConfigError, match="No failover available"):
        next_failover("us-east")


def test_next_failover_handles_unknown_current_region(monkeypatch):
    """Next failover returns primary when current region not in list."""
    monkeypatch.setenv("REGIONS", "us-east,us-west")
    monkeypatch.setenv("PRIMARY_REGION", "us-east")
    monkeypatch.setenv("FAILOVER_POLICY", "ordered")

    # Unknown region falls back to primary
    next_region = next_failover("unknown-region")
    assert next_region == "us-east"


def test_validate_region_config_succeeds_with_valid_config(monkeypatch):
    """Validate region config returns valid=True for correct setup."""
    monkeypatch.setenv("REGIONS", "us-east,us-west")
    monkeypatch.setenv("PRIMARY_REGION", "us-east")
    monkeypatch.setenv("FAILOVER_POLICY", "ordered")

    result = validate_region_config()

    assert result["valid"] is True
    assert result["regions"] == ["us-east", "us-west"]
    assert result["primary"] == "us-east"
    assert result["policy"] == "ordered"
    assert len(result["errors"]) == 0


def test_validate_region_config_reports_missing_regions(monkeypatch):
    """Validate region config reports errors for missing REGIONS."""
    monkeypatch.delenv("REGIONS", raising=False)
    monkeypatch.setenv("PRIMARY_REGION", "us-east")

    result = validate_region_config()

    assert result["valid"] is False
    assert "REGIONS environment variable not configured" in result["errors"][0]


def test_validate_region_config_reports_invalid_primary(monkeypatch):
    """Validate region config reports errors for invalid PRIMARY_REGION."""
    monkeypatch.setenv("REGIONS", "us-east,us-west")
    monkeypatch.setenv("PRIMARY_REGION", "eu-west")  # Not in REGIONS

    result = validate_region_config()

    assert result["valid"] is False
    assert any("PRIMARY_REGION" in err for err in result["errors"])
