#!/usr/bin/env python3
"""
Template Authoring CLI (Sprint 32)

Manage versioned templates: register, list, show, deprecate.
"""

import argparse
import json
import sys
from pathlib import Path

# Add src to path before other imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml  # noqa: E402

from relay_ai.template_registry import deprecate, get, list_templates, register  # noqa: E402


def cmd_register(args):
    """Register a new template."""
    try:
        # Parse tags
        tags = args.tags.split(",") if args.tags else []

        # Read template YAML
        if not Path(args.file).exists():
            print(f"Error: Template file not found: {args.file}", file=sys.stderr)
            sys.exit(1)

        with open(args.file, encoding="utf-8") as f:
            template_def = yaml.safe_load(f)

        # Get workflow_ref from template or command line
        workflow_ref = template_def.get("workflow_ref", args.workflow_ref)
        if not workflow_ref:
            print("Error: workflow_ref required (in YAML or --workflow-ref)", file=sys.stderr)
            sys.exit(1)

        # Copy template file to registry
        from relay_ai.template_registry.registry import get_registry_path

        registry_dir = get_registry_path().parent
        dest_path = registry_dir / f"{args.name}_{args.version}.yaml"

        # Ensure workflow_ref in template
        template_def["workflow_ref"] = workflow_ref

        with open(dest_path, "w", encoding="utf-8") as f:
            yaml.dump(template_def, f, default_flow_style=False, sort_keys=False)

        # Copy schema if specified
        schema_ref = None
        if args.schema:
            if not Path(args.schema).exists():
                print(f"Error: Schema file not found: {args.schema}", file=sys.stderr)
                sys.exit(1)

            schema_filename = f"{args.name}_{args.version}.schema{Path(args.schema).suffix}"
            from relay_ai.templates.loader import get_schema_path

            schemas_dir = get_schema_path("dummy").parent
            schemas_dir.mkdir(parents=True, exist_ok=True)
            schema_dest = schemas_dir / schema_filename

            # Copy schema file
            import shutil

            shutil.copy(args.schema, schema_dest)
            schema_ref = schema_filename

        # Register
        record = register(
            name=args.name,
            version=args.version,
            workflow_ref=workflow_ref,
            schema_ref=schema_ref,
            tags=tags,
        )

        print(f"✓ Template registered: {record['id']}")
        print(f"  Owner: {record['owner']}")
        print(f"  Workflow: {record['workflow_ref']}")
        if schema_ref:
            print(f"  Schema: {schema_ref}")
        if tags:
            print(f"  Tags: {', '.join(tags)}")

    except PermissionError as e:
        print(f"Permission denied: {e}", file=sys.stderr)
        sys.exit(2)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_list(args):
    """List templates."""
    try:
        templates = list_templates(owner=args.owner, tag=args.tag, status=args.status)

        if not templates:
            print("No templates found.")
            return

        print(f"{'Name':<20} {'Version':<10} {'Status':<12} {'Owner':<15} Tags")
        print("=" * 80)

        for t in templates:
            tags_str = ", ".join(t.get("tags", []))
            print(f"{t['name']:<20} {t['version']:<10} {t['status']:<12} {t['owner']:<15} {tags_str}")

        print(f"\nTotal: {len(templates)} template(s)")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_show(args):
    """Show template details."""
    try:
        template = get(args.name, args.version)

        if not template:
            if args.version:
                print(f"Template {args.name}:{args.version} not found.", file=sys.stderr)
            else:
                print(f"Template {args.name} not found.", file=sys.stderr)
            sys.exit(1)

        # Pretty print
        print(json.dumps(template, indent=2))

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_deprecate(args):
    """Deprecate a template version."""
    try:
        updated = deprecate(args.name, args.version, args.reason)

        print(f"✓ Template deprecated: {updated['id']}")
        print(f"  Reason: {args.reason}")
        print(f"  Updated: {updated['updated_at']}")

    except PermissionError as e:
        print(f"Permission denied: {e}", file=sys.stderr)
        sys.exit(2)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Template Authoring CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Register command
    register_parser = subparsers.add_parser("register", help="Register a new template")
    register_parser.add_argument("--name", required=True, help="Template name")
    register_parser.add_argument("--version", required=True, help="Template version (e.g., 1.0.0)")
    register_parser.add_argument("--file", required=True, help="Template YAML file")
    register_parser.add_argument("--workflow-ref", help="Workflow function reference")
    register_parser.add_argument("--schema", help="Schema file (JSON or YAML)")
    register_parser.add_argument("--tags", help="Comma-separated tags")

    # List command
    list_parser = subparsers.add_parser("list", help="List templates")
    list_parser.add_argument("--owner", help="Filter by owner")
    list_parser.add_argument("--tag", help="Filter by tag")
    list_parser.add_argument("--status", help="Filter by status (active, deprecated)")

    # Show command
    show_parser = subparsers.add_parser("show", help="Show template details")
    show_parser.add_argument("--name", required=True, help="Template name")
    show_parser.add_argument("--version", help="Template version (defaults to latest)")

    # Deprecate command
    deprecate_parser = subparsers.add_parser("deprecate", help="Deprecate a template")
    deprecate_parser.add_argument("--name", required=True, help="Template name")
    deprecate_parser.add_argument("--version", required=True, help="Template version")
    deprecate_parser.add_argument("--reason", required=True, help="Deprecation reason")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Dispatch
    if args.command == "register":
        cmd_register(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "deprecate":
        cmd_deprecate(args)


if __name__ == "__main__":
    main()
