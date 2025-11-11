#!/usr/bin/env python
"""Roles CLI - Manage user role assignments.

Sprint 51 Phase 1: Minimal CLI for role management.

Usage:
    python scripts/roles_cli.py add-role --workspace <uuid> --user <email> --role <admin|developer|viewer>
    python scripts/roles_cli.py list-roles --workspace <uuid>
"""
import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from relay_ai.db.connection import close_database, get_connection  # noqa: E402


async def add_role(workspace_id: str, user_id: str, role: str):
    """Add a role assignment for a user."""
    valid_roles = ["admin", "developer", "viewer"]
    if role not in valid_roles:
        print(f"Error: Invalid role '{role}'. Must be one of: {valid_roles}")
        return

    try:
        workspace_uuid = UUID(workspace_id)
    except ValueError:
        print(f"Error: Invalid workspace_id '{workspace_id}'. Must be a valid UUID.")
        return

    async with get_connection() as conn:
        role_id = await conn.fetchval(
            """
            INSERT INTO roles (workspace_id, user_id, role)
            VALUES ($1, $2, $3::role_enum)
            RETURNING id
            """,
            workspace_uuid,
            user_id,
            role,
        )

    print(f"✅ Role '{role}' assigned to user '{user_id}' in workspace {workspace_id}")
    print(f"   Role ID: {role_id}")


async def list_roles(workspace_id: str):
    """List all role assignments for a workspace."""
    try:
        workspace_uuid = UUID(workspace_id)
    except ValueError:
        print(f"Error: Invalid workspace_id '{workspace_id}'. Must be a valid UUID.")
        return

    async with get_connection() as conn:
        roles = await conn.fetch(
            """
            SELECT user_id, role, created_at
            FROM roles
            WHERE workspace_id = $1
            ORDER BY created_at DESC
            """,
            workspace_uuid,
        )

    if not roles:
        print(f"No roles found for workspace {workspace_id}")
        return

    print(f"\nRoles for workspace {workspace_id}:")
    print("=" * 80)
    print(f"{'User ID':<40} {'Role':<15} {'Created':<20}")
    print("=" * 80)

    for role_record in roles:
        user_id = role_record["user_id"]
        role = role_record["role"]
        created = role_record["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        print(f"{user_id:<40} {role:<15} {created:<20}")

    print("=" * 80)


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Roles CLI for Sprint 51")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # add-role command
    add_parser = subparsers.add_parser("add-role", help="Add a role assignment")
    add_parser.add_argument("--workspace", required=True, help="Workspace UUID")
    add_parser.add_argument("--user", required=True, help="User ID or email")
    add_parser.add_argument(
        "--role",
        required=True,
        choices=["admin", "developer", "viewer"],
        help="Role to assign",
    )

    # list-roles command
    list_parser = subparsers.add_parser("list-roles", help="List roles for a workspace")
    list_parser.add_argument("--workspace", required=True, help="Workspace UUID")

    args = parser.parse_args()

    try:
        if args.command == "add-role":
            await add_role(args.workspace, args.user, args.role)
        elif args.command == "list-roles":
            await list_roles(args.workspace)
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
