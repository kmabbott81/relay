"""Redaction system for secrets and PII sanitation."""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RedactionMatch:
    """A match found by redaction scanning."""

    type: str
    start: int
    end: int
    preview: str
    rule_name: str


@dataclass
class RedactionEvent:
    """Summary of redactions applied."""

    type: str
    count: int
    rule_name: str


class RedactionEngine:
    """Engine for detecting and redacting sensitive information."""

    def __init__(self, rules_path: str = None):
        """Initialize redaction engine with rules."""
        self.rules: list[dict[str, Any]] = []
        self.strategies: dict[str, dict[str, Any]] = {}
        self.default_strategy: str = "label"

        # Load rules
        if rules_path:
            self.load_rules(rules_path)
        else:
            self.load_default_rules()

    def load_rules(self, rules_path: str):
        """Load redaction rules from JSON file."""
        try:
            with open(rules_path, encoding="utf-8") as f:
                config = json.load(f)

            self.rules = config.get("rules", [])
            self.strategies = config.get("strategies", {})
            self.default_strategy = config.get("default_strategy", "label")

            logger.info(f"Loaded {len(self.rules)} redaction rules from {rules_path}")

        except Exception as e:
            logger.error(f"Error loading redaction rules from {rules_path}: {e}")
            self.load_default_rules()

    def load_default_rules(self):
        """Load default built-in rules."""
        default_config_path = Path(__file__).parent.parent / "config" / "redaction_rules.json"
        if default_config_path.exists():
            self.load_rules(str(default_config_path))
        else:
            # Minimal fallback rules
            self.rules = [
                {
                    "name": "api_key_generic",
                    "pattern": "sk-[a-zA-Z0-9]{20,}",
                    "type": "api_key",
                    "description": "Generic API keys starting with sk-",
                },
                {
                    "name": "email",
                    "pattern": "\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}\\b",
                    "type": "email",
                    "description": "Email addresses",
                },
            ]
            self.strategies = {"label": {"replacement": "[REDACTED:{type}]"}}
            self.default_strategy = "label"

    def find_redactions(self, text: str) -> list[RedactionMatch]:
        """
        Find all redaction matches in text.

        Args:
            text: Text to scan for sensitive information

        Returns:
            List of redaction matches
        """
        if not text:
            return []

        matches = []

        for rule in self.rules:
            try:
                pattern = rule["pattern"]
                rule_type = rule["type"]
                rule_name = rule["name"]

                # Find all matches for this rule
                for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
                    start, end = match.span()
                    matched_text = text[start:end]

                    # Create preview (first few chars)
                    preview = matched_text[:10] + "..." if len(matched_text) > 10 else matched_text

                    # Special validation for credit cards (Luhn check)
                    if rule_type == "credit_card":
                        if not self._validate_credit_card(matched_text):
                            continue

                    matches.append(
                        RedactionMatch(type=rule_type, start=start, end=end, preview=preview, rule_name=rule_name)
                    )

            except Exception as e:
                logger.warning(f"Error processing rule {rule.get('name', 'unknown')}: {e}")

        # Sort matches by position
        matches.sort(key=lambda x: x.start)
        return matches

    def _validate_credit_card(self, number: str) -> bool:
        """Validate credit card number using Luhn algorithm."""
        # Remove any spaces or dashes
        number = re.sub(r"[\s-]", "", number)

        if not number.isdigit() or len(number) < 13 or len(number) > 19:
            return False

        # Luhn algorithm
        def luhn_check(card_num):
            def digits_of(n):
                return [int(d) for d in str(n)]

            digits = digits_of(card_num)
            odd_digits = digits[-1::-2]
            even_digits = digits[-2::-2]
            checksum = sum(odd_digits)
            for d in even_digits:
                checksum += sum(digits_of(d * 2))
            return checksum % 10 == 0

        return luhn_check(number)

    def apply_redactions(self, text: str, strategy: str = None) -> tuple[str, list[RedactionEvent]]:
        """
        Apply redactions to text.

        Args:
            text: Text to redact
            strategy: Redaction strategy to use (default: configured default)

        Returns:
            Tuple of (redacted_text, redaction_events)
        """
        if not text:
            return text, []

        # Find all matches
        matches = self.find_redactions(text)
        if not matches:
            return text, []

        # Use specified strategy or default
        if not strategy:
            strategy = self.default_strategy

        # Apply redactions in reverse order to preserve positions
        redacted_text = text
        events_counter = {}

        for match in reversed(matches):
            # Apply redaction based on strategy
            replacement = self._get_replacement(match, strategy)

            # Replace the text
            redacted_text = redacted_text[: match.start] + replacement + redacted_text[match.end :]

            # Count events
            key = (match.type, match.rule_name)
            events_counter[key] = events_counter.get(key, 0) + 1

        # Convert counter to events list
        events = [
            RedactionEvent(type=type_name, count=count, rule_name=rule_name)
            for (type_name, rule_name), count in events_counter.items()
        ]

        return redacted_text, events

    def _get_replacement(self, match: RedactionMatch, strategy: str) -> str:
        """Get replacement text for a match based on strategy."""
        strategy_config = self.strategies.get(strategy, {"replacement": "[REDACTED:{type}]"})

        if strategy == "mask":
            # Replace with asterisk characters (Windows compatible)
            return "*" * min(len(match.preview), 8)

        elif strategy == "partial":
            # Show first/last chars with middle redacted
            original = match.preview
            show_chars = strategy_config.get("show_chars", 2)

            if len(original) <= show_chars * 2:
                return "[REDACTED]"
            else:
                return original[:show_chars] + "***" + original[-show_chars:]

        else:  # label strategy (default)
            replacement_template = strategy_config.get("replacement", "[REDACTED:{type}]")
            return replacement_template.format(type=match.type.upper())


# Global redaction engine instance
_redaction_engine = None


def get_redaction_engine(rules_path: str = None) -> RedactionEngine:
    """Get or create global redaction engine instance."""
    global _redaction_engine
    if _redaction_engine is None or rules_path:
        _redaction_engine = RedactionEngine(rules_path)
    return _redaction_engine


def find_redactions(text: str, rules_path: str = None) -> list[RedactionMatch]:
    """Find redactions in text using global engine."""
    engine = get_redaction_engine(rules_path)
    return engine.find_redactions(text)


def apply_redactions(text: str, strategy: str = "label", rules_path: str = None) -> tuple[str, list[RedactionEvent]]:
    """Apply redactions to text using global engine."""
    engine = get_redaction_engine(rules_path)
    return engine.apply_redactions(text, strategy)


if __name__ == "__main__":
    # Test redaction system
    test_text = """
    Here are some sensitive items:
    - API Key: sk-1234567890abcdefghijklmnopqrstuvwxyz123456789012
    - Email: user@example.com
    - Phone: (555) 123-4567
    - Credit Card: 4111111111111111
    - AWS Key: AKIAIOSFODNN7EXAMPLE
    - IP: 192.168.1.1
    - URL: https://api.example.com/secret
    """

    print("Original text:")
    print(test_text)

    # Test finding redactions
    matches = find_redactions(test_text)
    print(f"\nFound {len(matches)} redaction matches:")
    for match in matches:
        print(f"  {match.type}: {match.preview} ({match.rule_name})")

    # Test applying redactions
    redacted_text, events = apply_redactions(test_text, strategy="label")
    print("\nRedacted text:")
    print(redacted_text)

    print("\nRedaction events:")
    for event in events:
        print(f"  {event.type}: {event.count} instances ({event.rule_name})")

    # Test mask strategy
    masked_text, _ = apply_redactions(test_text, strategy="mask")
    print("\nMasked text:")
    print(masked_text)
