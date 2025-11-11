#!/usr/bin/env python3
"""
Minimal DAG Runner CLI

Loads a DAG from YAML, validates, and executes (or dry-runs).

Usage:
    python scripts/run_dag_min.py --dag configs/dags/weekly_ops_chain.min.yaml
    python scripts/run_dag_min.py --dag configs/dags/weekly_ops_chain.min.yaml --dry-run
    python scripts/run_dag_min.py --dag configs/dags/weekly_ops_chain.min.yaml --tenant acme_corp
"""

import argparse
import sys
from pathlib import Path

import yaml

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from relay_ai.orchestrator.graph import DAG, Task  # noqa: E402
from relay_ai.orchestrator.runner import RunnerError, resume_dag, run_dag  # noqa: E402


def load_dag_from_yaml(path: str) -> DAG:
    """Load DAG from YAML file."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    tasks = [
        Task(
            id=t["id"],
            workflow_ref=t.get("workflow_ref", ""),
            params=t.get("params", {}),
            retries=t.get("retries", 0),
            depends_on=t.get("depends_on", []),
            type=t.get("type", "workflow"),
            prompt=t.get("prompt"),
            required_role=t.get("required_role"),
            inputs=t.get("inputs"),
        )
        for t in data["tasks"]
    ]

    return DAG(name=data["name"], tasks=tasks, tenant_id=data.get("tenant_id", "local-dev"))


def main():
    parser = argparse.ArgumentParser(
        description="Run a DAG from YAML configuration", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dag", help="Path to DAG YAML file")
    parser.add_argument("--dry-run", action="store_true", help="Print execution plan without running")
    parser.add_argument("--tenant", default=None, help="Override tenant ID")
    parser.add_argument("--resume", help="Resume a paused DAG by run ID")

    args = parser.parse_args()

    # Resume mode
    if args.resume:
        if not args.dag:
            print("Error: --dag required when using --resume")
            return 1

        try:
            dag = load_dag_from_yaml(args.dag)
        except Exception as e:
            print(f"Error loading DAG: {e}")
            return 1

        tenant = args.tenant or dag.tenant_id

        try:
            print(f"Resuming DAG run {args.resume}...")
            result = resume_dag(args.resume, tenant=tenant, dag=dag)

            print("\n" + "=" * 60)
            print("DAG RESUMED & COMPLETED")
            print("=" * 60)
            print(f"DAG Run ID: {result['dag_run_id']}")
            print(f"DAG: {result['dag_name']}")
            print(f"Status: {result['status']}")
            print(f"Tasks Succeeded: {result['tasks_succeeded']}")
            print(f"Duration: {result.get('duration_seconds', 0):.2f}s")
            print("=" * 60)

            return 0

        except RunnerError as e:
            print(f"\nError resuming DAG: {e}")
            return 1

    # Normal execution mode
    if not args.dag:
        parser.print_help()
        return 1

    # Load DAG
    try:
        dag = load_dag_from_yaml(args.dag)
    except Exception as e:
        print(f"Error loading DAG: {e}")
        return 1

    # Override tenant if specified
    if args.tenant:
        dag.tenant_id = args.tenant

    # Execute
    try:
        result = run_dag(dag, tenant=dag.tenant_id, dry_run=args.dry_run, max_retries_default=0)

        if args.dry_run:
            print(f"\nDry run complete. {result['tasks_planned']} tasks would execute.")
        elif result.get("status") == "paused":
            print("\n" + "=" * 60)
            print("DAG PAUSED AT CHECKPOINT")
            print("=" * 60)
            print(f"DAG Run ID: {result['dag_run_id']}")
            print(f"Checkpoint ID: {result['checkpoint_id']}")
            print(f"Message: {result['message']}")
            print("=" * 60)
            print("\nNext steps:")
            print("1. Review checkpoint with: python scripts/approvals.py list")
            print(f"2. Approve with: python scripts/approvals.py approve {result['checkpoint_id']}")
            print(f"3. Resume with: python scripts/run_dag_min.py --dag {args.dag} --resume {result['dag_run_id']}")
        else:
            print("\n" + "=" * 60)
            print("DAG EXECUTION COMPLETE")
            print("=" * 60)
            print(f"DAG: {result['dag_name']}")
            print(f"Tasks Succeeded: {result['tasks_succeeded']}")
            print(f"Tasks Failed: {result['tasks_failed']}")
            print(f"Duration: {result['duration_seconds']:.2f}s")
            print("=" * 60)

            # Show task outputs
            if result.get("task_outputs"):
                print("\nTask Outputs:")
                for task_id, output in result["task_outputs"].items():
                    print(f"  {task_id}: {output.get('summary', output)}")

        return 0

    except RunnerError as e:
        print(f"\nError executing DAG: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
