"""
Delegation Management CLI (Sprint 34A)

Manage time-bounded authority delegations from command line.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from relay_ai.security.delegation import (  # noqa: E402
    grant_delegation,
    list_active_delegations,
    revoke_delegation,
)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Manage delegations")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # grant command
    grant_parser = subparsers.add_parser("grant", help="Grant time-bounded delegation")
    grant_parser.add_argument("--granter", required=True, help="User granting delegation")
    grant_parser.add_argument("--grantee", required=True, help="User receiving delegation")
    grant_parser.add_argument("--scope", required=True, choices=["team", "workspace"], help="Scope of delegation")
    grant_parser.add_argument("--scope-id", required=True, help="Team or workspace identifier")
    grant_parser.add_argument(
        "--role",
        required=True,
        choices=["Viewer", "Author", "Operator", "Auditor", "Compliance", "Admin"],
        help="Role being delegated",
    )
    grant_parser.add_argument("--hours", type=int, required=True, help="Duration in hours")
    grant_parser.add_argument("--reason", required=True, help="Justification for delegation")

    # list command
    list_parser = subparsers.add_parser("list", help="List active delegations")
    list_parser.add_argument("--scope", required=True, choices=["team", "workspace"], help="Scope to query")
    list_parser.add_argument("--scope-id", required=True, help="Team or workspace identifier")

    # revoke command
    revoke_parser = subparsers.add_parser("revoke", help="Revoke a delegation")
    revoke_parser.add_argument("--delegation-id", required=True, help="Delegation identifier")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "grant":
            delegation = grant_delegation(
                args.granter, args.grantee, args.scope, args.scope_id, args.role, args.hours, args.reason
            )
            print("✅ Delegation granted:")
            print(f"   ID: {delegation['delegation_id']}")
            print(f"   Grantee: {args.grantee}")
            print(f"   Scope: {args.scope}/{args.scope_id}")
            print(f"   Role: {args.role}")
            print(f"   Duration: {args.hours} hours")
            print(f"   Expires: {delegation['expires_at']}")
            print(f"   Reason: {args.reason}")
            return 0

        elif args.command == "list":
            delegations = list_active_delegations(args.scope, args.scope_id)
            if not delegations:
                print(f"No active delegations for {args.scope}/{args.scope_id}")
                return 0

            print(f"Active delegations for {args.scope}/{args.scope_id}:")
            print()
            for d in delegations:
                expires_at = datetime.fromisoformat(d["expires_at"].rstrip("Z"))
                now = datetime.utcnow()
                hours_remaining = (expires_at - now).total_seconds() / 3600

                print(f"  ID: {d['delegation_id']}")
                print(f"    Granter: {d['granter']} → Grantee: {d['grantee']}")
                print(f"    Role: {d['role']}")
                print(f"    Expires: {d['expires_at']} ({hours_remaining:.1f}h remaining)")
                print(f"    Reason: {d['reason']}")
                print()

            print(f"Total: {len(delegations)} active delegations")
            return 0

        elif args.command == "revoke":
            success = revoke_delegation(args.delegation_id)
            if success:
                print(f"✅ Delegation {args.delegation_id} revoked")
                return 0
            else:
                print(f"❌ Delegation {args.delegation_id} not found")
                return 1

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
