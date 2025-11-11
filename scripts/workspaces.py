"""
Workspace Management CLI (Sprint 34A)

Manage workspaces and workspace members from command line.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from relay_ai.security.workspaces import (  # noqa: E402
    get_workspace_role,
    list_workspace_members,
    upsert_workspace_member,
)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Manage workspaces and members")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # add-member command
    add_parser = subparsers.add_parser("add-member", help="Add or update workspace member")
    add_parser.add_argument("--workspace-id", required=True, help="Workspace identifier")
    add_parser.add_argument("--user", required=True, help="Username")
    add_parser.add_argument(
        "--role",
        required=True,
        choices=["Viewer", "Author", "Operator", "Auditor", "Compliance", "Admin"],
        help="Role to assign",
    )
    add_parser.add_argument("--workspace-name", help="Workspace name (for new workspaces)")
    add_parser.add_argument("--team-id", help="Parent team ID")

    # list-members command
    list_parser = subparsers.add_parser("list-members", help="List workspace members")
    list_parser.add_argument("--workspace-id", required=True, help="Workspace identifier")

    # get-role command
    role_parser = subparsers.add_parser("get-role", help="Get user's role in workspace")
    role_parser.add_argument("--workspace-id", required=True, help="Workspace identifier")
    role_parser.add_argument("--user", required=True, help="Username")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "add-member":
            workspace = upsert_workspace_member(
                args.workspace_id, args.user, args.role, args.workspace_name, args.team_id
            )
            print(f"✅ Added {args.user} to {args.workspace_id} with role {args.role}")
            print(f"   Workspace: {workspace.get('name', args.workspace_id)}")
            if workspace.get("team_id"):
                print(f"   Team: {workspace['team_id']}")
            print(f"   Total members: {len(workspace.get('members', []))}")
            return 0

        elif args.command == "list-members":
            members = list_workspace_members(args.workspace_id)
            if not members:
                print(f"No members found in workspace {args.workspace_id}")
                return 0

            print(f"Workspace {args.workspace_id} members:")
            for member in members:
                print(f"  • {member['user']:20} — {member['role']}")
            print(f"\nTotal: {len(members)} members")
            return 0

        elif args.command == "get-role":
            role = get_workspace_role(args.user, args.workspace_id)
            if role:
                print(f"{args.user} has role {role} in workspace {args.workspace_id}")
                return 0
            else:
                print(f"{args.user} is not a member of workspace {args.workspace_id}")
                return 1

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
