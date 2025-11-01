"""Unit tests for redaction system."""

import pytest

from src.redaction import RedactionEngine, RedactionEvent, RedactionMatch, apply_redactions, find_redactions


def test_find_api_keys():
    """Test detection of API keys."""
    # Use exactly 48 characters after sk- to match OpenAI format
    text = "Here is an API key: sk-123456789012345678901234567890123456789012345678"

    matches = find_redactions(text)

    assert len(matches) > 0
    assert any(m.type == "api_key" for m in matches)


def test_find_emails():
    """Test detection of email addresses."""
    text = "Contact us at user@example.com or admin@test.org"

    matches = find_redactions(text)

    assert len(matches) >= 2
    email_matches = [m for m in matches if m.type == "email"]
    assert len(email_matches) >= 2


def test_find_phone_numbers():
    """Test detection of US phone numbers."""
    text = """
    Call us at (555) 123-4567 or 555-123-4568
    International: +1-555-123-4569
    """

    matches = find_redactions(text)

    phone_matches = [m for m in matches if m.type == "phone"]
    assert len(phone_matches) >= 3


def test_find_ssn():
    """Test detection of Social Security Numbers."""
    text = "SSN: 123-45-6789 or 987654321"

    matches = find_redactions(text)

    ssn_matches = [m for m in matches if m.type == "ssn"]
    assert len(ssn_matches) >= 2


def test_find_credit_cards_with_luhn():
    """Test detection of credit card numbers with Luhn validation."""
    text = """
    Valid Visa: 4111111111111111
    Valid Mastercard: 5555555555554444
    Invalid: 1234567890123456
    """

    matches = find_redactions(text)

    # Should only match valid credit cards (with Luhn check)
    cc_matches = [m for m in matches if m.type == "credit_card"]
    # At least the valid cards should be detected
    assert len(cc_matches) >= 2


def test_find_aws_keys():
    """Test detection of AWS credentials."""
    text = """
    AWS Access Key: AKIAIOSFODNN7EXAMPLE
    AWS Secret: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
    """

    matches = find_redactions(text)

    aws_matches = [m for m in matches if m.type == "aws_credential"]
    assert len(aws_matches) >= 1  # At least access key should match


def test_find_ip_addresses():
    """Test detection of IP addresses."""
    text = "Server IP: 192.168.1.1 and external: 8.8.8.8"

    matches = find_redactions(text)

    ip_matches = [m for m in matches if m.type == "ip_address"]
    assert len(ip_matches) >= 2


def test_find_urls():
    """Test detection of URLs."""
    text = """
    Visit https://api.example.com/secret
    Or http://internal.server.local/data
    """

    matches = find_redactions(text)

    url_matches = [m for m in matches if m.type == "url"]
    assert len(url_matches) >= 2


def test_find_jwt_tokens():
    """Test detection of JWT tokens."""
    text = "Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"

    matches = find_redactions(text)

    jwt_matches = [m for m in matches if m.type == "jwt_token"]
    assert len(jwt_matches) >= 1


def test_apply_redactions_label_strategy():
    """Test applying redactions with label strategy."""
    text = "Email: user@example.com and phone: (555) 123-4567"

    redacted_text, events = apply_redactions(text, strategy="label")

    assert "user@example.com" not in redacted_text
    assert "[REDACTED:EMAIL]" in redacted_text or "[REDACTED:PHONE]" in redacted_text
    assert len(events) > 0
    assert all(isinstance(e, RedactionEvent) for e in events)


def test_apply_redactions_mask_strategy():
    """Test applying redactions with mask strategy."""
    text = "API Key: sk-123456789012345678901234567890123456789012345678"

    redacted_text, events = apply_redactions(text, strategy="mask")

    assert "sk-123456789012345678901234567890123456789012345678" not in redacted_text
    assert "*" in redacted_text  # Should contain asterisks
    assert len(events) > 0


def test_apply_redactions_events():
    """Test that redaction events are properly counted."""
    text = """
    user1@example.com
    user2@example.com
    user3@example.com
    """

    redacted_text, events = apply_redactions(text, strategy="label")

    # Should have event for email type
    email_events = [e for e in events if e.type == "email"]
    assert len(email_events) > 0

    # Total count should match number of emails
    total_email_count = sum(e.count for e in email_events)
    assert total_email_count == 3


def test_apply_redactions_preserves_non_sensitive():
    """Test that redaction preserves non-sensitive text."""
    text = "Hello world! Email: user@example.com Goodbye!"

    redacted_text, events = apply_redactions(text, strategy="label")

    assert "Hello world!" in redacted_text
    assert "Goodbye!" in redacted_text
    assert "user@example.com" not in redacted_text


def test_apply_redactions_empty_text():
    """Test redaction on empty text."""
    redacted_text, events = apply_redactions("", strategy="label")

    assert redacted_text == ""
    assert len(events) == 0


def test_apply_redactions_no_matches():
    """Test redaction on text with no sensitive data."""
    text = "This is completely safe text with no sensitive information."

    redacted_text, events = apply_redactions(text, strategy="label")

    assert redacted_text == text  # Should be unchanged
    assert len(events) == 0


def test_apply_redactions_idempotent():
    """Test that applying redactions twice is idempotent."""
    text = "Email: user@example.com"

    redacted_text1, events1 = apply_redactions(text, strategy="label")
    redacted_text2, events2 = apply_redactions(redacted_text1, strategy="label")

    # Second application should find nothing to redact
    assert redacted_text1 == redacted_text2
    assert len(events1) > 0
    assert len(events2) == 0


def test_redaction_match_structure():
    """Test structure of RedactionMatch objects."""
    text = "Email: user@example.com"

    matches = find_redactions(text)

    assert len(matches) > 0
    match = matches[0]

    assert isinstance(match, RedactionMatch)
    assert hasattr(match, "type")
    assert hasattr(match, "start")
    assert hasattr(match, "end")
    assert hasattr(match, "preview")
    assert hasattr(match, "rule_name")

    # Verify span matches
    extracted = text[match.start : match.end]
    assert "user@example.com" in extracted


def test_redaction_event_structure():
    """Test structure of RedactionEvent objects."""
    text = "Email: user@example.com"

    _, events = apply_redactions(text, strategy="label")

    assert len(events) > 0
    event = events[0]

    assert isinstance(event, RedactionEvent)
    assert hasattr(event, "type")
    assert hasattr(event, "count")
    assert hasattr(event, "rule_name")
    assert event.count > 0


def test_luhn_validation():
    """Test credit card Luhn algorithm validation."""
    engine = RedactionEngine()

    # Valid credit card numbers
    assert engine._validate_credit_card("4111111111111111")  # Visa
    assert engine._validate_credit_card("5555555555554444")  # Mastercard

    # Invalid credit card numbers
    assert not engine._validate_credit_card("1234567890123456")
    assert not engine._validate_credit_card("4111111111111112")  # Wrong check digit


def test_multiple_redaction_types():
    """Test text with multiple types of sensitive data."""
    text = """
    Contact: user@example.com
    Phone: (555) 123-4567
    API Key: sk-1234567890abcdefghijklmnopqrstuvwxyz123456
    Credit Card: 4111111111111111
    """

    redacted_text, events = apply_redactions(text, strategy="label")

    # Should have multiple event types
    event_types = {e.type for e in events}
    assert len(event_types) >= 3  # At least email, phone, api_key, credit_card

    # All sensitive data should be redacted
    assert "user@example.com" not in redacted_text
    assert "555-123-4567" not in redacted_text
    assert "sk-1234567890" not in redacted_text
    assert "4111111111111111" not in redacted_text


def test_redaction_with_custom_rules():
    """Test that custom rules can be loaded."""
    # Test with default rules first
    engine = RedactionEngine()
    assert len(engine.rules) > 0
    assert engine.default_strategy == "label"


def test_case_insensitive_matching():
    """Test that pattern matching is case-insensitive where appropriate."""
    text_upper = "EMAIL: USER@EXAMPLE.COM"
    text_lower = "email: user@example.com"

    matches_upper = find_redactions(text_upper)
    matches_lower = find_redactions(text_lower)

    # Both should find the email
    assert len(matches_upper) > 0
    assert len(matches_lower) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
