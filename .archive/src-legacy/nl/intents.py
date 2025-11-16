"""Intent Parser for Natural Language Commands.

Pure deterministic regex-based parsing - NO LLM calls.

Extracts:
- Verbs (email, message, forward, reply, schedule, create, update, delete, find, list)
- Targets (person names, channels, teams)
- Artifacts (messages, files, pages, events)
- Constraints (source, time, labels, folders)
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Intent:
    """Parsed intent from natural language command."""

    verb: str  # Primary action verb
    targets: list[str] = field(default_factory=list)  # People, channels, teams
    artifacts: list[str] = field(default_factory=list)  # Things to act on
    constraints: dict = field(default_factory=dict)  # Filters and metadata
    original_command: str = ""  # Original command text

    def __repr__(self) -> str:
        return (
            f"Intent(verb={self.verb!r}, targets={self.targets}, "
            f"artifacts={self.artifacts}, constraints={self.constraints})"
        )


# Verb patterns - deterministic regex matching
VERB_PATTERNS = {
    "email": [
        r"\bemail\b",
        r"\bsend\s+(?:an?\s+)?email\b",
    ],
    "message": [
        r"\bmessage\b",
        r"\bchat\b",
        r"\bping\b",
        r"\bsend\s+(?:a\s+)?message\b",
        r"\bDM\b",
    ],
    "forward": [
        r"\bforward\b",
        r"\bshare\s+.*?\s+with\b",
    ],
    "reply": [
        r"\breply\b",
        r"\brespond\b",
        r"\banswer\b",
        r"\breply\s+to\b",
    ],
    "schedule": [
        r"\bschedule\b",
        r"\bbook\b",
        r"\bset\s+up\s+(?:a\s+)?meeting\b",
        r"\bcreate\s+(?:a\s+)?(?:meeting|event|appointment)\b",
    ],
    "create": [
        r"\bcreate\b",
        r"\bmake\b",
        r"\bnew\b",
        r"\badd\b",
    ],
    "update": [
        r"\bupdate\b",
        r"\bedit\b",
        r"\bchange\b",
        r"\bmodify\b",
    ],
    "delete": [
        r"\bdelete\b",
        r"\bremove\b",
        r"\btrash\b",
        r"\barchive\b",
    ],
    "find": [
        r"\bfind\b",
        r"\bsearch\b",
        r"\blook\s+for\b",
        r"\bshow\s+me\b",
        r"\bget\b",
    ],
    "list": [
        r"\blist\b",
        r"\bshow\s+all\b",
        r"\bget\s+all\b",
    ],
}


# Source connectors
SOURCE_PATTERNS = {
    "teams": [r"\bteams\b", r"\bmicrosoft\s+teams\b"],
    "slack": [r"\bslack\b"],
    "outlook": [r"\boutlook\b", r"\boffice\s+365\b", r"\bo365\b"],
    "gmail": [r"\bgmail\b", r"\bgoogle\s+mail\b"],
    "notion": [r"\bnotion\b"],
}


# Time constraints
TIME_PATTERNS = {
    "today": [r"\btoday\b"],
    "yesterday": [r"\byesterday\b"],
    "this_week": [r"\bthis\s+week\b"],
    "last_week": [r"\blast\s+week\b"],
    "this_month": [r"\bthis\s+month\b"],
    "last_month": [r"\blast\s+month\b"],
}


# Artifact patterns
ARTIFACT_PATTERNS = {
    "message": [r"\bmessage\b", r"\bemail\b", r"\bmail\b", r"\bchat\b"],
    "file": [r"\bfile\b", r"\bdocument\b", r"\bspreadsheet\b", r"\bpdf\b"],
    "page": [r"\bpage\b", r"\bdoc\b", r"\bnote\b"],
    "event": [r"\bevent\b", r"\bmeeting\b", r"\bappointment\b", r"\bcalendar\b"],
    "contact": [r"\bcontact\b", r"\bperson\b", r"\buser\b"],
}


def parse_intent(command: str) -> Intent:
    """Parse natural language command into structured Intent.

    Pure deterministic parsing - NO LLM calls.

    Args:
        command: Natural language command string

    Returns:
        Intent object with parsed verb, targets, artifacts, constraints

    Example:
        >>> parse_intent("Email the Q4 budget to alice@example.com")
        Intent(verb='email', targets=['alice@example.com'], artifacts=['Q4 budget'], ...)
    """
    if not command or not command.strip():
        return Intent(verb="unknown", original_command=command)

    command_lower = command.lower()

    # 1. Extract verb (first matching verb wins)
    verb = _extract_verb(command_lower)

    intent = Intent(verb=verb, original_command=command)

    # 2. Extract targets (people, emails, channels)
    intent.targets = _extract_targets(command)

    # 3. Extract artifacts
    intent.artifacts = _extract_artifacts(command)

    # 4. Extract constraints
    intent.constraints = _extract_constraints(command, command_lower)

    return intent


def _extract_verb(command_lower: str) -> str:
    """Extract primary action verb from command.

    Args:
        command_lower: Lowercase command text

    Returns:
        Verb name or 'unknown'
    """
    # Priority order: specific verbs first, then general
    # Note: delete/update/create must come before message to avoid false matches
    verb_priority = [
        "reply",
        "forward",
        "schedule",
        "delete",
        "update",
        "create",
        "email",
        "message",
        "find",
        "list",
    ]

    for verb in verb_priority:
        patterns = VERB_PATTERNS.get(verb, [])
        for pattern in patterns:
            if re.search(pattern, command_lower):
                return verb

    return "unknown"


def _extract_targets(command: str) -> list[str]:
    """Extract targets (people, emails, channels) from command.

    Args:
        command: Command text

    Returns:
        List of target strings
    """
    targets = []

    # Extract email addresses
    email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    emails = re.findall(email_pattern, command)
    targets.extend(emails)

    # Extract names after common patterns
    # Pattern: "to [Name]", "with [Name]", "from [Name]", "and [Name]", "message [Name]"
    name_patterns = [
        (r"\bto\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", 0),  # (pattern, flags)
        (r"\bwith\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", 0),
        (r"\bfrom\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", 0),
        (r"\band\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", 0),
        # "message Alice" - stop at prepositions like "about"
        (r"(?i)\b(?:message|email|ping)\s+([A-Z][a-z]+)(?:\s+(?:about|to|with|from|in|on|at)\b|\s*$)", re.IGNORECASE),
        (r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)'s\s+message", 0),
    ]

    for pattern, flags in name_patterns:
        if flags:
            matches = re.findall(pattern, command, flags)
        else:
            matches = re.findall(pattern, command)
        targets.extend(matches)

    # Extract team names
    # Pattern: "the [Name] team"
    team_pattern = r"\bthe\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+team\b"
    teams = re.findall(team_pattern, command)
    targets.extend([f"{t} team" for t in teams])

    # Extract channel names
    # Pattern: "#channel" or "the [Name] channel"
    channel_patterns = [
        r"#([a-z0-9_-]+)",
        r"\bthe\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+channel\b",
    ]

    for pattern in channel_patterns:
        matches = re.findall(pattern, command)
        targets.extend(matches)

    # Deduplicate while preserving order
    seen = set()
    unique_targets = []
    for target in targets:
        target_lower = target.lower()
        if target_lower not in seen:
            seen.add(target_lower)
            unique_targets.append(target)

    return unique_targets


def _extract_artifacts(command: str) -> list[str]:
    """Extract artifacts (things to act on) from command.

    Extracts quoted strings and phrases like "the [thing]".

    Args:
        command: Command text

    Returns:
        List of artifact strings
    """
    artifacts = []

    # Extract quoted strings
    quoted = re.findall(r'"([^"]+)"', command)
    artifacts.extend(quoted)

    # Extract phrases like "the [artifact]"
    # Pattern: "the [words]" but not "the [person] team/channel"
    the_pattern = r"\bthe\s+([a-zA-Z0-9\s]+?)(?:\s+(?:to|with|from|in|about)\b|$)"
    the_matches = re.findall(the_pattern, command)

    for match in the_matches:
        match = match.strip()
        # Filter out team/channel references
        if not match.lower().endswith(("team", "channel")):
            # Limit length
            if len(match) < 50:
                artifacts.append(match)

    # Extract phrases like "about [topic]" or "for [topic]"
    about_pattern = r"\babout\s+([a-zA-Z0-9\s]+?)(?:\s+(?:to|with|from|in)\b|$)"
    about_matches = re.findall(about_pattern, command)
    for match in about_matches:
        match = match.strip()
        if len(match) < 50:
            artifacts.append(match)

    # Extract phrases like "for [topic]"
    for_pattern = r"\bfor\s+([a-zA-Z0-9\s]+?)(?:\s*$)"
    for_matches = re.findall(for_pattern, command)
    for match in for_matches:
        match = match.strip()
        if len(match) < 50 and not match.lower().startswith(("a ", "an ", "the ")):
            artifacts.append(match)

    # Deduplicate while preserving order
    seen = set()
    unique_artifacts = []
    for artifact in artifacts:
        artifact_lower = artifact.lower()
        if artifact_lower not in seen:
            seen.add(artifact_lower)
            unique_artifacts.append(artifact)

    return unique_artifacts


def _extract_constraints(command: str, command_lower: str) -> dict:
    """Extract constraints (source, time, labels) from command.

    Args:
        command_lower: Lowercase command text

    Returns:
        Dictionary of constraints
    """
    constraints = {}

    # Extract source connector
    for source, patterns in SOURCE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, command_lower):
                constraints["source"] = source
                break
        if "source" in constraints:
            break

    # Extract time constraint
    for time_key, patterns in TIME_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, command_lower):
                constraints["time"] = time_key
                break
        if "time" in constraints:
            break

    # Extract label/tag
    label_pattern = r"\bwith\s+(?:label|tag)\s+['\"]?([a-zA-Z0-9_-]+)['\"]?"
    label_match = re.search(label_pattern, command_lower)
    if label_match:
        constraints["label"] = label_match.group(1)

    # Extract folder (preserve case)
    folder_pattern = r"\bin\s+(?:the\s+)?([A-Za-z0-9\s]+?)\s+folder"
    folder_match = re.search(folder_pattern, command, re.IGNORECASE)
    if folder_match:
        constraints["folder"] = folder_match.group(1).strip()

    return constraints


def validate_intent(intent: Intent) -> tuple[bool, Optional[str]]:
    """Validate parsed intent has required components.

    Args:
        intent: Parsed Intent object

    Returns:
        (is_valid, error_message) tuple
    """
    if intent.verb == "unknown":
        return False, "Could not identify action verb in command"

    # Verb-specific validation
    if intent.verb in ["email", "message", "forward"] and not intent.targets:
        return False, f"'{intent.verb}' requires at least one target (person/email/channel)"

    if intent.verb == "reply" and not intent.artifacts:
        # Reply needs context about what to reply to
        # We'll rely on URG search to find "latest message"
        pass

    if intent.verb == "schedule" and not intent.targets:
        return False, "schedule requires participants"

    return True, None
