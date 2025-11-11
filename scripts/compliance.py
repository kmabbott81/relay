#!/usr/bin/env python3
"""
Compliance CLI - Sprint 33A + 33B

Manage data export, deletion, legal holds, and retention enforcement.

Sprint 33B: Added keyring management commands.

Exit codes:
  0 - Success
  2 - RBAC denied
  3 - Legal hold prevents operation
  1 - Other error
"""

import argparse
import json
import sys
from pathlib import Path

# Add src to path before other imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from relay_ai.compliance import (  # noqa: E402
    apply_legal_hold,
    current_holds,
    delete_tenant,
    enforce_retention,
    export_tenant,
    release_legal_hold,
)
from relay_ai.crypto.keyring import list_keys, rotate_key  # noqa: E402


def cmd_export(args):
    """Export tenant data."""
    try:
        out_dir = Path(args.out)
        result = export_tenant(args.tenant, out_dir)
        print(json.dumps(result, indent=2))
        return 0
    except PermissionError as e:
        print(json.dumps({"error": str(e), "code": "RBAC_DENIED"}), file=sys.stderr)
        return 2
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1


def cmd_delete(args):
    """Delete tenant data."""
    try:
        result = delete_tenant(args.tenant, dry_run=args.dry_run, respect_legal_hold=True)
        print(json.dumps(result, indent=2))
        return 0
    except PermissionError as e:
        print(json.dumps({"error": str(e), "code": "RBAC_DENIED"}), file=sys.stderr)
        return 2
    except ValueError as e:
        if "legal hold" in str(e).lower():
            print(json.dumps({"error": str(e), "code": "LEGAL_HOLD"}), file=sys.stderr)
            return 3
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1


def cmd_hold(args):
    """Apply legal hold to tenant."""
    try:
        result = apply_legal_hold(args.tenant, args.reason)
        print(json.dumps(result, indent=2))
        return 0
    except PermissionError as e:
        print(json.dumps({"error": str(e), "code": "RBAC_DENIED"}), file=sys.stderr)
        return 2
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1


def cmd_release(args):
    """Release legal hold from tenant."""
    try:
        result = release_legal_hold(args.tenant)
        print(json.dumps(result, indent=2))
        return 0
    except PermissionError as e:
        print(json.dumps({"error": str(e), "code": "RBAC_DENIED"}), file=sys.stderr)
        return 2
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1


def cmd_holds_list(args):
    """List all active holds."""
    try:
        holds = current_holds()
        print(json.dumps({"holds": holds, "count": len(holds)}, indent=2))
        return 0
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1


def cmd_retention(args):
    """Enforce retention policies."""
    try:
        result = enforce_retention()
        print(json.dumps(result, indent=2))
        return 0
    except PermissionError as e:
        print(json.dumps({"error": str(e), "code": "RBAC_DENIED"}), file=sys.stderr)
        return 2
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1


def cmd_list_keys(args):
    """List encryption keys (Sprint 33B)."""
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

        result = {"keys": safe_keys, "count": len(safe_keys)}
        print(json.dumps(result, indent=2))
        return 0

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1


def cmd_rotate_key(args):
    """Rotate encryption key (Sprint 33B)."""
    try:
        new_key = rotate_key()

        # Mask key material
        safe_key = {
            "key_id": new_key["key_id"],
            "alg": new_key["alg"],
            "status": new_key["status"],
            "created_at": new_key["created_at"],
        }

        result = {"event": "key_rotated", "new_key": safe_key}
        print(json.dumps(result, indent=2))
        return 0

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Compliance CLI - data export, deletion, legal holds")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Export command
    export_parser = subparsers.add_parser("export", help="Export tenant data")
    export_parser.add_argument("--tenant", required=True, help="Tenant ID")
    export_parser.add_argument("--out", required=True, help="Output directory")

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete tenant data")
    delete_parser.add_argument("--tenant", required=True, help="Tenant ID")
    delete_parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")

    # Hold command
    hold_parser = subparsers.add_parser("hold", help="Apply legal hold")
    hold_parser.add_argument("--tenant", required=True, help="Tenant ID")
    hold_parser.add_argument("--reason", required=True, help="Reason for hold")

    # Release command
    release_parser = subparsers.add_parser("release", help="Release legal hold")
    release_parser.add_argument("--tenant", required=True, help="Tenant ID")

    # Holds list command
    holds_parser = subparsers.add_parser("holds", help="List active holds")
    holds_parser.add_argument("--list", action="store_true", help="List all active holds")

    # Retention command
    subparsers.add_parser("retention", help="Enforce retention policies")

    # Keyring commands (Sprint 33B)
    subparsers.add_parser("list-keys", help="List encryption keys")
    subparsers.add_parser("rotate-key", help="Rotate encryption key")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Route to command handler
    handlers = {
        "export": cmd_export,
        "delete": cmd_delete,
        "hold": cmd_hold,
        "release": cmd_release,
        "holds": cmd_holds_list,
        "retention": cmd_retention,
        "list-keys": cmd_list_keys,
        "rotate-key": cmd_rotate_key,
    }

    handler = handlers.get(args.command)
    if handler:
        return handler(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
