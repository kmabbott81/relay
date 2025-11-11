#!/usr/bin/env python3
"""
Keyring CLI - Sprint 33B

Manage encryption keyring.

Exit codes:
  0 - Success
  1 - Error
"""

import argparse
import json
import sys

from relay_ai.crypto.keyring import active_key, list_keys, rotate_key


def cmd_list(args):
    """List all keys in keyring."""
    try:
        keys = list_keys()

        # Mask key material for security
        safe_keys = []
        for key in keys:
            safe_key = {
                "key_id": key["key_id"],
                "alg": key["alg"],
                "status": key["status"],
                "created_at": key["created_at"],
            }
            if "retired_at" in key:
                safe_key["retired_at"] = key["retired_at"]
            safe_keys.append(safe_key)

        result = {
            "keys": safe_keys,
            "count": len(safe_keys),
        }
        print(json.dumps(result, indent=2))
        return 0

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1


def cmd_rotate(args):
    """Rotate encryption key."""
    try:
        new_key = rotate_key()

        # Mask key material
        safe_key = {
            "key_id": new_key["key_id"],
            "alg": new_key["alg"],
            "status": new_key["status"],
            "created_at": new_key["created_at"],
        }

        result = {
            "event": "key_rotated",
            "new_key": safe_key,
        }
        print(json.dumps(result, indent=2))
        return 0

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1


def cmd_active(args):
    """Show currently active key."""
    try:
        key = active_key()

        # Mask key material
        safe_key = {
            "key_id": key["key_id"],
            "alg": key["alg"],
            "status": key["status"],
            "created_at": key["created_at"],
        }

        print(json.dumps(safe_key, indent=2))
        return 0

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Keyring management CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # list command
    subparsers.add_parser("list", help="List all keys")

    # rotate command
    subparsers.add_parser("rotate", help="Rotate encryption key")

    # active command
    subparsers.add_parser("active", help="Show active key")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "list":
        return cmd_list(args)
    elif args.command == "rotate":
        return cmd_rotate(args)
    elif args.command == "active":
        return cmd_active(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
