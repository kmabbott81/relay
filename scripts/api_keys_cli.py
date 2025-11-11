#!/usr/bin/env python
"""API Key CLI - Create and manage API keys.

Sprint 51 Phase 1: Minimal admin CLI for API key operations.

Usage:
    python scripts/api_keys_cli.py create-key --workspace <uuid> --role <admin|developer|viewer>
    python scripts/api_keys_cli.py list-keys --workspace <uuid>
"""
import argparse
import asyncio
import json
import secrets
import sys
from pathlib import Path
from uuid import UUID

import argon2

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from relay_ai.db.connection import close_database, get_connection  # noqa: E402

# Role to scopes mapping
ROLE_SCOPES = {
    "admin": ["actions:preview", "actions:execute", "audit:read"],
    "developer": ["actions:preview", "actions:execute"],
    "viewer": ["actions:preview"],
}


def generate_api_key() -> str:
    """Generate a secure API key in format: relay_sk_<16 random chars>."""
    random_part = secrets.token_urlsafe(12)  # ~16 chars base64
    return f"relay_sk_{random_part}"


def hash_key(plaintext_key: str) -> str:
    """Hash API key using Argon2."""
    ph = argon2.PasswordHasher()
    return ph.hash(plaintext_key)


async def create_key(workspace_id: str, role: str, created_by: str = "cli"):
    """Create a new API key."""
    # Validate role
    if role not in ROLE_SCOPES:
        print(f"Error: Invalid role '{role}'. Must be one of: {list(ROLE_SCOPES.keys())}")
        return

    # Validate workspace_id as UUID
    try:
        workspace_uuid = UUID(workspace_id)
    except ValueError:
        print(f"Error: Invalid workspace_id '{workspace_id}'. Must be a valid UUID.")
        return

    # Generate key
    plaintext_key = generate_api_key()
    key_hash = hash_key(plaintext_key)
    scopes = ROLE_SCOPES[role]

    # Store in database
    async with get_connection() as conn:
        key_id = await conn.fetchval(
            """
            INSERT INTO api_keys (workspace_id, key_hash, scopes, created_by)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            workspace_uuid,
            key_hash,
            json.dumps(scopes),
            created_by,
        )

    print("=" * 80)
    print("[SUCCESS] API KEY CREATED SUCCESSFULLY")
    print("=" * 80)
    print(f"Key ID:       {key_id}")
    print(f"Workspace ID: {workspace_id}")
    print(f"Role:         {role}")
    print(f"Scopes:       {', '.join(scopes)}")
    print()
    print("[WARNING] IMPORTANT: This key is shown ONLY ONCE. Store it securely!")
    print()
    print(f"API Key:      {plaintext_key}")
    print()
    print("=" * 80)
    print("Usage:")
    print(f'  curl -H "Authorization: Bearer {plaintext_key}" https://...')
    print("=" * 80)


async def list_keys(workspace_id: str):
    """List all API keys for a workspace."""
    try:
        workspace_uuid = UUID(workspace_id)
    except ValueError:
        print(f"Error: Invalid workspace_id '{workspace_id}'. Must be a valid UUID.")
        return

    async with get_connection() as conn:
        keys = await conn.fetch(
            """
            SELECT id, scopes, created_by, created_at, revoked_at
            FROM api_keys
            WHERE workspace_id = $1
            ORDER BY created_at DESC
            """,
            workspace_uuid,
        )

    if not keys:
        print(f"No API keys found for workspace {workspace_id}")
        return

    print(f"\nAPI Keys for workspace {workspace_id}:")
    print("=" * 100)
    print(f"{'ID':<38} {'Scopes':<40} {'Created':<20} {'Revoked':<10}")
    print("=" * 100)

    for key in keys:
        key_id = str(key["id"])
        scopes = ", ".join(json.loads(key["scopes"]))
        created = key["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        revoked = "Yes" if key["revoked_at"] else "No"
        print(f"{key_id:<38} {scopes:<40} {created:<20} {revoked:<10}")

    print("=" * 100)


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="API Key CLI for Sprint 51")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create-key command
    create_parser = subparsers.add_parser("create-key", help="Create a new API key")
    create_parser.add_argument("--workspace", required=True, help="Workspace UUID")
    create_parser.add_argument(
        "--role",
        required=True,
        choices=["admin", "developer", "viewer"],
        help="Role for the API key",
    )
    create_parser.add_argument("--created-by", default="cli", help="Creator identifier")

    # list-keys command
    list_parser = subparsers.add_parser("list-keys", help="List API keys for a workspace")
    list_parser.add_argument("--workspace", required=True, help="Workspace UUID")

    args = parser.parse_args()

    try:
        if args.command == "create-key":
            await create_key(args.workspace, args.role, args.created_by)
        elif args.command == "list-keys":
            await list_keys(args.workspace)
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
