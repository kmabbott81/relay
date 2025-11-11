#!/usr/bin/env python3
"""
Classification CLI - Sprint 33B

Manage classification labels for artifacts.

Exit codes:
  0 - Success
  1 - Error
"""

import argparse
import json
import sys
from pathlib import Path

from relay_ai.classify.labels import effective_label
from relay_ai.storage.secure_io import get_artifact_metadata


def cmd_set_label(args):
    """Set classification label for an artifact."""
    try:
        artifact_path = Path(args.path)
        label = effective_label(args.label)

        # Read existing metadata or create new
        sidecar_path = artifact_path.with_suffix(artifact_path.suffix + ".json")

        if sidecar_path.exists():
            metadata = json.loads(sidecar_path.read_text(encoding="utf-8"))
        else:
            metadata = {}

        # Update label
        metadata["label"] = label

        # Write back
        sidecar_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        result = {
            "artifact": str(artifact_path),
            "label": label,
            "sidecar": str(sidecar_path),
        }
        print(json.dumps(result, indent=2))
        return 0

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1


def cmd_show(args):
    """Show classification label for an artifact."""
    try:
        artifact_path = Path(args.path)
        metadata = get_artifact_metadata(artifact_path)

        if not metadata:
            result = {
                "artifact": str(artifact_path),
                "label": None,
                "message": "No metadata sidecar found",
            }
        else:
            result = {
                "artifact": str(artifact_path),
                "label": metadata.get("label"),
                "tenant": metadata.get("tenant"),
                "encrypted": metadata.get("encrypted", False),
                "created_at": metadata.get("created_at"),
            }

        print(json.dumps(result, indent=2))
        return 0

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Classification management CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # set-label command
    set_parser = subparsers.add_parser("set-label", help="Set classification label for artifact")
    set_parser.add_argument("--path", required=True, help="Path to artifact")
    set_parser.add_argument("--label", required=True, help="Classification label")

    # show command
    show_parser = subparsers.add_parser("show", help="Show artifact metadata")
    show_parser.add_argument("--path", required=True, help="Path to artifact")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "set-label":
        return cmd_set_label(args)
    elif args.command == "show":
        return cmd_show(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
