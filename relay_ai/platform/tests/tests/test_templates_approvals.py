"""Tests for template approvals workflow."""

from src.publish import approve_pending_result, create_pending_approval, reject_pending_result
from src.schemas import Judgment, ScoredDraft


def create_test_judgment() -> Judgment:
    """Helper to create a test judgment."""
    scored_draft = ScoredDraft(
        provider="openai/gpt-4o",
        answer="This is a test answer.",
        score=8.5,
        reasons="Well-structured and comprehensive",
        subscores={"support": 9.0, "clarity": 8.0},
        safety_flags=[],
        evidence=[],
    )

    return Judgment(
        ranked=[scored_draft],
        winner_provider="openai/gpt-4o",
        judge_provider="openai/gpt-4o",
        judgment_text="Test judgment",
        prompt_tokens=100,
        completion_tokens=200,
    )


def test_create_pending_approval():
    """Creating pending approval should return pending status."""
    judgment = create_test_judgment()
    drafts = []  # Not used in create_pending_approval logic
    allowed = ["openai/gpt-4o"]

    status, provider, text, reason, redaction_meta = create_pending_approval(judgment, drafts, allowed)

    assert status == "pending_approval"
    assert provider == "openai/gpt-4o"
    assert text == "This is a test answer."
    assert "Awaiting approval" in reason
    assert redaction_meta["redacted"] is False


def test_pending_approval_includes_provider_info():
    """Pending approval reason should include provider and allowed status."""
    judgment = create_test_judgment()
    drafts = []
    allowed = ["anthropic/claude-3-sonnet"]  # Different from judgment provider

    status, provider, text, reason, redaction_meta = create_pending_approval(judgment, drafts, allowed)

    assert status == "pending_approval"
    assert "Provider: openai/gpt-4o" in reason
    assert "In allowed list: No" in reason


def test_approve_pending_result():
    """Approving should change status to published."""
    status, provider, text, reason = approve_pending_result(
        pending_status="pending_approval",
        pending_provider="openai/gpt-4o",
        pending_text="Test content",
        allowed=["openai/gpt-4o"],
    )

    assert status == "published"
    assert provider == "openai/gpt-4o"
    assert text == "Test content"
    assert reason == ""  # No reason for approved content


def test_approve_non_pending_fails():
    """Cannot approve non-pending results."""
    status, provider, text, reason = approve_pending_result(
        pending_status="published",  # Already published
        pending_provider="openai/gpt-4o",
        pending_text="Test content",
        allowed=["openai/gpt-4o"],
    )

    assert status == "published"  # Status unchanged
    assert "Cannot approve" in reason


def test_reject_pending_result():
    """Rejecting should change status to advisory_only."""
    status, provider, text, reason = reject_pending_result(
        pending_status="pending_approval",
        pending_provider="openai/gpt-4o",
        pending_text="Test content",
        rejection_reason="Insufficient detail",
    )

    assert status == "advisory_only"
    assert provider == "openai/gpt-4o"
    assert text == "Test content"
    assert "Rejected by reviewer" in reason
    assert "Insufficient detail" in reason


def test_reject_non_pending_fails():
    """Cannot reject non-pending results."""
    status, provider, text, reason = reject_pending_result(
        pending_status="published",
        pending_provider="openai/gpt-4o",
        pending_text="Test content",
        rejection_reason="Test",
    )

    assert status == "published"  # Status unchanged
    assert "Cannot reject" in reason


def test_approval_workflow_full_cycle():
    """Full workflow: pending -> approve -> published."""
    judgment = create_test_judgment()
    drafts = []
    allowed = ["openai/gpt-4o"]

    # Step 1: Create pending approval
    status1, provider1, text1, reason1, _ = create_pending_approval(judgment, drafts, allowed)

    assert status1 == "pending_approval"
    assert "Awaiting approval" in reason1

    # Step 2: Approve
    status2, provider2, text2, reason2 = approve_pending_result(status1, provider1, text1, allowed)

    assert status2 == "published"
    assert reason2 == ""
    assert text2 == text1  # Same text


def test_rejection_workflow_full_cycle():
    """Full workflow: pending -> reject -> advisory_only."""
    judgment = create_test_judgment()
    drafts = []
    allowed = ["openai/gpt-4o"]

    # Step 1: Create pending approval
    status1, provider1, text1, reason1, _ = create_pending_approval(judgment, drafts, allowed)

    assert status1 == "pending_approval"

    # Step 2: Reject
    status2, provider2, text2, reason2 = reject_pending_result(status1, provider1, text1, "Not relevant")

    assert status2 == "advisory_only"
    assert "Rejected by reviewer" in reason2
    assert "Not relevant" in reason2
    assert text2 == text1  # Same text


def test_pending_approval_with_no_drafts():
    """Pending approval with no ranked drafts should return none."""
    # Empty judgment
    judgment = Judgment(
        ranked=[],
        winner_provider="",
        judge_provider="openai/gpt-4o",
        judgment_text="No drafts",
        prompt_tokens=0,
        completion_tokens=0,
    )

    drafts = []
    allowed = ["openai/gpt-4o"]

    status, provider, text, reason, _ = create_pending_approval(judgment, drafts, allowed)

    assert status == "none"
    assert "No ranked drafts" in reason
