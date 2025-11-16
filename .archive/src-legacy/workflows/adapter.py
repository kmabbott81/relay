"""
Workflow Adapter - Maps workflow references to callable functions.

Shims to existing example workflows, returning small payloads.
File writes from original workflows are preserved.

Sprint 32: Added template-based workflow execution.
"""

from typing import Callable


def run_template_workflow(template_name: str, version: str | None, params: dict) -> dict:
    """
    Run workflow via template registry.

    Args:
        template_name: Template name
        version: Template version (None for latest)
        params: User parameters

    Returns:
        Workflow output dict

    Raises:
        ValueError: If template not found or validation fails
    """
    from relay_ai.template_registry import load_and_validate

    # Load and validate
    template_def, resolved_params = load_and_validate(template_name, version, params)

    # Get workflow function from template
    workflow_ref = template_def.get("workflow_ref")

    if not workflow_ref:
        raise ValueError(f"Template {template_name} missing workflow_ref")

    # Look up workflow function
    workflow_fn = WORKFLOW_MAP.get(workflow_ref)

    if not workflow_fn:
        raise ValueError(f"Unknown workflow: {workflow_ref}")

    # Execute with resolved params (defaults applied)
    return workflow_fn(resolved_params)


def inbox_drive_sweep_adapter(params: dict) -> dict:
    """
    Adapter for inbox/drive sweep workflow.

    Args:
        params: Input parameters

    Returns:
        Dict with summary of prioritized items
    """
    # Minimal shim - in real impl, would call actual workflow
    return {
        "summary": "Prioritized 15 items: 5 high, 7 medium, 3 low",
        "high_priority_count": 5,
        "action_items": ["Budget approval", "Sprint planning", "Q4 roadmap"],
    }


def weekly_report_pack_adapter(params: dict) -> dict:
    """
    Adapter for weekly report generation.

    Args:
        params: Input parameters (may include upstream outputs)

    Returns:
        Dict with report summary
    """
    # Can access upstream via namespaced keys like "sweep__summary"
    upstream_summary = params.get("sweep__summary", "No upstream data")

    return {
        "summary": f"Generated weekly report. Incorporated: {upstream_summary}",
        "sections": ["Executive Summary", "Accomplishments", "Metrics", "Next Week"],
        "word_count": 1200,
    }


def meeting_transcript_brief_adapter(params: dict) -> dict:
    """
    Adapter for meeting transcript briefing.

    Args:
        params: Input parameters

    Returns:
        Dict with brief summary
    """
    return {
        "summary": "Generated meeting brief with 8 action items",
        "action_items": 8,
        "decisions": 3,
        "follow_ups": ["Schedule Q4 planning", "Review budget", "Update roadmap"],
    }


def template_adapter(params: dict) -> dict:
    """
    Adapter for template-based workflows (Sprint 32).

    Args:
        params: Must include template_name, optional template_version

    Returns:
        Workflow output dict
    """
    template_name = params.get("template_name")
    template_version = params.get("template_version")

    if not template_name:
        raise ValueError("template_adapter requires template_name parameter")

    # Extract template params (exclude template_name/template_version and upstream outputs)
    # Upstream outputs are namespaced with "__" (e.g., "task1__summary")
    template_params = {
        k: v for k, v in params.items() if k not in ["template_name", "template_version"] and "__" not in k
    }

    return run_template_workflow(template_name, template_version, template_params)


# Workflow registry - maps workflow_ref strings to callable functions
WORKFLOW_MAP: dict[str, Callable[[dict], dict]] = {
    "inbox_drive_sweep": inbox_drive_sweep_adapter,
    "weekly_report_pack": weekly_report_pack_adapter,
    "meeting_transcript_brief": meeting_transcript_brief_adapter,
    "template": template_adapter,  # Sprint 32: Template-based execution
}
