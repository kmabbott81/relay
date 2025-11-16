"""Guardrails for content validation and safety checks."""

import re


def has_long_verbatim_quote(text: str, limit: int = 75) -> bool:
    """
    Check if text contains verbatim quotes longer than the specified limit.

    Args:
        text: Text to check
        limit: Maximum allowed quote length (default 75 words)

    Returns:
        True if long verbatim quotes are found
    """
    if not text:
        return False

    # Look for quoted text patterns
    quote_patterns = [
        r'"([^"]{100,})"',  # Double quotes with 100+ chars
        r"'([^']{100,})'",  # Single quotes with 100+ chars
        r"```([^`]{100,})```",  # Code blocks with 100+ chars
        r"> ([^\n]{100,})",  # Block quotes with 100+ chars
    ]

    for pattern in quote_patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            # Count words in the match
            word_count = len(match.split())
            if word_count >= limit:
                return True

    return False


def validate_publish_text(text: str) -> None:
    """
    Validate text before publishing.

    Args:
        text: Text to validate

    Raises:
        ValueError: If text fails validation checks
    """
    if not text or not text.strip():
        raise ValueError("Cannot publish empty text")

    if has_long_verbatim_quote(text):
        raise ValueError(
            "Text contains verbatim quotes longer than 75 words. " "Cannot publish due to potential copyright concerns."
        )


def check_safety_flags(safety_flags: list[str]) -> list[str]:
    """
    Analyze safety flags and return blocking issues.

    Args:
        safety_flags: List of safety flags from agents

    Returns:
        List of blocking safety issues
    """
    blocking_flags = []

    critical_flags = {
        "policy_violation",
        "hate_speech",
        "harassment",
        "violence",
        "illegal_content",
        "privacy_violation",
        "copyright_violation",
        "disqualified_citations",
    }

    for flag in safety_flags:
        if flag.lower() in critical_flags:
            blocking_flags.append(flag)

    return blocking_flags


def validate_draft_content(text: str, safety_flags: list[str]) -> tuple[bool, str]:
    """
    Comprehensive validation of draft content.

    Args:
        text: Draft text to validate
        safety_flags: Safety flags from the generating agent

    Returns:
        Tuple of (is_valid, reason_if_invalid)
    """
    if not text or not text.strip():
        return False, "Empty content"

    # Check safety flags
    blocking_flags = check_safety_flags(safety_flags)
    if blocking_flags:
        return False, f"Safety violation: {', '.join(blocking_flags)}"

    # Check for long quotes
    if has_long_verbatim_quote(text):
        return False, "Contains long verbatim quotes"

    # Check for suspicious patterns
    suspicious_patterns = [
        r"I cannot.*provide.*information",  # Refusal patterns
        r"I\'m sorry.*I cannot",
        r"I don\'t have.*access to",
        r"As an AI.*I cannot",
    ]

    for pattern in suspicious_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return False, "Content appears to be a refusal or disclaimer"

    return True, ""


def check_long_quote(text: str, limit: int = 75) -> bool:
    """
    Check if text contains long verbatim quotes.

    Args:
        text: Text to check
        limit: Maximum allowed quote length in words

    Returns:
        True if long quotes found
    """
    return has_long_verbatim_quote(text, limit)


def check_safety_flags_blocking(flags: list[str]) -> bool:
    """
    Check if safety flags contain blocking issues.

    Args:
        flags: List of safety flags

    Returns:
        True if blocking flags found
    """
    blocking_flags = check_safety_flags(flags)
    return len(blocking_flags) > 0


def run_publish_guardrails(text: str, flags: list[str]) -> tuple[bool, str]:
    """
    Run comprehensive publish guardrails.

    Args:
        text: Text to validate
        flags: Safety flags from agent

    Returns:
        Tuple of (ok, reason)
    """
    # Use existing comprehensive validation
    is_valid, reason = validate_draft_content(text, flags)

    if not is_valid:
        return False, reason

    # Additional publish-specific checks
    try:
        validate_publish_text(text)
        return True, ""
    except ValueError as e:
        return False, str(e)
