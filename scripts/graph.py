"""Unified Resource Graph (URG) CLI.

Commands:
- search: Search resources across connectors
- act: Execute actions on resources
- rebuild-index: Rebuild URG index from shards
- stats: Show index statistics
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import after path setup
from relay_ai.graph.actions import RBACDenied, execute_action, list_actions  # noqa: E402
from relay_ai.graph.index import get_index  # noqa: E402
from relay_ai.graph.search import search  # noqa: E402


def cmd_search(args):
    """Search URG index."""
    tenant = args.tenant or os.getenv("GRAPH_DEFAULT_TENANT", "local-dev")

    try:
        results = search(
            args.q,
            tenant=tenant,
            type=args.type,
            source=args.source,
            limit=args.limit,
        )

        if args.json:
            print(json.dumps(results, indent=2))
        else:
            # Pretty print
            print(f"\nFound {len(results)} results:\n")
            for i, resource in enumerate(results, 1):
                print(f"{i}. [{resource.get('type')}] {resource.get('title')}")
                print(f"   ID: {resource.get('id')}")
                print(f"   Source: {resource.get('source')}")
                print(f"   Snippet: {resource.get('snippet')[:80]}...")
                print(f"   Timestamp: {resource.get('timestamp')}")
                print()

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_act(args):
    """Execute action on resource."""
    tenant = args.tenant or os.getenv("GRAPH_DEFAULT_TENANT", "local-dev")
    user_id = args.user or os.getenv("USER", "cli-user")

    # Parse payload JSON
    try:
        payload = json.loads(args.payload) if args.payload else {}
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON payload: {e}", file=sys.stderr)
        return 1

    try:
        result = execute_action(
            args.action,
            args.id,
            payload,
            user_id=user_id,
            tenant=tenant,
        )

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print("\nAction executed successfully:")
            print(f"  Action: {result.get('action')}")
            print(f"  Graph ID: {result.get('graph_id')}")
            print(f"  Status: {result.get('status')}")
            print()

        return 0

    except RBACDenied as e:
        print(f"RBAC Denied: {e}", file=sys.stderr)
        return 2

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 3

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_rebuild_index(args):
    """Rebuild URG index."""
    tenant = args.tenant

    try:
        index = get_index()
        print("Rebuilding URG index...")

        index.rebuild_index(tenant=tenant)

        stats = index.get_stats(tenant=tenant)
        print("\nIndex rebuilt successfully:")
        print(f"  Total resources: {stats['total']}")
        print(f"  By type: {stats['by_type']}")
        print(f"  By source: {stats['by_source']}")
        print()

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_stats(args):
    """Show index statistics."""
    tenant = args.tenant

    try:
        index = get_index()
        stats = index.get_stats(tenant=tenant)

        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            print("\nURG Index Statistics:")
            print(f"  Total resources: {stats['total']}")
            print("\n  By type:")
            for resource_type, count in stats["by_type"].items():
                print(f"    {resource_type}: {count}")
            print("\n  By source:")
            for source, count in stats["by_source"].items():
                print(f"    {source}: {count}")

            if tenant:
                print(f"\n  Filtered by tenant: {tenant}")
            else:
                print("\n  By tenant:")
                for tenant_id, count in stats["by_tenant"].items():
                    print(f"    {tenant_id}: {count}")
            print()

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_list_actions(args):
    """List available actions."""
    try:
        actions = list_actions(args.type)

        if args.json:
            print(json.dumps(actions, indent=2))
        else:
            print("\nAvailable actions:")
            for resource_type, action_list in actions.items():
                print(f"\n  {resource_type}:")
                for action in action_list:
                    print(f"    - {action}")
            print()

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Unified Resource Graph (URG) CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search URG index")
    search_parser.add_argument("--q", required=True, help="Search query")
    search_parser.add_argument("--type", help="Filter by resource type")
    search_parser.add_argument("--source", help="Filter by source connector")
    search_parser.add_argument("--tenant", help="Tenant ID (default: GRAPH_DEFAULT_TENANT env)")
    search_parser.add_argument("--limit", type=int, default=50, help="Max results (default: 50)")
    search_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Act command
    act_parser = subparsers.add_parser("act", help="Execute action on resource")
    act_parser.add_argument("--action", required=True, help="Action to execute")
    act_parser.add_argument("--id", required=True, help="Graph ID of resource")
    act_parser.add_argument("--payload", help="JSON payload for action")
    act_parser.add_argument("--tenant", help="Tenant ID (default: GRAPH_DEFAULT_TENANT env)")
    act_parser.add_argument("--user", help="User ID (default: USER env)")
    act_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Rebuild index command
    rebuild_parser = subparsers.add_parser("rebuild-index", help="Rebuild URG index")
    rebuild_parser.add_argument("--tenant", help="Rebuild for specific tenant only")

    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show index statistics")
    stats_parser.add_argument("--tenant", help="Filter by tenant")
    stats_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # List actions command
    list_actions_parser = subparsers.add_parser("list-actions", help="List available actions")
    list_actions_parser.add_argument("--type", help="Filter by resource type")
    list_actions_parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Route to command handler
    if args.command == "search":
        return cmd_search(args)
    elif args.command == "act":
        return cmd_act(args)
    elif args.command == "rebuild-index":
        return cmd_rebuild_index(args)
    elif args.command == "stats":
        return cmd_stats(args)
    elif args.command == "list-actions":
        return cmd_list_actions(args)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
