"""Weekly Report Pack - Professional workflow for generating weekly status reports.

Usage:
    python -m relay_ai.workflows.examples.weekly_report_pack --dry-run
    python -m relay_ai.workflows.examples.weekly_report_pack --live
"""

import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from relay_ai.agents.openai_adapter import create_adapter

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_config(config_path: Path) -> dict:
    """
    Load workflow configuration from YAML.

    Args:
        config_path: Path to config file

    Returns:
        Configuration dictionary
    """
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def generate_sample_context() -> str:
    """
    Generate sample context for demonstration.

    Returns:
        Sample weekly activity context
    """
    return """
    **Team Activities:**
    - Completed Sprint 24 planning and kickoff
    - Deployed multi-region observability dashboard
    - Fixed 3 critical bugs in authentication flow
    - Onboarded 2 new team members

    **Metrics:**
    - Velocity: 34 story points (target: 30)
    - Code coverage: 87% (up from 84%)
    - Incident response time: 12 min avg (target: <15 min)
    - Customer satisfaction: 4.6/5.0

    **Challenges:**
    - Database migration delayed by 2 days due to vendor issues
    - Need additional resources for Q4 planning

    **Upcoming:**
    - Launch new analytics feature (scheduled for next week)
    - Security audit preparation
    - Team offsite planning
    """


def format_prompt(template: str, start_date: str, end_date: str, context: str) -> str:
    """
    Format prompt template with variables.

    Args:
        template: Prompt template string
        start_date: Report start date
        end_date: Report end date
        context: Activity context

    Returns:
        Formatted prompt
    """
    return template.format(start_date=start_date, end_date=end_date, context=context)


def write_report(output_path: Path, content: str, metadata: dict):
    """
    Write report to output file.

    Args:
        output_path: Path to output file
        content: Report content
        metadata: Workflow metadata
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Weekly Status Report\n\n")
        f.write(f"**Generated:** {datetime.utcnow().isoformat()}Z\n")
        f.write(f"**Workflow:** {metadata['workflow_name']}\n\n")
        f.write("---\n\n")
        f.write(content)

    logger.info(f"Report written to: {output_path}")


def run_workflow(dry_run: bool = True) -> str:
    """
    Run weekly report workflow.

    Args:
        dry_run: If True, use mock adapter; if False, use live OpenAI API

    Returns:
        Path to generated report
    """
    logger.info(f"Running weekly report workflow (dry_run={dry_run})")

    # Load configuration
    project_root = Path(__file__).parent.parent.parent.parent
    config_path = project_root / "templates" / "examples" / "weekly_report.yaml"
    config = load_config(config_path)

    logger.info(f"Loaded config from: {config_path}")

    # Calculate date range (last 7 days)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    # Generate context
    context = generate_sample_context()

    # Format prompt
    prompt = format_prompt(
        config["prompt_template"],
        start_date=start_date_str,
        end_date=end_date_str,
        context=context,
    )

    # Create adapter (mock or live)
    adapter = create_adapter(use_mock=dry_run)

    # Generate report
    logger.info("Generating report...")
    report_content = adapter.generate_text(
        prompt,
        workflow="weekly_report",
        model=config["parameters"]["model"],
        max_tokens=config["parameters"]["max_tokens"],
        temperature=config["parameters"]["temperature"],
    )

    # Prepare output path
    output_dir = project_root / "artifacts" / "weekly_report" / end_date.strftime("%Y-%m-%d")
    output_path = output_dir / "report.md"

    # Write report
    write_report(output_path, report_content, config)

    return str(output_path)


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Weekly Report Pack - Generate weekly status reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--dry-run", action="store_true", help="Run with mock adapter (no API calls)")
    mode_group.add_argument("--live", action="store_true", help="Run with live OpenAI API")

    args = parser.parse_args()

    try:
        output_path = run_workflow(dry_run=args.dry_run)
        print(f"\nSuccess! Report generated: {output_path}")
        exit(0)
    except Exception as e:
        logger.error(f"Workflow failed: {e}", exc_info=True)
        print(f"\nError: {e}")
        exit(1)


if __name__ == "__main__":
    main()
