"""Inbox Drive Sweep - Personal workflow for prioritizing tasks from inbox and files.

Usage:
    python -m src.workflows.examples.inbox_drive_sweep --dry-run
    python -m src.workflows.examples.inbox_drive_sweep --live
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


def generate_sample_data() -> dict:
    """
    Generate sample inbox and drive data for demonstration.

    Returns:
        Dictionary with inbox items, files, priorities, and deadlines
    """
    return {
        "item_count": 12,
        "inbox_items": """
        1. Email from Sarah: "Urgent: Q4 budget review needed by Friday"
        2. Email from IT: "Password reset reminder - expires in 3 days"
        3. Email from Manager: "Performance review scheduled for next week"
        4. Newsletter: "Weekly industry trends digest"
        5. Email from Client: "Follow-up on proposal - need response"
        6. Calendar invite: "Team building event next month"
        7. Email from HR: "Benefits enrollment deadline approaching"
        8. Spam: "Limited time offer on productivity tools"
        9. Email from Project lead: "Sprint planning meeting tomorrow 10am"
        10. Email from Legal: "Updated contract for review and signature"
        11. LinkedIn notification: "5 new job opportunities"
        12. Email from Finance: "Expense report submission due Thursday"
        """,
        "file_count": 8,
        "drive_files": """
        1. Q3_Results_Final_Draft.pdf (modified yesterday)
        2. Project_Timeline_2024.xlsx (modified 3 days ago)
        3. Meeting_Notes_Sept.docx (modified last week)
        4. Budget_Proposal_v3.xlsx (modified 2 hours ago)
        5. Team_Photos_Offsite.zip (modified 2 weeks ago)
        6. Client_Contract_Draft.pdf (modified today)
        7. Training_Materials_Old.pptx (modified 6 months ago)
        8. Personal_Goals_2024.docx (modified 1 month ago)
        """,
        "user_priorities": "Q4 planning, client relationship management, team development",
        "upcoming_deadlines": "Budget review (Friday), Expense report (Thursday), Benefits enrollment (next week)",
    }


def format_prompt(
    template: str, item_count: int, inbox_items: str, file_count: int, drive_files: str, user_priorities: str, upcoming_deadlines: str
) -> str:
    """
    Format prompt template with variables.

    Args:
        template: Prompt template string
        item_count: Number of inbox items
        inbox_items: List of inbox items
        file_count: Number of drive files
        drive_files: List of drive files
        user_priorities: User's current priorities
        upcoming_deadlines: Upcoming deadlines

    Returns:
        Formatted prompt
    """
    return template.format(
        item_count=item_count,
        inbox_items=inbox_items,
        file_count=file_count,
        drive_files=drive_files,
        user_priorities=user_priorities,
        upcoming_deadlines=upcoming_deadlines,
    )


def write_priorities(output_path: Path, content: str, metadata: dict):
    """
    Write priorities to output file.

    Args:
        output_path: Path to output file
        content: Priorities content
        metadata: Workflow metadata
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# Inbox & Drive Sweep - Task Priorities\n\n")
        f.write(f"**Generated:** {datetime.utcnow().isoformat()}Z\n")
        f.write(f"**Workflow:** {metadata['workflow_name']}\n\n")
        f.write("---\n\n")
        f.write(content)

    logger.info(f"Priorities written to: {output_path}")


def run_workflow(dry_run: bool = True) -> str:
    """
    Run inbox drive sweep workflow.

    Args:
        dry_run: If True, use mock adapter; if False, use live OpenAI API

    Returns:
        Path to generated priorities
    """
    logger.info(f"Running inbox drive sweep workflow (dry_run={dry_run})")

    # Load configuration
    project_root = Path(__file__).parent.parent.parent.parent
    config_path = project_root / "templates" / "examples" / "inbox_sweep.yaml"
    config = load_config(config_path)

    logger.info(f"Loaded config from: {config_path}")

    # Generate sample data
    data = generate_sample_data()

    # Format prompt
    prompt = format_prompt(
        config["prompt_template"],
        item_count=data["item_count"],
        inbox_items=data["inbox_items"],
        file_count=data["file_count"],
        drive_files=data["drive_files"],
        user_priorities=data["user_priorities"],
        upcoming_deadlines=data["upcoming_deadlines"],
    )

    # Create adapter (mock or live)
    adapter = create_adapter(use_mock=dry_run)

    # Generate priorities
    logger.info("Generating task priorities...")
    priorities_content = adapter.generate_text(
        prompt,
        workflow="inbox_sweep",
        model=config["parameters"]["model"],
        max_tokens=config["parameters"]["max_tokens"],
        temperature=config["parameters"]["temperature"],
    )

    # Prepare output path
    today = datetime.now().strftime("%Y-%m-%d")
    output_dir = project_root / "artifacts" / "inbox_sweep" / today
    output_path = output_dir / "priorities.md"

    # Write priorities
    write_priorities(output_path, priorities_content, config)

    return str(output_path)


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Inbox Drive Sweep - Prioritize tasks from inbox and cloud drive",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--dry-run", action="store_true", help="Run with mock adapter (no API calls)")
    mode_group.add_argument("--live", action="store_true", help="Run with live OpenAI API")

    args = parser.parse_args()

    try:
        output_path = run_workflow(dry_run=args.dry_run)
        print(f"\nSuccess! Task priorities generated: {output_path}")
        exit(0)
    except Exception as e:
        logger.error(f"Workflow failed: {e}", exc_info=True)
        print(f"\nError: {e}")
        exit(1)


if __name__ == "__main__":
    main()
