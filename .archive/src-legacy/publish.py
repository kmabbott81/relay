"""Publishing logic with verbatim provider selection."""

from typing import Any, Optional

from .guardrails import validate_draft_content, validate_publish_text
from .redaction import apply_redactions
from .schemas import Draft, Judgment, ScoredDraft


def create_sort_key(scored_draft: ScoredDraft, allowed_providers: list[str]) -> tuple:
    """
    Create sort key for deterministic tie-breaking.

    Returns tuple for sorting (all values negated for reverse sort):
    1. Primary score (negated for descending)
    2. Allowed provider bonus (1 if allowed, 0 if not)
    3. Support sub-score (negated for descending)
    4. Provider stability order (OpenAI providers first)
    """
    # Primary score (higher is better, so negate for reverse sort)
    primary_score = scored_draft.score

    # Allowed provider bonus (1 if in allowed list, 0 if not)
    allowed_bonus = 1 if scored_draft.provider in allowed_providers else 0

    # Support sub-score (higher is better, so negate for reverse sort)
    support_score = scored_draft.subscores.get("support", 0) if scored_draft.subscores else 0

    # Provider stability order (OpenAI first, then others alphabetically)
    provider_order = 0 if scored_draft.provider.startswith("openai/") else 1

    return (-primary_score, -allowed_bonus, -support_score, provider_order, scored_draft.provider)


def select_publish_text(
    judgment: Judgment,
    drafts: list[Draft],
    allowed: list[str],
    enable_redaction: bool = True,
    redaction_rules: Optional[str] = None,
) -> tuple[str, str, str, str, dict[str, Any]]:
    """
    Select text to publish based on judgment and allowed providers.

    Args:
        judgment: Judge's ranking and decision
        drafts: Original list of drafts
        allowed: List of allowed provider names for publishing
        enable_redaction: Whether to apply redaction to published text
        redaction_rules: Optional path to custom redaction rules

    Returns:
        Tuple of (status, provider, text, reason, redaction_metadata) where:
        - status: "published", "advisory_only", or "none"
        - provider: Selected provider name
        - text: Published text (redacted if enabled)
        - reason: Reason for status (empty for published)
        - redaction_metadata: Dict with redaction info
    """
    if not judgment.ranked:
        return ("none", "", "", "No ranked drafts available", {"redacted": False, "events": []})

    # Try to find highest-ranked draft from allowed provider
    for scored_draft in judgment.ranked:
        if scored_draft.provider in allowed:
            # Validate content before publishing
            is_valid, reason = validate_draft_content(scored_draft.answer, scored_draft.safety_flags)

            if not is_valid:
                print(f"Warning: Draft from {scored_draft.provider} failed validation: {reason}")
                continue

            try:
                # Final publish validation (checks for long quotes)
                validate_publish_text(scored_draft.answer)

                # Apply redaction if enabled
                final_text = scored_draft.answer
                redaction_metadata = {"redacted": False, "events": []}

                if enable_redaction:
                    redacted_text, redaction_events = apply_redactions(
                        scored_draft.answer, strategy="label", rules_path=redaction_rules
                    )

                    if redaction_events:
                        final_text = redacted_text
                        redaction_metadata = {
                            "redacted": True,
                            "events": [
                                {"type": e.type, "count": e.count, "rule_name": e.rule_name} for e in redaction_events
                            ],
                        }
                        print(f"Applied {sum(e.count for e in redaction_events)} redactions to published text")

                return ("published", scored_draft.provider, final_text, "", redaction_metadata)

            except ValueError as e:
                print(f"Warning: Draft from {scored_draft.provider} failed publish validation: {e}")
                continue

    # No allowed provider found or all failed validation
    # Check if all drafts are disqualified
    qualified_drafts = [d for d in judgment.ranked if d.score > 0 and "disqualified_citations" not in d.safety_flags]

    if not qualified_drafts:
        # All drafts disqualified
        disqualified_reasons = [d.reasons for d in judgment.ranked if "DISQUALIFIED" in d.reasons]
        reason = "All drafts disqualified: " + "; ".join(disqualified_reasons[:2])  # Show first 2 reasons
        return ("advisory_only", "", "", reason, {"redacted": False, "events": []})

    # Return advisory-only (top-ranked qualified draft regardless of provider)
    top_draft = qualified_drafts[0]

    # Still validate content for advisory
    is_valid, reason = validate_draft_content(top_draft.answer, top_draft.safety_flags)

    if not is_valid:
        print(f"Warning: Top-ranked draft failed validation: {reason}")
        return ("none", "", "", f"Top draft validation failed: {reason}", {"redacted": False, "events": []})

    # Apply redaction to advisory text as well
    final_text = top_draft.answer
    redaction_metadata = {"redacted": False, "events": []}

    if enable_redaction:
        redacted_text, redaction_events = apply_redactions(
            top_draft.answer, strategy="label", rules_path=redaction_rules
        )

        if redaction_events:
            final_text = redacted_text
            redaction_metadata = {
                "redacted": True,
                "events": [{"type": e.type, "count": e.count, "rule_name": e.rule_name} for e in redaction_events],
            }
            print(f"Applied {sum(e.count for e in redaction_events)} redactions to advisory text")

    advisory_reason = f"Winner {top_draft.provider} not in allowed list {allowed}"
    return ("advisory_only", top_draft.provider, final_text, advisory_reason, redaction_metadata)


def get_publish_status_message(status: str, provider: str) -> str:
    """
    Get user-friendly status message for publishing result.

    Args:
        status: Publishing status
        provider: Provider name

    Returns:
        Formatted status message
    """
    if status == "published":
        return f"PUBLISHED (verbatim from {provider})"
    elif status == "advisory_only":
        return f"ADVISORY ONLY (from {provider} - not in allowed list)"
    else:
        return "NO CONTENT AVAILABLE (all drafts failed validation)"


def format_publish_metadata(status: str, provider: str, judgment: Judgment, drafts: list[Draft]) -> str:
    """
    Format metadata for logging and display.

    Args:
        status: Publishing status
        provider: Selected provider
        judgment: Judge's decision
        drafts: Original drafts

    Returns:
        Formatted metadata string
    """
    metadata = []

    metadata.append(f"Status: {get_publish_status_message(status, provider)}")
    metadata.append(f"Total Drafts: {len(drafts)}")
    metadata.append(f"Ranked Drafts: {len(judgment.ranked)}")

    if judgment.ranked:
        metadata.append(f"Top Score: {judgment.ranked[0].score:.1f}/10")
        metadata.append(f"Winner: {judgment.winner_provider}")

    # Provider breakdown
    providers = {}
    for draft in drafts:
        providers[draft.provider] = providers.get(draft.provider, 0) + 1

    provider_list = [f"{p}: {c}" for p, c in providers.items()]
    metadata.append(f"Providers: {', '.join(provider_list)}")

    return "\n".join(metadata)


def create_pending_approval(
    judgment: Judgment,
    drafts: list[Draft],
    allowed: list[str],
    enable_redaction: bool = True,
    redaction_rules: Optional[str] = None,
) -> tuple[str, str, str, str, dict[str, Any]]:
    """
    Create a pending approval result that requires human review.

    Args:
        judgment: Judge's ranking and decision
        drafts: Original list of drafts
        allowed: List of allowed provider names
        enable_redaction: Whether to apply redaction
        redaction_rules: Optional path to custom redaction rules

    Returns:
        Tuple of (status, provider, text, reason, redaction_metadata) where status is "pending_approval"
    """
    if not judgment.ranked:
        return ("none", "", "", "No ranked drafts available", {"redacted": False, "events": []})

    # Get the top-ranked draft for preview
    top_draft = judgment.ranked[0]

    # Validate content
    is_valid, reason = validate_draft_content(top_draft.answer, top_draft.safety_flags)

    if not is_valid:
        return ("none", "", "", f"Top draft failed validation: {reason}", {"redacted": False, "events": []})

    # Apply redaction for preview
    final_text = top_draft.answer
    redaction_metadata = {"redacted": False, "events": []}

    if enable_redaction:
        redacted_text, redaction_events = apply_redactions(
            top_draft.answer, strategy="label", rules_path=redaction_rules
        )

        if redaction_events:
            final_text = redacted_text
            redaction_metadata = {
                "redacted": True,
                "events": [{"type": e.type, "count": e.count, "rule_name": e.rule_name} for e in redaction_events],
            }

    # Return pending approval status
    in_allowed = "Yes" if top_draft.provider in allowed else "No"
    reason = f"Awaiting approval | Provider: {top_draft.provider} | In allowed list: {in_allowed}"

    return ("pending_approval", top_draft.provider, final_text, reason, redaction_metadata)


def approve_pending_result(
    pending_status: str, pending_provider: str, pending_text: str, allowed: list[str]
) -> tuple[str, str, str, str]:
    """
    Approve a pending result and finalize publishing.

    Args:
        pending_status: Current status (should be "pending_approval")
        pending_provider: Provider of pending draft
        pending_text: Text of pending draft
        allowed: List of allowed providers

    Returns:
        Tuple of (status, provider, text, reason)
    """
    if pending_status != "pending_approval":
        return (pending_status, pending_provider, pending_text, "Cannot approve non-pending result")

    # Approve: finalize as published
    return ("published", pending_provider, pending_text, "")


def reject_pending_result(
    pending_status: str, pending_provider: str, pending_text: str, rejection_reason: str
) -> tuple[str, str, str, str]:
    """
    Reject a pending result.

    Args:
        pending_status: Current status (should be "pending_approval")
        pending_provider: Provider of pending draft
        pending_text: Text of pending draft
        rejection_reason: Reason for rejection

    Returns:
        Tuple of (status, provider, text, reason)
    """
    if pending_status != "pending_approval":
        return (pending_status, pending_provider, pending_text, "Cannot reject non-pending result")

    # Reject: mark as advisory with rejection reason
    return ("advisory_only", pending_provider, pending_text, f"Rejected by reviewer: {rejection_reason}")
