"""Connector health CLI for operations monitoring.

Commands:
- list: Show brief status for all enabled connectors
- drill <ID>: Show detailed status for specific connector

Exit codes:
- 0: All healthy
- 1: One or more degraded/down
- 2: RBAC denied
- 3: Not found/error
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import after path modification (ruff: E402)
from relay_ai.connectors.circuit import get_circuit_state  # noqa: E402
from relay_ai.connectors.metrics import get_metrics_path, health_status  # noqa: E402
from relay_ai.connectors.registry import list_enabled_connectors  # noqa: E402


def check_rbac() -> bool:
    """Check if user has Operator role (or higher).

    Returns:
        True if authorized, False otherwise
    """
    required_role = os.getenv("CONNECTOR_RBAC_ROLE", "Operator")
    user_role = os.getenv("USER_ROLE", "Viewer")

    # Simple role hierarchy: Admin > Deployer > Operator > Viewer
    roles = ["Admin", "Deployer", "Operator", "Viewer"]

    try:
        user_idx = roles.index(user_role)
        required_idx = roles.index(required_role)
        return user_idx <= required_idx
    except ValueError:
        return False


def list_connectors(output_json: bool = False) -> int:
    """List all enabled connectors with health status.

    Args:
        output_json: Output as JSON instead of text

    Returns:
        Exit code (0=healthy, 1=degraded/down)
    """
    enabled = list_enabled_connectors()

    if not enabled:
        if output_json:
            print(json.dumps({"connectors": [], "status": "no_connectors"}))
        else:
            print("No connectors enabled.")
        return 0

    connector_statuses = []
    any_degraded = False

    for entry in enabled:
        connector_id = entry["connector_id"]

        # Get health
        health = health_status(connector_id, window_minutes=60)
        metrics = health.get("metrics", {})

        # Get circuit state
        circuit_state = get_circuit_state(connector_id)

        status_data = {
            "connector_id": connector_id,
            "health": health["status"],
            "p95_ms": metrics.get("p95_ms", 0.0),
            "error_rate": metrics.get("error_rate", 0.0),
            "calls_60m": metrics.get("total_calls", 0),
            "circuit_state": circuit_state,
        }

        connector_statuses.append(status_data)

        if health["status"] in ("degraded", "down"):
            any_degraded = True

    if output_json:
        print(json.dumps({"connectors": connector_statuses}, indent=2))
    else:
        # Text table
        print(f"{'Connector':<25} {'Health':<12} {'P95 (ms)':<10} {'Error %':<10} {'Calls (60m)':<12} {'Circuit':<10}")
        print("-" * 90)

        for status in connector_statuses:
            health_icon = {
                "healthy": "✅",
                "degraded": "⚠️",
                "down": "🚨",
                "unknown": "❓",
            }.get(status["health"], "❓")

            circuit_icon = {
                "closed": "🟢",
                "open": "🔴",
                "half_open": "🟡",
            }.get(status["circuit_state"], "⚪")

            print(
                f"{status['connector_id']:<25} {health_icon} {status['health']:<10} "
                f"{status['p95_ms']:<10.0f} {status['error_rate']*100:<10.1f} "
                f"{status['calls_60m']:<12} {circuit_icon} {status['circuit_state']:<10}"
            )

    return 1 if any_degraded else 0


def drill_connector(connector_id: str, output_json: bool = False) -> int:
    """Show detailed status for specific connector.

    Args:
        connector_id: Connector identifier
        output_json: Output as JSON instead of text

    Returns:
        Exit code (0=healthy, 1=degraded/down, 3=not found)
    """
    # Check if connector enabled
    enabled = list_enabled_connectors()
    connector_entry = None
    for entry in enabled:
        if entry["connector_id"] == connector_id:
            connector_entry = entry
            break

    if not connector_entry:
        if output_json:
            print(json.dumps({"error": "Connector not found or not enabled"}))
        else:
            print(f"Error: Connector '{connector_id}' not found or not enabled.")
        return 3

    # Get health
    health = health_status(connector_id, window_minutes=60)
    metrics = health.get("metrics", {})

    # Get circuit state
    circuit_state = get_circuit_state(connector_id)

    # Get recent failures
    recent_failures = get_recent_failures(connector_id, limit=5)

    if output_json:
        result = {
            "connector_id": connector_id,
            "health": health["status"],
            "reason": health["reason"],
            "metrics": {
                "total_calls": metrics.get("total_calls", 0),
                "error_rate": metrics.get("error_rate", 0.0),
                "p50_ms": metrics.get("p50_ms", 0.0),
                "p95_ms": metrics.get("p95_ms", 0.0),
                "p99_ms": metrics.get("p99_ms", 0.0),
            },
            "circuit_state": circuit_state,
            "recent_failures": recent_failures,
        }
        print(json.dumps(result, indent=2))
    else:
        # Text output
        print(f"Connector: {connector_id}")
        print(f"Health: {health['status']}")
        print(f"Reason: {health['reason']}")
        print()
        print("Metrics (Last 60 Minutes):")
        print(f"  Total Calls: {metrics.get('total_calls', 0)}")
        print(f"  Error Rate: {metrics.get('error_rate', 0.0) * 100:.1f}%")
        print(f"  P50 Latency: {metrics.get('p50_ms', 0.0):.0f}ms")
        print(f"  P95 Latency: {metrics.get('p95_ms', 0.0):.0f}ms")
        print(f"  P99 Latency: {metrics.get('p99_ms', 0.0):.0f}ms")
        print()
        print(f"Circuit State: {circuit_state}")
        print()

        if recent_failures:
            print(f"Recent Failures (Last {len(recent_failures)}):")
            for failure in recent_failures:
                print(
                    f"  - {failure['timestamp'][:19]}: {failure['operation']} - {failure.get('error', 'No error message')}"
                )
        else:
            print("No recent failures.")

    return 1 if health["status"] in ("degraded", "down") else 0


def get_recent_failures(connector_id: str, limit: int = 5) -> list[dict]:
    """Get recent failures for connector.

    Args:
        connector_id: Connector identifier
        limit: Maximum number of failures to return

    Returns:
        List of recent failure entries
    """
    metrics_path = get_metrics_path()
    if not metrics_path.exists():
        return []

    failures = []

    try:
        with open(metrics_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    entry = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue

                if entry.get("connector_id") == connector_id and entry.get("status") == "error":
                    failures.append(entry)
    except OSError:
        return []

    # Return last N failures
    return failures[-limit:]


def main():
    """CLI entrypoint."""
    # Set UTF-8 encoding for Windows console
    import io

    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Connector health monitoring CLI")
    parser.add_argument("command", choices=["list", "drill"], help="Command to execute")
    parser.add_argument("connector_id", nargs="?", help="Connector ID (required for drill)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    # Check RBAC
    if not check_rbac():
        print("Error: Insufficient permissions. Operator role required.", file=sys.stderr)
        return 2

    if args.command == "list":
        return list_connectors(output_json=args.json)
    elif args.command == "drill":
        if not args.connector_id:
            print("Error: connector_id required for drill command", file=sys.stderr)
            return 3
        return drill_connector(args.connector_id, output_json=args.json)

    return 3


if __name__ == "__main__":
    sys.exit(main())
