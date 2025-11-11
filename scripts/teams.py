"""
Team Management CLI (Sprint 34A)

Manage teams and team members from command line.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from relay_ai.security.teams import get_team_role, list_team_members, upsert_team_member  # noqa: E402


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Manage teams and members")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # add-member command
    add_parser = subparsers.add_parser("add-member", help="Add or update team member")
    add_parser.add_argument("--team-id", required=True, help="Team identifier")
    add_parser.add_argument("--user", required=True, help="Username")
    add_parser.add_argument(
        "--role",
        required=True,
        choices=["Viewer", "Author", "Operator", "Auditor", "Compliance", "Admin"],
        help="Role to assign",
    )
    add_parser.add_argument("--team-name", help="Team name (for new teams)")

    # list-members command
    list_parser = subparsers.add_parser("list-members", help="List team members")
    list_parser.add_argument("--team-id", required=True, help="Team identifier")

    # get-role command
    role_parser = subparsers.add_parser("get-role", help="Get user's role in team")
    role_parser.add_argument("--team-id", required=True, help="Team identifier")
    role_parser.add_argument("--user", required=True, help="Username")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "add-member":
            team = upsert_team_member(args.team_id, args.user, args.role, args.team_name)
            print(f"✅ Added {args.user} to {args.team_id} with role {args.role}")
            print(f"   Team: {team.get('name', args.team_id)}")
            print(f"   Total members: {len(team.get('members', []))}")
            return 0

        elif args.command == "list-members":
            members = list_team_members(args.team_id)
            if not members:
                print(f"No members found in team {args.team_id}")
                return 0

            print(f"Team {args.team_id} members:")
            for member in members:
                print(f"  • {member['user']:20} — {member['role']}")
            print(f"\nTotal: {len(members)} members")
            return 0

        elif args.command == "get-role":
            role = get_team_role(args.user, args.team_id)
            if role:
                print(f"{args.user} has role {role} in team {args.team_id}")
                return 0
            else:
                print(f"{args.user} is not a member of team {args.team_id}")
                return 1

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
