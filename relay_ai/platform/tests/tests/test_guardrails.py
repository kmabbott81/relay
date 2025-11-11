"""Unit tests for guardrails functionality."""

import pytest

from relay_ai.guardrails import (
    check_long_quote,
    check_safety_flags,
    check_safety_flags_blocking,
    has_long_verbatim_quote,
    run_publish_guardrails,
    validate_draft_content,
    validate_publish_text,
)


def test_check_long_quote():
    """Test long quote detection."""
    # Short quote should pass
    short_text = 'This is a "short quote" that should be fine.'
    assert not check_long_quote(short_text, 75)

    # Long quote should fail
    long_quote = '"' + " ".join(["word"] * 80) + '"'
    long_text = f"This text has a long quote: {long_quote}"
    assert check_long_quote(long_text, 75)

    # Custom limit
    medium_quote = '"' + " ".join(["word"] * 50) + '"'
    medium_text = f"This has a medium quote: {medium_quote}"
    assert not check_long_quote(medium_text, 75)  # Under default limit
    assert check_long_quote(medium_text, 40)  # Over custom limit


def test_check_safety_flags_blocking():
    """Test safety flag blocking detection."""
    # Safe flags
    safe_flags = ["warning", "minor_issue", "advisory"]
    assert not check_safety_flags_blocking(safe_flags)

    # Blocking flags
    blocking_flags = ["hate_speech", "policy_violation"]
    assert check_safety_flags_blocking(blocking_flags)

    # Mixed flags
    mixed_flags = ["warning", "hate_speech", "advisory"]
    assert check_safety_flags_blocking(mixed_flags)

    # Empty flags
    assert not check_safety_flags_blocking([])


def test_run_publish_guardrails_success():
    """Test successful publish guardrails."""
    clean_text = "This is clean, safe content with no issues."
    safe_flags = ["minor_warning"]

    ok, reason = run_publish_guardrails(clean_text, safe_flags)
    assert ok
    assert reason == ""


def test_run_publish_guardrails_safety_failure():
    """Test publish guardrails failing on safety flags."""
    clean_text = "This is clean content but with bad flags."
    bad_flags = ["hate_speech", "policy_violation"]

    ok, reason = run_publish_guardrails(clean_text, bad_flags)
    assert not ok
    assert "Safety violation" in reason


def test_run_publish_guardrails_long_quote_failure():
    """Test publish guardrails failing on long quotes."""
    long_quote = '"' + " ".join(["word"] * 80) + '"'
    text_with_long_quote = f"This text has problems: {long_quote}"
    safe_flags = []

    ok, reason = run_publish_guardrails(text_with_long_quote, safe_flags)
    assert not ok
    assert "verbatim quotes" in reason or "copyright" in reason


def test_run_publish_guardrails_empty_content():
    """Test publish guardrails failing on empty content."""
    empty_text = ""
    safe_flags = []

    ok, reason = run_publish_guardrails(empty_text, safe_flags)
    assert not ok
    assert "Empty content" in reason or "empty text" in reason


def test_run_publish_guardrails_refusal_pattern():
    """Test publish guardrails detecting refusal patterns."""
    refusal_text = "I cannot provide information about this topic due to safety concerns."
    safe_flags = []

    ok, reason = run_publish_guardrails(refusal_text, safe_flags)
    assert not ok
    assert "refusal" in reason or "disclaimer" in reason


def test_has_long_verbatim_quote_patterns():
    """Test different quote pattern detection."""
    # Double quotes
    double_quote_text = 'He said "' + " ".join(["word"] * 80) + '"'
    assert has_long_verbatim_quote(double_quote_text, 75)

    # Single quotes
    single_quote_text = "She said '" + " ".join(["word"] * 80) + "'"
    assert has_long_verbatim_quote(single_quote_text, 75)

    # Code blocks
    code_block = "```" + " ".join(["code"] * 80) + "```"
    assert has_long_verbatim_quote(code_block, 75)

    # Block quotes
    block_quote = "> " + " ".join(["quote"] * 80)
    assert has_long_verbatim_quote(block_quote, 75)


def test_check_safety_flags_comprehensive():
    """Test comprehensive safety flag checking."""
    # All critical flags should be caught
    critical_flags = [
        "policy_violation",
        "hate_speech",
        "harassment",
        "violence",
        "illegal_content",
        "privacy_violation",
        "copyright_violation",
    ]

    for flag in critical_flags:
        blocking = check_safety_flags([flag])
        assert len(blocking) == 1
        assert blocking[0] == flag

    # Case insensitive
    blocking = check_safety_flags(["HATE_SPEECH"])
    assert len(blocking) == 1

    # Non-blocking flags
    safe_flags = ["warning", "advisory", "minor_issue", "informational"]
    blocking = check_safety_flags(safe_flags)
    assert len(blocking) == 0


def test_validate_draft_content_comprehensive():
    """Test comprehensive draft content validation."""
    # Valid content
    valid_text = "This is good, clean content with proper sources."
    valid_flags = ["minor_warning"]
    is_valid, reason = validate_draft_content(valid_text, valid_flags)
    assert is_valid
    assert reason == ""

    # Invalid - empty
    is_valid, reason = validate_draft_content("", [])
    assert not is_valid
    assert "Empty content" in reason

    # Invalid - safety flags
    is_valid, reason = validate_draft_content("Good content", ["hate_speech"])
    assert not is_valid
    assert "Safety violation" in reason

    # Invalid - long quote
    long_quote_text = 'Good text with "' + " ".join(["word"] * 80) + '"'
    is_valid, reason = validate_draft_content(long_quote_text, [])
    assert not is_valid
    assert "long verbatim quotes" in reason

    # Invalid - refusal pattern
    refusal_text = "I'm sorry but I cannot provide that information."
    is_valid, reason = validate_draft_content(refusal_text, [])
    assert not is_valid
    assert "refusal" in reason


def test_validate_publish_text_edge_cases():
    """Test edge cases for publish text validation."""
    # None input
    with pytest.raises(ValueError, match="empty text"):
        validate_publish_text(None)

    # Whitespace only
    with pytest.raises(ValueError, match="empty text"):
        validate_publish_text("   \n\t   ")

    # Very long quote
    very_long_quote = '"' + " ".join(["word"] * 100) + '"'
    with pytest.raises(ValueError, match="verbatim quotes"):
        validate_publish_text(very_long_quote)

    # Valid text should not raise
    try:
        validate_publish_text("This is valid content without issues.")
    except ValueError:
        pytest.fail("Valid text should not raise ValueError")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
