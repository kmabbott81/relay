"""Meeting Transcript Brief - Academic workflow for summarizing meetings.

Usage:
    python -m relay_ai.workflows.examples.meeting_transcript_brief --dry-run
    python -m relay_ai.workflows.examples.meeting_transcript_brief --live
"""

import argparse
import logging
from datetime import datetime
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


def generate_sample_transcript() -> dict:
    """
    Generate sample meeting transcript for demonstration.

    Returns:
        Dictionary with meeting metadata and transcript
    """
    return {
        "meeting_title": "Research Project Status - Sprint Review",
        "meeting_date": datetime.now().strftime("%Y-%m-%d"),
        "attendees": "Prof. Smith, Dr. Johnson, Alice Chen (PhD candidate), Bob Martinez (Research Assistant)",
        "transcript": """
        Prof. Smith: Good morning everyone. Let's start with the data collection update.

        Alice Chen: We've completed data collection from 85% of participants. The remaining 15% are scheduled for next week. Initial analysis shows promising trends in the hypothesis validation.

        Dr. Johnson: That's excellent progress. Have you encountered any issues with the data quality?

        Alice Chen: Minor issues with two participants - incomplete surveys. We've reached out for follow-ups.

        Prof. Smith: Good. Bob, what's the status on the literature review?

        Bob Martinez: I've reviewed 47 papers so far. I'm finding strong support for our theoretical framework. I'll have the complete synthesis ready by Friday.

        Dr. Johnson: Make sure to include the recent Nature publication from Chen et al. It's highly relevant.

        Bob Martinez: Will do. I'll add it to the list.

        Prof. Smith: Let's discuss the conference paper. Alice, can you draft the abstract by next Wednesday?

        Alice Chen: Yes, I'll have a draft ready. Should I focus on the preliminary findings or wait for the complete dataset?

        Prof. Smith: Use preliminary findings but note it's ongoing research. We need to submit by the 15th deadline.

        Dr. Johnson: One concern - our IRB approval expires next month. We need to file for renewal.

        Prof. Smith: Good catch. Bob, can you handle the IRB renewal paperwork?

        Bob Martinez: Absolutely. I'll start on it this week.

        Prof. Smith: Perfect. Any other questions or concerns? No? Let's reconvene next Tuesday same time.
        """,
    }


def format_prompt(template: str, meeting_title: str, meeting_date: str, attendees: str, transcript: str) -> str:
    """
    Format prompt template with variables.

    Args:
        template: Prompt template string
        meeting_title: Title of the meeting
        meeting_date: Date of the meeting
        attendees: List of attendees
        transcript: Meeting transcript

    Returns:
        Formatted prompt
    """
    return template.format(
        meeting_title=meeting_title,
        meeting_date=meeting_date,
        attendees=attendees,
        transcript=transcript,
    )


def write_brief(output_path: Path, content: str, metadata: dict):
    """
    Write meeting brief to output file.

    Args:
        output_path: Path to output file
        content: Brief content
        metadata: Workflow metadata
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Meeting Brief\n\n")
        f.write(f"**Generated:** {datetime.utcnow().isoformat()}Z\n")
        f.write(f"**Workflow:** {metadata['workflow_name']}\n\n")
        f.write("---\n\n")
        f.write(content)

    logger.info(f"Brief written to: {output_path}")


def run_workflow(dry_run: bool = True) -> str:
    """
    Run meeting transcript brief workflow.

    Args:
        dry_run: If True, use mock adapter; if False, use live OpenAI API

    Returns:
        Path to generated brief
    """
    logger.info(f"Running meeting transcript brief workflow (dry_run={dry_run})")

    # Load configuration
    project_root = Path(__file__).parent.parent.parent.parent
    config_path = project_root / "templates" / "examples" / "meeting_brief.yaml"
    config = load_config(config_path)

    logger.info(f"Loaded config from: {config_path}")

    # Generate sample meeting data
    meeting_data = generate_sample_transcript()

    # Format prompt
    prompt = format_prompt(
        config["prompt_template"],
        meeting_title=meeting_data["meeting_title"],
        meeting_date=meeting_data["meeting_date"],
        attendees=meeting_data["attendees"],
        transcript=meeting_data["transcript"],
    )

    # Create adapter (mock or live)
    adapter = create_adapter(use_mock=dry_run)

    # Generate brief
    logger.info("Generating meeting brief...")
    brief_content = adapter.generate_text(
        prompt,
        workflow="meeting_brief",
        model=config["parameters"]["model"],
        max_tokens=config["parameters"]["max_tokens"],
        temperature=config["parameters"]["temperature"],
    )

    # Prepare output path
    today = datetime.now().strftime("%Y-%m-%d")
    output_dir = project_root / "artifacts" / "meeting_briefs" / today
    output_path = output_dir / "brief.md"

    # Write brief
    write_brief(output_path, brief_content, config)

    return str(output_path)


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Meeting Transcript Brief - Summarize meetings and extract action items",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--dry-run", action="store_true", help="Run with mock adapter (no API calls)")
    mode_group.add_argument("--live", action="store_true", help="Run with live OpenAI API")

    args = parser.parse_args()

    try:
        output_path = run_workflow(dry_run=args.dry_run)
        print(f"\nSuccess! Meeting brief generated: {output_path}")
        exit(0)
    except Exception as e:
        logger.error(f"Workflow failed: {e}", exc_info=True)
        print(f"\nError: {e}")
        exit(1)


if __name__ == "__main__":
    main()
