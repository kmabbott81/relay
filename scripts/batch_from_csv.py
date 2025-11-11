#!/usr/bin/env python3
"""CLI tool for batch template processing from CSV files."""

import argparse
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from relay_ai.templates import (
    estimate_batch_cost,
    list_templates,
    load_csv_for_batch,
    process_batch_dry_run,
    render_template,
)


def main():
    parser = argparse.ArgumentParser(description="Batch process templates from CSV file")
    parser.add_argument("template_key", help="Template key (filename without .yaml)")
    parser.add_argument("csv_path", help="Path to CSV file with template inputs")
    parser.add_argument("--dry-run", action="store_true", help="Show cost projection without processing")
    parser.add_argument("--budget-usd", type=float, help="Maximum USD budget for batch")
    parser.add_argument("--budget-tokens", type=int, help="Maximum token budget for batch")
    parser.add_argument("--output-dir", default="runs/ui/templates/batch", help="Output directory for artifacts")

    args = parser.parse_args()

    # Load templates
    templates = list_templates()
    template = None

    for t in templates:
        if t.key == args.template_key:
            template = t
            break

    if not template:
        print(f"Error: Template '{args.template_key}' not found", file=sys.stderr)
        print(f"Available templates: {', '.join(t.key for t in templates)}", file=sys.stderr)
        sys.exit(1)

    print(f"Template: {template.name} v{template.version}")
    print(f"CSV: {args.csv_path}")
    print()

    # Load and validate CSV
    print("Loading CSV...")
    rows, errors = load_csv_for_batch(args.csv_path, template)

    if errors:
        print(f"Validation errors ({len(errors)}):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        if not rows:
            sys.exit(1)
        print()

    print(f"Loaded {len(rows)} valid rows")
    print()

    # Estimate costs
    print("Estimating costs...")
    batch_est = estimate_batch_cost(template, rows)

    print(f"Total rows: {batch_est['num_rows']}")
    print(f"Estimated cost: ${batch_est['total_cost_usd']:.4f}")
    print(f"Estimated tokens: {batch_est['total_tokens']:,}")
    print()

    # Check budget
    if args.budget_usd or args.budget_tokens:
        print("Checking budget...")
        dry_run_result = process_batch_dry_run(template, rows, args.budget_usd, args.budget_tokens)

        if dry_run_result["warnings"]:
            for warning in dry_run_result["warnings"]:
                print(f"⚠️  WARNING: {warning}")

        if dry_run_result["errors"]:
            for error in dry_run_result["errors"]:
                print(f"❌ ERROR: {error}", file=sys.stderr)
            print("\nBatch processing blocked by budget constraints", file=sys.stderr)
            sys.exit(1)

        if dry_run_result["within_budget"]:
            print("✅ Within budget")
        print()

    # Dry run mode - exit without processing
    if args.dry_run:
        print("Dry run complete. No artifacts created.")
        sys.exit(0)

    # Process batch
    print("Processing batch...")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    import time

    batch_id = int(time.time())
    batch_dir = output_dir / str(batch_id)
    batch_dir.mkdir(parents=True, exist_ok=True)

    successful = 0
    failed = 0

    for i, row in enumerate(rows):
        try:
            # Render template
            rendered = render_template(template, row)

            # Create preview artifact (no DJP execution in CLI)
            artifact = {
                "template": {
                    "name": template.name,
                    "version": template.version,
                    "key": template.key,
                    "context": template.context,
                },
                "inputs": row,
                "provenance": {
                    "template_body": rendered,
                    "resolved_inputs": row,
                    "timestamp": int(time.time()),
                    "batch_id": batch_id,
                    "batch_index": i,
                },
                "rendered_output": rendered,
            }

            # Save artifact
            artifact_file = batch_dir / f"{batch_id}-{template.key}-row{i:03d}.json"
            artifact_file.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

            successful += 1
            print(f"  [{i+1}/{len(rows)}] ✅ {artifact_file.name}")

        except Exception as e:
            failed += 1
            print(f"  [{i+1}/{len(rows)}] ❌ Error: {e}", file=sys.stderr)

    print()
    print(f"Batch complete: {successful} successful, {failed} failed")
    print(f"Artifacts saved to: {batch_dir}")


if __name__ == "__main__":
    main()
