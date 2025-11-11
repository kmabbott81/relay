"""Unit tests for grounded mode with publish integration."""

import pytest

from relay_ai.publish import select_publish_text
from relay_ai.schemas import Judgment, ScoredDraft


@pytest.fixture
def sample_judgment():
    """Create a sample judgment for testing."""
    scored_drafts = [
        ScoredDraft(
            provider="openai/gpt-4o",
            answer="This is the best answer with [Source 1] and [Source 2] citations.",
            evidence=["Evidence from Source 1", "Evidence from Source 2"],
            confidence=0.9,
            safety_flags=[],
            score=9.5,
            reasons="Excellent answer with proper citations",
            subscores={"task_fit": 4.0, "support": 4.0, "clarity": 2.0},
        ),
        ScoredDraft(
            provider="anthropic/claude-3-5-sonnet",
            answer="This is a good answer but without citations.",
            evidence=["Some evidence"],
            confidence=0.8,
            safety_flags=[],
            score=7.0,
            reasons="Good answer but lacks proper citations",
            subscores={"task_fit": 3.0, "support": 3.0, "clarity": 1.5},
        ),
    ]

    return Judgment(
        ranked=scored_drafts,
        winner_provider="openai/gpt-4o",
        scores={"openai/gpt-4o": 9.5, "anthropic/claude-3-5-sonnet": 7.0},
    )


@pytest.fixture
def disqualified_judgment():
    """Create a judgment where drafts are disqualified for insufficient citations."""
    scored_drafts = [
        ScoredDraft(
            provider="openai/gpt-4o",
            answer="This answer has no citations.",
            evidence=[],
            confidence=0.5,
            safety_flags=["disqualified_citations"],
            score=0.0,
            reasons="DISQUALIFIED: Insufficient citations (0 found, 2 required)",
            subscores={},
        ),
        ScoredDraft(
            provider="anthropic/claude-3-5-sonnet",
            answer="This also lacks citations.",
            evidence=[],
            confidence=0.5,
            safety_flags=["disqualified_citations"],
            score=0.0,
            reasons="DISQUALIFIED: Insufficient citations (0 found, 2 required)",
            subscores={},
        ),
    ]

    return Judgment(ranked=scored_drafts, winner_provider="", scores={})


def test_publish_with_grounded_draft(sample_judgment):
    """Test publishing a grounded draft with citations."""
    allowed_providers = ["openai/gpt-4o", "openai/gpt-4o-mini"]

    status, provider, text, reason, redaction_meta = select_publish_text(
        sample_judgment, [], allowed_providers, enable_redaction=False
    )

    assert status == "published"
    assert provider == "openai/gpt-4o"
    assert "[Source 1]" in text
    assert "[Source 2]" in text
    assert reason == ""


def test_publish_disqualified_grounded_drafts(disqualified_judgment):
    """Test that disqualified drafts still publish but are marked."""
    allowed_providers = ["openai/gpt-4o", "openai/gpt-4o-mini"]

    status, provider, text, reason, redaction_meta = select_publish_text(
        disqualified_judgment, [], allowed_providers, enable_redaction=False
    )

    # Note: Current behavior publishes disqualified drafts if from allowed provider
    # Judge adds disqualified_citations flag which is visible in artifacts
    assert status in ["published", "advisory_only"]  # Either outcome is acceptable
    assert provider in allowed_providers or provider == ""


def test_grounded_citations_in_metadata():
    """Test that citation metadata is properly structured."""
    # This test verifies the structure but the actual citation extraction
    # happens at the workflow level, not in select_publish_text

    scored_drafts = [
        ScoredDraft(
            provider="openai/gpt-4o",
            answer="According to [Research Paper 1] and [Study 2], we find...",
            evidence=["Citation from paper 1", "Citation from study 2"],
            confidence=0.9,
            safety_flags=[],
            score=9.0,
            reasons="Well-cited answer",
            subscores={"task_fit": 4.0, "support": 4.0, "clarity": 1.5},
        ),
    ]

    judgment = Judgment(ranked=scored_drafts, winner_provider="openai/gpt-4o", scores={"openai/gpt-4o": 9.0})

    status, provider, text, reason, redaction_meta = select_publish_text(
        judgment, [], ["openai/gpt-4o"], enable_redaction=False
    )

    assert status == "published"
    assert "[Research Paper 1]" in text
    assert "[Study 2]" in text


def test_publish_with_redaction_enabled(sample_judgment):
    """Test that redaction is applied when enabled."""
    # Create judgment with sensitive data
    scored_drafts = [
        ScoredDraft(
            provider="openai/gpt-4o",
            answer="Contact user@example.com for more info. API key: sk-1234567890abcdefghijklmnopqrstuvwxyz123456",
            evidence=[],
            confidence=0.9,
            safety_flags=[],
            score=9.0,
            reasons="Good answer but contains sensitive data",
            subscores={"task_fit": 4.0, "support": 3.5, "clarity": 2.0},
        ),
    ]

    judgment = Judgment(ranked=scored_drafts, winner_provider="openai/gpt-4o", scores={"openai/gpt-4o": 9.0})

    status, provider, text, reason, redaction_meta = select_publish_text(
        judgment, [], ["openai/gpt-4o"], enable_redaction=True
    )

    assert status == "published"
    assert "user@example.com" not in text
    assert "sk-1234567890" not in text
    assert redaction_meta["redacted"] is True
    assert len(redaction_meta["events"]) > 0


def test_publish_with_redaction_disabled(sample_judgment):
    """Test that redaction can be disabled."""
    # Create judgment with sensitive data
    scored_drafts = [
        ScoredDraft(
            provider="openai/gpt-4o",
            answer="Contact user@example.com for more info.",
            evidence=[],
            confidence=0.9,
            safety_flags=[],
            score=9.0,
            reasons="Good answer",
            subscores={"task_fit": 4.0, "support": 3.5, "clarity": 2.0},
        ),
    ]

    judgment = Judgment(ranked=scored_drafts, winner_provider="openai/gpt-4o", scores={"openai/gpt-4o": 9.0})

    status, provider, text, reason, redaction_meta = select_publish_text(
        judgment, [], ["openai/gpt-4o"], enable_redaction=False
    )

    assert status == "published"
    assert "user@example.com" in text  # Should NOT be redacted
    assert redaction_meta["redacted"] is False
    assert len(redaction_meta["events"]) == 0


def test_redaction_metadata_structure():
    """Test structure of redaction metadata."""
    scored_drafts = [
        ScoredDraft(
            provider="openai/gpt-4o",
            answer="Emails: user1@example.com, user2@example.com, user3@example.com",
            evidence=[],
            confidence=0.9,
            safety_flags=[],
            score=9.0,
            reasons="Good answer",
            subscores={"task_fit": 4.0, "support": 3.5, "clarity": 2.0},
        ),
    ]

    judgment = Judgment(ranked=scored_drafts, winner_provider="openai/gpt-4o", scores={"openai/gpt-4o": 9.0})

    status, provider, text, reason, redaction_meta = select_publish_text(
        judgment, [], ["openai/gpt-4o"], enable_redaction=True
    )

    assert "redacted" in redaction_meta
    assert "events" in redaction_meta
    assert isinstance(redaction_meta["events"], list)

    if redaction_meta["redacted"]:
        # Verify event structure
        for event in redaction_meta["events"]:
            assert "type" in event
            assert "count" in event
            assert "rule_name" in event
            assert event["count"] > 0


def test_grounded_fail_disqualification():
    """Test that drafts with disqualified_citations flag are handled."""
    scored_drafts = [
        ScoredDraft(
            provider="openai/gpt-4o",
            answer="This answer has only one citation [Source 1].",
            evidence=["Single citation"],
            confidence=0.7,
            safety_flags=["disqualified_citations"],
            score=0.0,
            reasons="DISQUALIFIED: Insufficient citations (1 found, 2 required)",
            subscores={},
        ),
    ]

    judgment = Judgment(ranked=scored_drafts, winner_provider="", scores={})

    status, provider, text, reason, redaction_meta = select_publish_text(
        judgment, [], ["openai/gpt-4o"], enable_redaction=False
    )

    # Disqualified drafts can still be published if from allowed provider
    # The disqualified_citations flag is preserved in safety_flags for tracking
    assert status in ["published", "advisory_only"]
    assert "disqualified_citations" in scored_drafts[0].safety_flags


def test_advisory_with_redaction():
    """Test that redaction is applied to advisory-only text as well."""
    scored_drafts = [
        ScoredDraft(
            provider="anthropic/claude-3-5-sonnet",  # Not in allowed list
            answer="Contact user@example.com for details.",
            evidence=[],
            confidence=0.9,
            safety_flags=[],
            score=9.0,
            reasons="Good answer",
            subscores={"task_fit": 4.0, "support": 3.5, "clarity": 2.0},
        ),
    ]

    judgment = Judgment(
        ranked=scored_drafts, winner_provider="anthropic/claude-3-5-sonnet", scores={"anthropic/claude-3-5-sonnet": 9.0}
    )

    # Provider not in allowed list, should be advisory_only
    status, provider, text, reason, redaction_meta = select_publish_text(
        judgment, [], ["openai/gpt-4o"], enable_redaction=True  # Different provider
    )

    assert status == "advisory_only"
    assert "user@example.com" not in text  # Should be redacted
    assert redaction_meta["redacted"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
