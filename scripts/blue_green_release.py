"""Blue/Green release CLI tool.

Orchestrates canary deployments across multiple regions with automatic rollback
on failures.

Usage:
    python scripts/blue_green_release.py \\
        --image-blue app:v1.0 \\
        --image-green app:v2.0 \\
        --canary-seq 2,10,25,50,100 \\
        --region us-east --region us-west \\
        --abort-on-err \\
        --timeout-s 300

Environment Variables:
    DEPLOY_RBAC_ROLE: Must be 'Deployer' or 'Admin'
    HEALTH_PORT: Health check port (default: 8086)
"""

import argparse
import sys
import time
from http.client import HTTPConnection

from relay_ai.deploy.traffic_manager import DeploymentError, TrafficManager


def check_region_ready(region: str, port: int = 8086, timeout_s: int = 5) -> bool:
    """
    Check if region instance is ready via /ready endpoint.

    Args:
        region: Region endpoint (host:port or just host)
        port: Health check port (default: 8086)
        timeout_s: Timeout in seconds

    Returns:
        True if ready, False otherwise
    """
    try:
        # Parse region endpoint
        if ":" in region:
            host, port_str = region.split(":")
            port = int(port_str)
        else:
            host = region

        conn = HTTPConnection(host, port, timeout=timeout_s)
        conn.request("GET", "/ready")
        response = conn.getresponse()
        conn.close()

        return response.status == 200

    except Exception as e:
        print(f"ERROR: Region {region} readiness check failed: {e}", file=sys.stderr)
        return False


def smoke_test_regions(regions: list[str], port: int, timeout_s: int) -> bool:
    """
    Perform smoke test on all regions.

    Args:
        regions: List of region endpoints
        port: Health check port
        timeout_s: Timeout per region

    Returns:
        True if all regions ready, False otherwise
    """
    print(f"\nSmoke testing {len(regions)} regions...")

    all_ready = True
    for region in regions:
        print(f"  • Checking {region}...", end=" ")
        if check_region_ready(region, port, timeout_s):
            print("[OK] Ready")
        else:
            print("[FAIL] Not ready")
            all_ready = False

    return all_ready


def execute_canary_sequence(
    manager: TrafficManager,
    sequence: list[int],
    regions: list[str],
    port: int,
    timeout_s: int,
    abort_on_err: bool,
) -> bool:
    """
    Execute canary weight progression.

    Args:
        manager: Traffic manager
        sequence: List of canary weights (e.g., [2, 10, 25, 50, 100])
        regions: List of region endpoints
        port: Health check port
        timeout_s: Timeout per step
        abort_on_err: Whether to abort on first error

    Returns:
        True if successful, False if aborted
    """
    print(f"\nStarting canary sequence: {sequence}")

    # Start at first weight
    first_weight = sequence[0]
    manager.start_canary(first_weight)
    print(f"  • Canary started at {first_weight}%")

    # Wait for stabilization
    print(f"  • Waiting {timeout_s}s for stabilization...")
    time.sleep(timeout_s)

    # Check regions
    if not smoke_test_regions(regions, port, timeout_s):
        if abort_on_err:
            print("\nERROR: Smoke test failed at initial canary weight", file=sys.stderr)
            return False

    # Progress through remaining weights
    for weight in sequence[1:]:
        print(f"\n  • Increasing to {weight}%...")
        manager.increase_weight(weight)

        # Wait for stabilization
        print(f"  • Waiting {timeout_s}s for stabilization...")
        time.sleep(timeout_s)

        # Check regions
        if not smoke_test_regions(regions, port, timeout_s):
            if abort_on_err:
                print(f"\nERROR: Smoke test failed at {weight}% canary weight", file=sys.stderr)
                return False
            else:
                print(f"WARNING: Some regions not ready at {weight}%, continuing...")

    return True


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Blue/Green deployment orchestration tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("--image-blue", required=True, help="Blue (current) image tag")
    parser.add_argument("--image-green", required=True, help="Green (new) image tag")
    parser.add_argument(
        "--canary-seq",
        required=True,
        help="Canary weight sequence (comma-separated, e.g., '2,10,25,50,100')",
    )
    parser.add_argument(
        "--region", action="append", dest="regions", required=True, help="Region endpoint (can be repeated)"
    )
    parser.add_argument("--abort-on-err", action="store_true", help="Abort deployment on first error")
    parser.add_argument("--timeout-s", type=int, default=60, help="Timeout per canary step (seconds)")
    parser.add_argument("--health-port", type=int, default=8086, help="Health check port (default: 8086)")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (no actual deployment)")

    args = parser.parse_args()

    # Parse canary sequence
    try:
        canary_seq = [int(w.strip()) for w in args.canary_seq.split(",")]
    except ValueError:
        print(f"ERROR: Invalid canary sequence: {args.canary_seq}", file=sys.stderr)
        sys.exit(1)

    # Validate sequence
    if not all(0 <= w <= 100 for w in canary_seq):
        print(f"ERROR: Canary weights must be 0-100: {canary_seq}", file=sys.stderr)
        sys.exit(1)

    if canary_seq != sorted(canary_seq):
        print(f"ERROR: Canary sequence must be ascending: {canary_seq}", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print("Blue/Green Deployment")
    print("=" * 60)
    print(f"Blue (current):  {args.image_blue}")
    print(f"Green (new):     {args.image_green}")
    print(f"Regions:         {', '.join(args.regions)}")
    print(f"Canary sequence: {canary_seq}")
    print(f"Abort on error:  {args.abort_on_err}")
    print(f"Timeout/step:    {args.timeout_s}s")
    print("=" * 60)

    if args.dry_run:
        print("\nDRY RUN - No actual deployment")
        print("Validation passed")
        sys.exit(0)

    # Initialize traffic manager
    try:
        manager = TrafficManager()
    except PermissionError as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Provision green deployment
    print("\nProvisioning green deployment...")
    try:
        manager.provision_green(args.image_green)
        print(f"[OK] Green provisioned: {args.image_green}")
    except DeploymentError as e:
        print(f"\nERROR: Failed to provision green: {e}", file=sys.stderr)
        sys.exit(1)

    # Smoke test regions
    print("\nPerforming initial smoke test...")
    if not smoke_test_regions(args.regions, args.health_port, args.timeout_s):
        if args.abort_on_err:
            print("\nERROR: Initial smoke test failed, aborting", file=sys.stderr)
            sys.exit(1)
        else:
            print("WARNING: Some regions not ready, continuing...")

    # Execute canary sequence
    success = execute_canary_sequence(
        manager, canary_seq, args.regions, args.health_port, args.timeout_s, args.abort_on_err
    )

    if not success:
        print("\nERROR: Canary deployment failed, initiating rollback...", file=sys.stderr)
        try:
            manager.rollback_to_blue("Canary smoke test failure")
            print("[OK] Rolled back to blue")
        except DeploymentError as e:
            print(f"ERROR: Rollback failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Promote green to live
    print("\nCanary successful, promoting green to live...")
    try:
        manager.promote_green()
        print(f"[OK] Green promoted: {args.image_green} is now live")
    except DeploymentError as e:
        print(f"\nERROR: Failed to promote green: {e}", file=sys.stderr)
        sys.exit(1)

    print("\n" + "=" * 60)
    print("[OK] Deployment completed successfully")
    print("=" * 60)


if __name__ == "__main__":
    main()
