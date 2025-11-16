"""CLI interface for Debate → Judge → Publish workflow."""

import argparse
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

from .artifacts import create_run_artifact, estimate_token_costs, save_run_artifact
from .config import ALLOWED_PUBLISH_MODELS, has_required_keys, load_policy
from .corpus import get_corpus_stats, load_corpus
from .costs import check_budget_limits, format_cost_projection, project_workflow_cost
from .debate import run_debate
from .judge import judge_drafts
from .metrics import export_metrics, load_runs
from .publish import format_publish_metadata, get_publish_status_message, select_publish_text
from .schemas import Draft, Judgment


def print_cost_footer(artifact: dict, quiet: bool = False) -> None:
    """Print cost and token usage footer to stdout."""
    if quiet:
        return

    provenance = artifact.get("provenance", {})
    model_usage = provenance.get("model_usage", {})
    estimated_costs = provenance.get("estimated_costs", {})

    if not model_usage:
        # Create mock usage data for demo purposes
        # In real usage, this would come from actual API calls
        model_usage = {
            "openai/gpt-4o": {"tokens_in": 150, "tokens_out": 80},
            "openai/gpt-4o-mini": {"tokens_in": 100, "tokens_out": 50},
        }
        estimated_costs = estimate_token_costs(model_usage)

    total_tokens_in = sum(usage.get("tokens_in", 0) for usage in model_usage.values())
    total_tokens_out = sum(usage.get("tokens_out", 0) for usage in model_usage.values())
    total_tokens = total_tokens_in + total_tokens_out
    total_cost = sum(estimated_costs.values())

    # Build cost summary
    cost_parts = []
    for provider, usage in model_usage.items():
        tokens_in = usage.get("tokens_in", 0)
        tokens_out = usage.get("tokens_out", 0)
        cost = estimated_costs.get(provider, 0.0)
        cost_parts.append(f"{provider} in={tokens_in} out={tokens_out} ${cost:.4f}")

    cost_line = " | ".join(cost_parts)
    total_line = f"Total ${total_cost:.4f} (tokens={total_tokens})"

    print(f"\nCosts: {cost_line} | {total_line}")


def list_presets() -> None:
    """List all available preset configurations."""
    presets_dir = Path("presets/cli")

    if not presets_dir.exists():
        print("No presets directory found")
        return

    preset_files = list(presets_dir.glob("*.json"))

    if not preset_files:
        print("No preset configurations found")
        return

    print("Available Preset Configurations:")
    print("=" * 50)

    for preset_file in sorted(preset_files):
        preset_name = preset_file.stem
        try:
            with open(preset_file, encoding="utf-8") as f:
                preset_data = json.load(f)

            description = preset_data.get("description", "No description available")
            args = preset_data.get("args", {})

            print(f"\n{preset_name}:")
            print(f"  Description: {description}")
            print("  Configuration:")
            for key, value in args.items():
                print(f"    {key}: {value}")

        except Exception as e:
            print(f"\n{preset_name}: [ERROR] {e}")

    print('\nUsage: python -m src.run_workflow --preset <name> --task "Your task"')


def load_preset(preset_name: str) -> dict:
    """
    Load a CLI preset configuration.

    Args:
        preset_name: Name of the preset (e.g., 'quick', 'thorough')

    Returns:
        Dictionary of preset arguments

    Raises:
        FileNotFoundError: If preset file doesn't exist
        ValueError: If preset file is invalid JSON
    """
    preset_path = Path(f"presets/cli/{preset_name}.json")

    if not preset_path.exists():
        available_presets = list(Path("presets/cli").glob("*.json")) if Path("presets/cli").exists() else []
        preset_names = [p.stem for p in available_presets]
        raise FileNotFoundError(f"Preset '{preset_name}' not found. Available presets: {', '.join(preset_names)}")

    try:
        with open(preset_path, encoding="utf-8") as f:
            preset_data = json.load(f)

        if "args" not in preset_data:
            raise ValueError(f"Preset '{preset_name}' missing 'args' section")

        return preset_data["args"]
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in preset '{preset_name}': {e}")


def write_run_log(
    task: str,
    drafts: list[Draft],
    judgment: Judgment,
    status: str,
    provider: str,
    text: str,
    trace_name: str,
    allowed_models: list[str] = None,
) -> str:
    """Write detailed log of the workflow run."""

    timestamp = datetime.now().strftime("%Y.%m.%d-%H%M")
    log_filename = f"{timestamp}-DEBATE-JUDGE-RUN.md"
    log_path = Path(log_filename)

    log_content = f"""# Debate → Judge → Publish Run Log

**Timestamp:** {datetime.now().isoformat()}
**Trace Name:** {trace_name}
**Task:** {task}

## Summary

{get_publish_status_message(status, provider)}

{format_publish_metadata(status, provider, judgment, drafts)}

## Drafts and Scores

| Provider | Score | Answer Preview | Evidence Count |
|----------|-------|----------------|----------------|
"""

    # Add table rows for scored drafts
    for draft in judgment.ranked:
        preview = draft.answer[:100].replace("\n", " ") + "..." if len(draft.answer) > 100 else draft.answer
        evidence_count = len(draft.evidence)
        log_content += f"| {draft.provider} | {draft.score:.1f}/10 | {preview} | {evidence_count} |\n"

    log_content += """
## Judge Reasoning

"""

    # Add detailed judge reasoning
    for draft in judgment.ranked:
        log_content += f"""
### {draft.provider} (Score: {draft.score}/10)
**Reasoning:** {draft.reasons}

**Full Answer:**
{draft.answer}

**Evidence:**
"""
        for i, evidence in enumerate(draft.evidence, 1):
            log_content += f"{i}. {evidence}\n"

        if draft.safety_flags:
            log_content += f"\n**Safety Flags:** {', '.join(draft.safety_flags)}\n"

        log_content += "\n---\n"

    # Add published content if available
    if status == "published" and text:
        log_content += f"""
## Published Content

**Provider:** {provider}
**Status:** PUBLISHED (verbatim)

{text}
"""
    elif status == "advisory_only" and text:
        log_content += f"""
## Advisory Content

**Provider:** {provider}
**Status:** ADVISORY ONLY (not from allowed provider list)

{text}
"""

    log_content += f"""
## Technical Details

**Allowed Publish Models:** {', '.join(allowed_models or ALLOWED_PUBLISH_MODELS)}
**Total Processing Time:** [Not tracked in this version]
**API Providers Used:** {', '.join(set(draft.provider for draft in drafts))}
"""

    # Write log file
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(log_content)

    return str(log_path)


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Debate-Judge-Publish workflow using OpenAI Agents SDK")
    parser.add_argument("--task", help="Task for agents to solve")
    parser.add_argument(
        "--max_tokens", type=int, default=1200, help="Maximum tokens per agent response (default: 1200)"
    )
    parser.add_argument("--temperature", type=float, default=0.3, help="Temperature for agent responses (default: 0.3)")
    parser.add_argument(
        "--trace_name", default="debate-judge", help="Name for tracing this run (default: debate-judge)"
    )
    parser.add_argument(
        "--require_citations", type=int, default=0, help="Minimum number of citations required in evidence (default: 0)"
    )
    parser.add_argument(
        "--policy", default="openai_only", help="Policy name or path for allowed publish models (default: openai_only)"
    )
    parser.add_argument("--fastpath", action="store_true", help="Enable fast-path mode (OpenAI models only)")
    parser.add_argument("--max_debaters", type=int, help="Maximum number of debaters to use")
    parser.add_argument("--timeout_s", type=int, help="Timeout in seconds for debate stage")
    parser.add_argument("--margin_threshold", type=int, help="Score margin threshold to skip second pass in judging")
    parser.add_argument("--seed", type=int, help="Random seed for deterministic results")
    parser.add_argument("--quiet", action="store_true", help="Suppress cost and summary output")
    parser.add_argument("--preset", help="Load CLI preset configuration (quick, thorough, research, deterministic)")
    parser.add_argument("--list-presets", action="store_true", help="List available preset configurations and exit")
    parser.add_argument("--budget_usd", type=float, help="Budget limit in USD (soft warn at 90%%, hard stop at 100%%)")
    parser.add_argument(
        "--budget_tokens", type=int, help="Budget limit in tokens (soft warn at 90%%, hard stop at 100%%)"
    )
    parser.add_argument(
        "--max_cost_usd", type=float, help="Maximum cost limit that aborts mid-run if projection exceeded"
    )
    parser.add_argument("--metrics", help="Export metrics to CSV file after completion (e.g., metrics.csv)")
    parser.add_argument(
        "--grounded_corpus", help="Path to corpus directory for grounded mode (contains .txt/.md/.pdf files)"
    )
    parser.add_argument(
        "--grounded_required",
        type=int,
        default=0,
        help="Minimum number of corpus citations required (default: 0, disabled)",
    )
    parser.add_argument(
        "--redact",
        choices=["on", "off"],
        default="on",
        help="Enable/disable redaction of sensitive information (default: on)",
    )
    parser.add_argument("--redaction_rules", help="Path to custom redaction rules JSON file")

    args = parser.parse_args()

    # Handle --list-presets flag
    if args.list_presets:
        list_presets()
        return 0

    # Validate required arguments for normal operation
    if not args.task:
        print("ERROR: --task is required")
        parser.print_help()
        return 1

    # Apply preset configuration if specified
    if args.preset:
        try:
            preset_args = load_preset(args.preset)
            print(f"Loading preset: {args.preset}")

            # Apply preset values only if the argument wasn't explicitly set by user
            for key, value in preset_args.items():
                if hasattr(args, key) and getattr(args, key) == parser.get_default(key):
                    setattr(args, key, value)

        except (FileNotFoundError, ValueError) as e:
            print(f"Error loading preset '{args.preset}': {e}")
            return 1

    # Check API keys
    if not has_required_keys():
        print("ERROR: OPENAI_API_KEY environment variable is required")
        print('Set it with: $env:OPENAI_API_KEY = "sk-..." (PowerShell)')
        print('Or: export OPENAI_API_KEY="sk-..." (bash)')
        return 1

    # Load policy for allowed publish models
    try:
        allowed_models = load_policy(args.policy)
        print(f"Using policy: {args.policy} ({len(allowed_models)} allowed models)")
    except Exception as e:
        print(f"Error loading policy '{args.policy}': {e}")
        print("Falling back to default policy")
        allowed_models = ALLOWED_PUBLISH_MODELS

    print("Starting Debate-Judge-Publish workflow")
    print(f"Task: {args.task}")
    print(f"Trace: {args.trace_name}")

    # Load corpus if grounded mode is enabled
    corpus_docs = []
    if args.grounded_corpus:
        try:
            print(f"Loading corpus from: {args.grounded_corpus}")
            corpus_docs = load_corpus(args.grounded_corpus)
            stats = get_corpus_stats()
            print(f"Loaded {stats['total_docs']} documents for grounded mode")

            if args.grounded_required > 0:
                print(f"Grounded mode: requiring {args.grounded_required} corpus citations")
        except Exception as e:
            print(f"Error loading corpus: {e}")
            if args.grounded_required > 0:
                print("Error: Grounded mode required but corpus failed to load")
                return 1

    # Project costs before execution
    cost_projection = project_workflow_cost(
        max_debaters=args.max_debaters or 3,
        max_tokens=args.max_tokens,
        require_citations=args.require_citations,
        fastpath=args.fastpath,
        allowed_models=allowed_models,
    )

    print()
    print(format_cost_projection(cost_projection))

    # Check budget limits
    if args.budget_usd or args.budget_tokens:
        within_budget, warning_msg, error_msg = check_budget_limits(
            cost_projection.total_cost, cost_projection.total_tokens_projected, args.budget_usd, args.budget_tokens
        )

        if warning_msg:
            print(f"\n⚠️  Budget Warning: {warning_msg}")

        if error_msg:
            print(f"\n❌ Budget Exceeded: {error_msg}")
            print("Run aborted to prevent budget overrun.")
            return 1

        if within_budget and (args.budget_usd or args.budget_tokens):
            print("\n✅ Projected usage within budget limits")

    print()

    # Track execution time
    start_time = time.time()

    try:
        # Step 1: Debate
        print("Running debate stage...")
        drafts = await run_debate(
            args.task,
            args.max_tokens,
            args.temperature,
            args.require_citations,
            args.max_debaters,
            args.timeout_s,
            args.fastpath,
            args.seed,
            args.max_cost_usd,
            corpus_docs,
            args.grounded_required,
        )

        if not drafts:
            print("ERROR: No valid drafts generated")
            return 1

        # Step 2: Judge
        print("Running judge stage...")
        judgment = await judge_drafts(
            args.task, drafts, allowed_models, args.require_citations, args.margin_threshold, args.seed
        )

        # Step 3: Publish
        print("Running publish stage...")
        status, provider, text, reason, redaction_metadata = select_publish_text(
            judgment,
            drafts,
            allowed_models,
            enable_redaction=(args.redact == "on"),
            redaction_rules=args.redaction_rules,
        )

        # Extract citations from published text if grounded mode is enabled
        citations_list = []
        grounded_fail = None
        if args.grounded_corpus and corpus_docs:
            from .corpus import extract_citations

            citations_objs = extract_citations(text, corpus_docs, top_n=10)
            citations_list = [{"doc_id": c.doc_id, "title": c.title, "path": c.path} for c in citations_objs]

            # Check if grounding requirements were met
            if args.grounded_required > 0 and len(citations_objs) < args.grounded_required:
                grounded_fail = (
                    f"Insufficient citations: {len(citations_objs)} found, {args.grounded_required} required"
                )

        # Step 4: Save artifacts and log results
        # Create and save JSON artifact
        artifact = create_run_artifact(
            args.task,
            args.max_tokens,
            args.temperature,
            args.trace_name,
            drafts,
            judgment,
            status,
            provider,
            text,
            allowed_models,
            start_time,
            args.require_citations,
            args.policy,
            args.fastpath,
            args.max_debaters,
            args.timeout_s,
            args.margin_threshold,
            args.seed,
            None,  # model_usage - TODO: implement tracking
            reason,
            args.preset,  # Add preset name to artifact
            args.grounded_corpus,
            args.grounded_required,
            args.redact == "on",
            args.redaction_rules,
            redaction_metadata,
            len(corpus_docs) if corpus_docs else 0,
            citations_list,
            grounded_fail,
        )
        artifact_file = save_run_artifact(artifact)

        # Create Markdown log
        log_file = write_run_log(args.task, drafts, judgment, status, provider, text, args.trace_name, allowed_models)

        # Step 5: Console summary
        if not args.quiet:
            print("\n" + "=" * 60)
            print("WORKFLOW COMPLETE")
            print("=" * 60)
            print(get_publish_status_message(status, provider))
            print(f"Log file: {log_file}")

            if text:
                print(f"\nContent preview ({provider}):")
                print("-" * 40)
                preview = text[:300] + "..." if len(text) > 300 else text
                print(preview)
                print("-" * 40)

        # Step 6: Cost footer
        print_cost_footer(artifact, args.quiet)

        # Step 7: Export metrics if requested
        if args.metrics:
            try:
                df = load_runs()
                export_metrics(df, args.metrics)
            except Exception as e:
                print(f"Warning: Failed to export metrics: {e}")

        return 0

    except Exception as e:
        print(f"ERROR: Workflow failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
