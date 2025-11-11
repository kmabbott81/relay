"""
Connector Management CLI (Sprint 34B)

Manage connectors from command line.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from relay_ai.connectors.registry import (  # noqa: E402
    disable_connector,
    enable_connector,
    list_enabled_connectors,
    load_connector,
    register_connector,
)
from relay_ai.security.teams import get_team_role  # noqa: E402


def check_rbac(user_id: str, tenant_id: str, required_role: str = "Operator") -> bool:
    """Check if user has required role.

    Args:
        user_id: User identifier
        tenant_id: Tenant identifier
        required_role: Required role level

    Returns:
        True if authorized, False otherwise
    """
    user_role = get_team_role(user_id, tenant_id)
    if not user_role:
        return False

    role_levels = {
        "Viewer": 0,
        "Author": 1,
        "Operator": 2,
        "Auditor": 3,
        "Compliance": 4,
        "Admin": 5,
    }

    return role_levels.get(user_role, 0) >= role_levels.get(required_role, 2)


def cmd_list(args):
    """List registered connectors."""
    connectors = list_enabled_connectors()

    if args.json:
        print(json.dumps(connectors, indent=2))
        return 0

    if not connectors:
        print("No enabled connectors found")
        return 0

    print("Enabled Connectors:")
    for conn in connectors:
        print(f"  • {conn['connector_id']:20} — {conn['module']}.{conn['class_name']}")
        print(f"    Auth: {conn['auth_type']:10} Scopes: {', '.join(conn['scopes'])}")
        print(f"    Updated: {conn['updated_at']}")
    print(f"\nTotal: {len(connectors)} connectors")
    return 0


def cmd_register(args):
    """Register new connector."""
    # RBAC check
    if not check_rbac(args.user, args.tenant, "Admin"):
        print(f"❌ RBAC denied: {args.user} lacks Admin role", file=sys.stderr)
        return 2

    scopes = args.scopes.split(",") if args.scopes else ["read"]

    entry = register_connector(
        connector_id=args.id,
        module=args.module,
        class_name=args.class_name,
        enabled=True,
        auth_type=args.auth_type,
        scopes=scopes,
    )

    if args.json:
        print(json.dumps(entry, indent=2))
    else:
        print(f"✅ Registered connector: {args.id}")
        print(f"   Module: {args.module}")
        print(f"   Class: {args.class_name}")
        print(f"   Scopes: {', '.join(scopes)}")

    return 0


def cmd_enable(args):
    """Enable connector."""
    # RBAC check
    if not check_rbac(args.user, args.tenant, "Admin"):
        print(f"❌ RBAC denied: {args.user} lacks Admin role", file=sys.stderr)
        return 2

    success = enable_connector(args.id)
    if success:
        print(f"✅ Enabled connector: {args.id}")
        return 0
    else:
        print(f"❌ Connector not found: {args.id}", file=sys.stderr)
        return 1


def cmd_disable(args):
    """Disable connector."""
    # RBAC check
    if not check_rbac(args.user, args.tenant, "Admin"):
        print(f"❌ RBAC denied: {args.user} lacks Admin role", file=sys.stderr)
        return 2

    success = disable_connector(args.id)
    if success:
        print(f"✅ Disabled connector: {args.id}")
        return 0
    else:
        print(f"❌ Connector not found: {args.id}", file=sys.stderr)
        return 1


def cmd_test(args):
    """Test connector operations."""
    # RBAC check
    if not check_rbac(args.user, args.tenant, "Operator"):
        print(f"❌ RBAC denied: {args.user} lacks Operator role", file=sys.stderr)
        return 2

    # If --ingest flag is set, ingest snapshot into URG
    if hasattr(args, "ingest") and args.ingest:
        from src.connectors.ingest import ingest_connector_snapshot

        resource_type = args.resource_type or "messages"
        limit = 100  # Default ingest limit

        print(f"Ingesting {resource_type} from {args.id} into URG...")

        try:
            result = ingest_connector_snapshot(
                args.id,
                resource_type,
                tenant=args.tenant,
                user_id=args.user,
                limit=limit,
            )

            print("✅ Ingestion complete:")
            print(f"   Resources ingested: {result['count']}")
            print(f"   Errors: {result['errors']}")
            print(f"   Source: {result['source']}")
            print(f"   Resource type: {result['resource_type']}")

            if args.json:
                print(json.dumps(result, indent=2))

            return 0

        except Exception as e:
            print(f"❌ Ingestion failed: {e}", file=sys.stderr)
            return 1

    # Load connector
    connector = load_connector(args.id, args.tenant, args.user)
    if not connector:
        print(f"❌ Connector not found or disabled: {args.id}", file=sys.stderr)
        return 1

    # Connect
    result = connector.connect()
    if result.status != "success":
        print(f"❌ Connect failed: {result.message}", file=sys.stderr)
        return 1

    print(f"✅ Connected: {result.message}")

    # Execute test action
    if args.action == "list":
        result = connector.list_resources(args.resource_type or "items")
        if result.status == "success":
            print(f"✅ List: {result.message}")
            if args.json:
                print(json.dumps(result.data, indent=2))
            else:
                print(f"   Found {len(result.data or [])} resources")
        else:
            print(f"❌ List failed: {result.message}", file=sys.stderr)
            return 1

    elif args.action == "get":
        if not args.resource_id:
            print("❌ --resource-id required for get action", file=sys.stderr)
            return 1
        result = connector.get_resource(args.resource_type or "items", args.resource_id)
        if result.status == "success":
            print(f"✅ Get: {result.message}")
            if args.json:
                print(json.dumps(result.data, indent=2))
        else:
            print(f"❌ Get failed: {result.message}", file=sys.stderr)
            return 1

    elif args.action == "create":
        if not args.payload:
            print("❌ --payload required for create action", file=sys.stderr)
            return 1
        payload = json.loads(args.payload)
        result = connector.create_resource(args.resource_type or "items", payload)
        if result.status == "success":
            print(f"✅ Create: {result.message}")
            if args.json:
                print(json.dumps(result.data, indent=2))
        else:
            print(f"❌ Create failed: {result.message}", file=sys.stderr)
            return 1

    elif args.action == "delete":
        if not args.resource_id:
            print("❌ --resource-id required for delete action", file=sys.stderr)
            return 1
        result = connector.delete_resource(args.resource_type or "items", args.resource_id)
        if result.status == "success":
            print(f"✅ Delete: {result.message}")
        else:
            print(f"❌ Delete failed: {result.message}", file=sys.stderr)
            return 1

    # Disconnect
    connector.disconnect()
    return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Manage connectors")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument("--user", default="admin", help="User ID for RBAC")
    parser.add_argument("--tenant", default="default", help="Tenant ID")

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # list command
    subparsers.add_parser("list", help="List enabled connectors")

    # register command
    register_parser = subparsers.add_parser("register", help="Register new connector")
    register_parser.add_argument("--id", required=True, help="Connector ID")
    register_parser.add_argument("--module", required=True, help="Python module path")
    register_parser.add_argument("--class", dest="class_name", required=True, help="Class name")
    register_parser.add_argument("--auth-type", default="env", help="Auth type (env, oauth, api_key)")
    register_parser.add_argument("--scopes", help="Comma-separated scopes (read,write)")

    # enable command
    enable_parser = subparsers.add_parser("enable", help="Enable connector")
    enable_parser.add_argument("id", help="Connector ID")

    # disable command
    disable_parser = subparsers.add_parser("disable", help="Disable connector")
    disable_parser.add_argument("id", help="Connector ID")

    # test command
    test_parser = subparsers.add_parser("test", help="Test connector")
    test_parser.add_argument("id", help="Connector ID")
    test_parser.add_argument(
        "--action", default="list", choices=["list", "get", "create", "delete"], help="Test action"
    )
    test_parser.add_argument("--resource-type", help="Resource type")
    test_parser.add_argument("--resource-id", help="Resource ID (for get/delete)")
    test_parser.add_argument("--payload", help="JSON payload (for create)")
    test_parser.add_argument("--dry-run", action="store_true", help="Dry-run mode")
    test_parser.add_argument("--ingest", action="store_true", help="Ingest snapshot into URG index")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "list":
            return cmd_list(args)
        elif args.command == "register":
            return cmd_register(args)
        elif args.command == "enable":
            return cmd_enable(args)
        elif args.command == "disable":
            return cmd_disable(args)
        elif args.command == "test":
            return cmd_test(args)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
