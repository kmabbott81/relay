"""Tests for negative paths and error handling."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.artifacts import create_run_artifact
from src.config import load_policy
from src.judge import judge_drafts
from src.publish import select_publish_text
from src.schemas import Draft, Judgment, ScoredDraft


def test_empty_drafts_list():
    """Test handling of empty drafts list."""

    async def test_empty_judgment():
        # Test judge_drafts with empty list
        judgment = await judge_drafts("Test task", [])

        assert judgment.ranked == []
        assert judgment.winner_provider == ""

    # Run the async test
    import asyncio

    asyncio.run(test_empty_judgment())


def test_judgment_returning_empty():
    """Test publish selection when judgment returns empty."""

    empty_judgment = Judgment(ranked=[], winner_provider="")
    drafts = []
    allowed = ["openai/gpt-4o"]

    status, provider, text, reason, _redaction_meta = select_publish_text(empty_judgment, drafts, allowed)

    assert status == "none"
    assert provider == ""
    assert text == ""
    assert reason == "No ranked drafts available"


def test_all_drafts_disqualified():
    """Test behavior when all drafts are disqualified due to insufficient citations."""

    # Create drafts that will be disqualified
    disqualified_draft = ScoredDraft(
        provider="openai/gpt-4o",
        answer="Response without enough citations",
        evidence=["only one source"],  # Not enough citations
        confidence=0.8,
        safety_flags=["disqualified_citations"],
        score=0.0,
        reasons="DISQUALIFIED: Only 1 citations, 2 required",
        subscores={"task_fit": 0, "support": 0, "clarity": 0},
    )

    judgment = Judgment(ranked=[disqualified_draft], winner_provider="openai/gpt-4o")

    original_drafts = [
        Draft(
            provider="openai/gpt-4o",
            answer="Response without enough citations",
            evidence=["only one source"],
            confidence=0.8,
            safety_flags=[],
        )
    ]

    status, provider, text, reason, _redaction_meta = select_publish_text(judgment, original_drafts, ["openai/gpt-4o"])

    assert status == "advisory_only"
    assert provider == ""
    assert text == ""
    assert "All drafts disqualified" in reason


def test_corrupt_policy_file():
    """Test handling of corrupt policy file."""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        # Write invalid JSON
        f.write('{"ALLOWED_PUBLISH_MODELS": [invalid json}')
        corrupt_path = f.name

    try:
        with pytest.raises(json.JSONDecodeError):
            load_policy(corrupt_path)
    finally:
        Path(corrupt_path).unlink()


def test_missing_policy_file():
    """Test handling of missing policy file."""

    with pytest.raises(FileNotFoundError):
        load_policy("nonexistent_policy_file.json")


def test_policy_file_missing_required_key():
    """Test handling of policy file missing ALLOWED_PUBLISH_MODELS key."""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        # Write JSON with wrong key
        json.dump({"WRONG_KEY": ["openai/gpt-4o"]}, f)
        wrong_key_path = f.name

    try:
        with pytest.raises(KeyError):
            load_policy(wrong_key_path)
    finally:
        Path(wrong_key_path).unlink()


def test_artifact_creation_with_minimal_data():
    """Test artifact creation with minimal required data."""

    import time

    # Create minimal test data
    minimal_judgment = Judgment(ranked=[], winner_provider="")
    minimal_drafts = []

    artifact = create_run_artifact(
        task="Test task",
        max_tokens=1000,
        temperature=0.3,
        trace_name="test",
        drafts=minimal_drafts,
        judgment=minimal_judgment,
        status="none",
        provider="",
        text="",
        allowed_models=[],
        start_time=time.time() - 1,  # 1 second ago
    )

    # Verify structure
    assert "run_metadata" in artifact
    assert "debate" in artifact
    assert "judge" in artifact
    assert "publish" in artifact
    assert "provenance" in artifact

    assert artifact["debate"]["total_drafts"] == 0
    assert artifact["judge"]["total_ranked"] == 0
    assert artifact["publish"]["status"] == "none"


def test_safety_flag_blocking():
    """Test that safety flags properly block publication."""

    # Create a draft with blocking safety flags
    unsafe_draft = ScoredDraft(
        provider="openai/gpt-4o",
        answer="Unsafe content that should be blocked",
        evidence=["source 1", "source 2"],
        confidence=0.8,
        safety_flags=["policy_violation", "hate_speech"],
        score=8.5,  # High score but should still be blocked
        reasons="High scoring but unsafe content",
        subscores={"task_fit": 4, "support": 4, "clarity": 0.5},
    )

    judgment = Judgment(ranked=[unsafe_draft], winner_provider="openai/gpt-4o")

    original_drafts = [
        Draft(
            provider="openai/gpt-4o",
            answer="Unsafe content that should be blocked",
            evidence=["source 1", "source 2"],
            confidence=0.8,
            safety_flags=["policy_violation", "hate_speech"],
        )
    ]

    status, provider, text, reason, _redaction_meta = select_publish_text(judgment, original_drafts, ["openai/gpt-4o"])

    # Should be blocked by safety validation
    assert status != "published"
    # Either none or advisory_only depending on validation outcome


def test_long_quote_blocking():
    """Test that long verbatim quotes block publication."""

    # Create a draft with a long verbatim quote (>75 words)
    long_quote_text = '"' + " ".join(["word"] * 80) + '"'  # 80 words in quotes

    long_quote_draft = ScoredDraft(
        provider="openai/gpt-4o",
        answer=f"Here is a response with a long quote: {long_quote_text}",
        evidence=["source 1", "source 2"],
        confidence=0.8,
        safety_flags=[],
        score=8.5,
        reasons="Good content but has long quote",
        subscores={"task_fit": 4, "support": 4, "clarity": 0.5},
    )

    judgment = Judgment(ranked=[long_quote_draft], winner_provider="openai/gpt-4o")

    original_drafts = [
        Draft(
            provider="openai/gpt-4o",
            answer=f"Here is a response with a long quote: {long_quote_text}",
            evidence=["source 1", "source 2"],
            confidence=0.8,
            safety_flags=[],
        )
    ]

    status, provider, text, reason, _redaction_meta = select_publish_text(judgment, original_drafts, ["openai/gpt-4o"])

    # Should be blocked by long quote validation
    assert status != "published"


def test_fallback_to_safe_defaults():
    """Test that system falls back to safe defaults when things go wrong."""

    # Test with None values and empty data
    with patch("src.artifacts.get_git_sha", return_value="unknown"):
        with patch("src.artifacts.get_sdk_version", return_value="unknown"):
            artifact = create_run_artifact(
                task="",  # Empty task
                max_tokens=0,  # Invalid max_tokens
                temperature=-1,  # Invalid temperature
                trace_name="",  # Empty trace name
                drafts=[],
                judgment=Judgment(ranked=[], winner_provider=""),
                status="none",
                provider="",
                text="",
                allowed_models=[],
                start_time=0,
                model_usage=None,  # No model usage data
            )

            # Should still create valid artifact structure
            assert artifact["provenance"]["git_sha"] == "unknown"
            assert artifact["provenance"]["sdk_version"] == "unknown"
            assert artifact["provenance"]["model_usage"] == {}
            assert artifact["provenance"]["estimated_costs"] == {}


@pytest.mark.bizlogic_asserts  # Sprint 52: Citation disqualification logic failing
def test_citation_disqualification_logic():
    """Test the citation disqualification logic in judge_drafts."""

    async def test_citation_disqualification():
        # Create drafts with insufficient citations
        insufficient_draft = Draft(
            provider="openai/gpt-4o",
            answer="Response with only one citation",
            evidence=["single source"],  # Only 1, need 3
            confidence=0.8,
            safety_flags=[],
        )

        sufficient_draft = Draft(
            provider="anthropic/claude",
            answer="Response with sufficient citations",
            evidence=["source 1", "source 2", "source 3", "source 4"],  # 4 citations
            confidence=0.9,
            safety_flags=[],
        )

        drafts = [insufficient_draft, sufficient_draft]

        # Mock the judge agent to return reasonable scores
        with patch("src.judge.Agent") as MockAgent:
            mock_agent_instance = Mock()
            mock_response = Mock()
            mock_response.last_message.return_value = json.dumps(
                {
                    "evaluations": [
                        {
                            "draft_index": 0,
                            "score": 7.0,
                            "reasons": "Good response",
                            "subscores": {"task_fit": 3, "support": 3, "clarity": 1},
                        },
                        {
                            "draft_index": 1,
                            "score": 8.0,
                            "reasons": "Better response",
                            "subscores": {"task_fit": 4, "support": 3, "clarity": 1},
                        },
                    ]
                }
            )
            mock_agent_instance.run.return_value = mock_response
            MockAgent.return_value = mock_agent_instance

            judgment = await judge_drafts("Test task", drafts, require_citations=3)

            # First draft should be disqualified (score 0)
            # Second draft should remain with original score
            disqualified = [d for d in judgment.ranked if d.score == 0.0]
            qualified = [d for d in judgment.ranked if d.score > 0.0]

            assert len(disqualified) == 1
            assert disqualified[0].provider == "openai/gpt-4o"
            assert "DISQUALIFIED" in disqualified[0].reasons

            assert len(qualified) == 1
            assert qualified[0].provider == "anthropic/claude"

    # Run the async test
    import asyncio

    asyncio.run(test_citation_disqualification())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
