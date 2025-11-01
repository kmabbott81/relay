"""Tests for byte-exact publish and deterministic tie-breakers."""

import pytest

from src.publish import create_sort_key, select_publish_text
from src.schemas import Draft, Judgment, ScoredDraft


def test_byte_exact_publish():
    """Test that published text is byte-for-byte identical to selected draft."""
    # Create test drafts
    draft_text = "This is the exact text that should be published verbatim."

    draft = Draft(provider="openai/gpt-4o", answer=draft_text, evidence=["source 1"], confidence=0.8)

    scored_draft = ScoredDraft(
        provider="openai/gpt-4o",
        answer=draft_text,
        evidence=["source 1"],
        confidence=0.8,
        score=8.5,
        reasons="Good response",
        subscores={"task_fit": 4, "support": 3, "clarity": 1.5},
    )

    judgment = Judgment(ranked=[scored_draft], winner_provider="openai/gpt-4o")

    allowed = ["openai/gpt-4o"]

    # Test publish selection
    status, provider, text, _reason, _redaction_meta = select_publish_text(judgment, [draft], allowed)

    # Assertions
    assert status == "published"
    assert provider == "openai/gpt-4o"
    assert text == draft_text  # Byte-for-byte identical
    assert len(text) == len(draft_text)
    # Text should be identical in content (byte-for-byte)
    assert text == draft_text
    assert isinstance(text, str)


def test_tie_breaker_allowed_provider_preference():
    """Test tie-breaker prefers allowed providers."""
    # Create two drafts with same score
    draft1 = ScoredDraft(
        provider="anthropic/claude",
        answer="Claude response",
        evidence=["source 1"],
        confidence=0.9,
        score=8.0,
        reasons="Excellent",
        subscores={"task_fit": 3, "support": 3, "clarity": 2},
    )

    draft2 = ScoredDraft(
        provider="openai/gpt-4o",
        answer="OpenAI response",
        evidence=["source 2"],
        confidence=0.8,
        score=8.0,  # Same score as draft1
        reasons="Very good",
        subscores={"task_fit": 3, "support": 3, "clarity": 2},
    )

    allowed = ["openai/gpt-4o"]

    # Test sort keys
    key1 = create_sort_key(draft1, allowed)
    key2 = create_sort_key(draft2, allowed)

    # OpenAI should win tie-breaker (lower sort key value)
    assert key2 < key1

    # Test in judgment context
    judgment = Judgment(
        ranked=sorted([draft1, draft2], key=lambda x: create_sort_key(x, allowed)), winner_provider="openai/gpt-4o"
    )

    assert judgment.ranked[0].provider == "openai/gpt-4o"


def test_tie_breaker_support_subscore():
    """Test tie-breaker uses support sub-score when providers are both allowed."""
    draft1 = ScoredDraft(
        provider="openai/gpt-4o",
        answer="Response 1",
        evidence=["source 1"],
        confidence=0.8,
        score=8.0,
        reasons="Good",
        subscores={"task_fit": 3, "support": 2, "clarity": 3},  # Lower support
    )

    draft2 = ScoredDraft(
        provider="openai/gpt-4.1",
        answer="Response 2",
        evidence=["source 2", "source 3"],
        confidence=0.8,
        score=8.0,  # Same total score
        reasons="Also good",
        subscores={"task_fit": 3, "support": 4, "clarity": 1},  # Higher support
    )

    allowed = ["openai/gpt-4o", "openai/gpt-4.1"]

    # Test sort keys
    key1 = create_sort_key(draft1, allowed)
    key2 = create_sort_key(draft2, allowed)

    # Draft2 should win (higher support score)
    assert key2 < key1

    # Test in judgment context
    judgment = Judgment(
        ranked=sorted([draft1, draft2], key=lambda x: create_sort_key(x, allowed)), winner_provider="openai/gpt-4.1"
    )

    assert judgment.ranked[0].provider == "openai/gpt-4.1"
    assert judgment.ranked[0].subscores["support"] == 4


def test_tie_breaker_provider_stability():
    """Test tie-breaker uses stable provider ordering."""
    draft1 = ScoredDraft(
        provider="google/gemini",
        answer="Gemini response",
        evidence=["source 1"],
        confidence=0.8,
        score=8.0,
        reasons="Good",
        subscores={"task_fit": 3, "support": 3, "clarity": 2},
    )

    draft2 = ScoredDraft(
        provider="openai/gpt-4o",
        answer="OpenAI response",
        evidence=["source 2"],
        confidence=0.8,
        score=8.0,  # Same score
        reasons="Also good",
        subscores={"task_fit": 3, "support": 3, "clarity": 2},  # Same subscores
    )

    allowed = []  # Neither is in allowed list

    # Test sort keys
    key1 = create_sort_key(draft1, allowed)
    key2 = create_sort_key(draft2, allowed)

    # OpenAI should win stability tie-breaker
    assert key2 < key1

    # Test in judgment context
    judgment = Judgment(
        ranked=sorted([draft1, draft2], key=lambda x: create_sort_key(x, allowed)), winner_provider="openai/gpt-4o"
    )

    assert judgment.ranked[0].provider == "openai/gpt-4o"


def test_advisory_only_when_no_allowed_providers():
    """Test advisory_only status when winner is not in allowed list."""
    draft = Draft(provider="anthropic/claude", answer="Claude response that won", evidence=["source 1"], confidence=0.9)

    scored_draft = ScoredDraft(
        provider="anthropic/claude",
        answer="Claude response that won",
        evidence=["source 1"],
        confidence=0.9,
        score=9.5,
        reasons="Excellent response",
        subscores={"task_fit": 4, "support": 4, "clarity": 1.5},
    )

    judgment = Judgment(ranked=[scored_draft], winner_provider="anthropic/claude")

    allowed = ["openai/gpt-4o"]  # Claude not in allowed list

    # Test publish selection
    status, provider, text, _reason, _redaction_meta = select_publish_text(judgment, [draft], allowed)

    # Should be advisory only
    assert status == "advisory_only"
    assert provider == "anthropic/claude"
    assert text == "Claude response that won"


def test_deterministic_sorting():
    """Test that sorting is deterministic across multiple runs."""
    draft1 = ScoredDraft(
        provider="openai/gpt-4o",
        answer="Response A",
        evidence=["source 1"],
        confidence=0.8,
        score=8.0,
        reasons="Good",
        subscores={"task_fit": 3, "support": 3, "clarity": 2},
    )

    draft2 = ScoredDraft(
        provider="openai/gpt-4.1",
        answer="Response B",
        evidence=["source 2"],
        confidence=0.8,
        score=8.0,
        reasons="Also good",
        subscores={"task_fit": 3, "support": 3, "clarity": 2},
    )

    allowed = ["openai/gpt-4o", "openai/gpt-4.1"]
    drafts = [draft1, draft2]

    # Sort multiple times
    sorted1 = sorted(drafts, key=lambda x: create_sort_key(x, allowed))
    sorted2 = sorted(drafts, key=lambda x: create_sort_key(x, allowed))
    sorted3 = sorted(drafts, key=lambda x: create_sort_key(x, allowed))

    # Results should be identical
    assert [d.provider for d in sorted1] == [d.provider for d in sorted2]
    assert [d.provider for d in sorted2] == [d.provider for d in sorted3]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
