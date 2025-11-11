#!/usr/bin/env python3
"""Natural Language Command CLI.

Usage:
    python scripts/nl.py dry "command" --tenant TENANT [--json]
    python scripts/nl.py run "command" --tenant TENANT [--force] [--json]
    python scripts/nl.py resume --checkpoint-id ID --tenant TENANT [--json]

Exit codes:
    0 - Success
    1 - Error
    2 - RBAC denied
    3 - Paused for approval
"""

import argparse
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from relay_ai.nl.executor import execute_plan, resume_plan
from relay_ai.nl.planner import make_plan


def format_plan_preview(plan) -> str:
    """Format plan preview for terminal output.

    Args:
        plan: Plan object

    Returns:
        Formatted string
    """
    return plan.preview


def format_execution_result(result) -> str:
    """Format execution result for terminal output.

    Args:
        result: ExecutionResult object

    Returns:
        Formatted string
    """
    lines = []

    lines.append(f"Status: {result.status.upper()}")
    lines.append("")

    if result.status == "dry":
        lines.append("DRY RUN - Preview only")
        lines.append("")
        lines.append(result.plan.preview)

    elif result.status == "paused":
        lines.append("PAUSED FOR APPROVAL")
        lines.append("")
        lines.append(f"Checkpoint ID: {result.checkpoint_id}")
        lines.append("")
        lines.append("To resume after approval:")
        lines.append(f"  python scripts/nl.py resume --checkpoint-id {result.checkpoint_id} --tenant <TENANT>")
        lines.append("")
        lines.append("Plan preview:")
        lines.append(result.plan.preview)

    elif result.status == "success":
        lines.append("EXECUTION SUCCESSFUL")
        lines.append("")
        lines.append(f"Completed {len(result.results)} steps:")
        for res in result.results:
            lines.append(f"  {res['step'] + 1}. {res['description']} - {res['status']}")

        if result.audit_ids:
            lines.append("")
            lines.append(f"Audit IDs: {len(result.audit_ids)} events logged")

    elif result.status == "error":
        lines.append("EXECUTION FAILED")
        lines.append("")
        lines.append(f"Error: {result.error}")
        lines.append("")
        lines.append(
            f"Completed {len([r for r in result.results if r['status'] == 'success'])} of {len(result.results)} steps"
        )

        # Show failed step
        for res in result.results:
            if res["status"] == "error":
                lines.append("")
                lines.append(f"Failed step: {res['description']}")
                lines.append(f"Error: {res.get('error', 'Unknown error')}")
                break

    return "\n".join(lines)


def cmd_dry(args):
    """Execute dry command.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    try:
        # Make plan
        plan = make_plan(
            command=args.command,
            tenant=args.tenant,
            user_id=args.user_id,
        )

        # Execute dry run
        result = execute_plan(
            plan,
            tenant=args.tenant,
            user_id=args.user_id,
            dry_run=True,
        )

        # Output
        if args.json:
            output = {
                "status": result.status,
                "plan": {
                    "plan_id": plan.plan_id,
                    "verb": plan.intent.verb,
                    "risk_level": plan.risk_level,
                    "requires_approval": plan.requires_approval,
                    "steps": [
                        {
                            "action": step.action,
                            "description": step.description,
                        }
                        for step in plan.steps
                    ],
                },
            }
            print(json.dumps(output, indent=2))
        else:
            print(format_plan_preview(plan))

        return 0

    except Exception as e:
        if args.json:
            print(json.dumps({"status": "error", "error": str(e)}, indent=2))
        else:
            print(f"Error: {e}", file=sys.stderr)

        return 1


def cmd_run(args):
    """Execute run command.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    try:
        # Make plan
        plan = make_plan(
            command=args.command,
            tenant=args.tenant,
            user_id=args.user_id,
        )

        # Force execution if requested (skip approval)
        if args.force:
            plan.requires_approval = False

        # Execute plan
        result = execute_plan(
            plan,
            tenant=args.tenant,
            user_id=args.user_id,
            dry_run=False,
        )

        # Output
        if args.json:
            output = {
                "status": result.status,
                "plan_id": plan.plan_id,
                "checkpoint_id": result.checkpoint_id,
                "steps_completed": len([r for r in result.results if r.get("status") == "success"]),
                "steps_total": len(plan.steps),
                "error": result.error,
            }
            print(json.dumps(output, indent=2))
        else:
            print(format_execution_result(result))

        # Return exit code based on status
        if result.status == "success":
            return 0
        elif result.status == "paused":
            return 3  # Paused for approval
        else:
            return 1  # Error

    except Exception as e:
        error_str = str(e)

        if args.json:
            print(json.dumps({"status": "error", "error": error_str}, indent=2))
        else:
            print(f"Error: {error_str}", file=sys.stderr)

        # Check for RBAC denial
        if "RBAC" in error_str or "permission" in error_str.lower():
            return 2

        return 1


def cmd_resume(args):
    """Execute resume command.

    Args:
        args: Parsed arguments

    Returns:
        Exit code
    """
    try:
        # Resume plan
        result = resume_plan(
            checkpoint_id=args.checkpoint_id,
            tenant=args.tenant,
            user_id=args.user_id,
        )

        # Output
        if args.json:
            output = {
                "status": result.status,
                "checkpoint_id": args.checkpoint_id,
                "steps_completed": len([r for r in result.results if r.get("status") == "success"]),
                "error": result.error,
            }
            print(json.dumps(output, indent=2))
        else:
            print(format_execution_result(result))

        # Return exit code
        if result.status == "success":
            return 0
        else:
            return 1

    except Exception as e:
        error_str = str(e)

        if args.json:
            print(json.dumps({"status": "error", "error": error_str}, indent=2))
        else:
            print(f"Error: {error_str}", file=sys.stderr)

        return 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Natural Language Command CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview command without executing
  python scripts/nl.py dry "email the Q4 budget to alice@example.com" --tenant acme

  # Execute command
  python scripts/nl.py run "forward latest contract to Bob" --tenant acme

  # Execute with approval bypass (use with caution)
  python scripts/nl.py run "delete old messages" --tenant acme --force

  # Resume after approval
  python scripts/nl.py resume --checkpoint-id nlp-approval-abc123 --tenant acme

Exit codes:
  0 - Success
  1 - Error
  2 - RBAC denied
  3 - Paused for approval
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Dry command
    dry_parser = subparsers.add_parser("dry", help="Preview command without executing")
    dry_parser.add_argument("command", help="Natural language command")
    dry_parser.add_argument("--tenant", required=True, help="Tenant ID")
    dry_parser.add_argument("--user-id", default="cli-user", help="User ID (default: cli-user)")
    dry_parser.add_argument("--json", action="store_true", help="Output JSON format")

    # Run command
    run_parser = subparsers.add_parser("run", help="Execute command")
    run_parser.add_argument("command", help="Natural language command")
    run_parser.add_argument("--tenant", required=True, help="Tenant ID")
    run_parser.add_argument("--user-id", default="cli-user", help="User ID (default: cli-user)")
    run_parser.add_argument("--force", action="store_true", help="Skip approval (use with caution)")
    run_parser.add_argument("--json", action="store_true", help="Output JSON format")

    # Resume command
    resume_parser = subparsers.add_parser("resume", help="Resume after approval")
    resume_parser.add_argument("--checkpoint-id", required=True, help="Checkpoint ID")
    resume_parser.add_argument("--tenant", required=True, help="Tenant ID")
    resume_parser.add_argument("--user-id", default="cli-user", help="User ID (default: cli-user)")
    resume_parser.add_argument("--json", action="store_true", help="Output JSON format")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Route to command handler
    if args.command == "dry":
        return cmd_dry(args)
    elif args.command == "run":
        return cmd_run(args)
    elif args.command == "resume":
        return cmd_resume(args)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
