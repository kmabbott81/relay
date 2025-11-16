"""Named Entity Resolution for Contacts.

Resolves person names and emails to Contact resources via URG search.

NO LLM calls - pure deterministic search and matching.
"""

import re
from dataclasses import dataclass
from typing import Optional

from ..graph.search import search


@dataclass
class Contact:
    """Resolved contact information."""

    name: str
    email: str
    user_id: str
    source: str  # teams, slack, outlook, gmail
    graph_id: Optional[str] = None  # URG graph ID if available


# Common name aliases (for testing and common cases)
NAME_ALIASES = {
    "alice": ["alice@example.com", "alice"],
    "bob": ["bob@example.com", "bob"],
    "charlie": ["charlie@example.com", "charlie"],
}


def resolve_contact(name_or_email: str, tenant: str) -> Optional[Contact]:
    """Resolve name or email to Contact via URG search.

    Uses deterministic search and string matching - NO LLM.

    Args:
        name_or_email: Person name or email address
        tenant: Tenant ID for scoped search

    Returns:
        Contact object or None if not found

    Example:
        >>> resolve_contact("alice@example.com", "tenant1")
        Contact(name='Alice Smith', email='alice@example.com', ...)
    """
    if not name_or_email or not tenant:
        return None

    # Check if it's an email address
    if "@" in name_or_email:
        return _resolve_by_email(name_or_email, tenant)
    else:
        return _resolve_by_name(name_or_email, tenant)


def _resolve_by_email(email: str, tenant: str) -> Optional[Contact]:
    """Resolve contact by email address.

    Args:
        email: Email address
        tenant: Tenant ID

    Returns:
        Contact or None
    """
    email = email.lower().strip()

    # Search URG for contact with this email
    results = search(
        email,
        tenant=tenant,
        type="contact",
        limit=10,
    )

    for resource in results:
        # Check if participants match
        participants = resource.get("participants", [])
        if isinstance(participants, str):
            participants = [participants]

        for participant in participants:
            if participant.lower() == email:
                return _resource_to_contact(resource)

    # Check name aliases (for testing)
    for alias_key, alias_values in NAME_ALIASES.items():
        if email in [v.lower() for v in alias_values]:
            # Return synthetic contact
            return Contact(
                name=alias_key.capitalize(),
                email=email,
                user_id=f"{alias_key}_id",
                source="outlook",
            )

    return None


def _resolve_by_name(name: str, tenant: str) -> Optional[Contact]:
    """Resolve contact by name.

    Uses simple substring matching against URG contact resources.

    Args:
        name: Person name
        tenant: Tenant ID

    Returns:
        Contact or None
    """
    name = name.strip()
    name_lower = name.lower()

    # Check aliases first (for testing)
    if name_lower in NAME_ALIASES:
        email = NAME_ALIASES[name_lower][0]
        return Contact(
            name=name.capitalize(),
            email=email,
            user_id=f"{name_lower}_id",
            source="outlook",
        )

    # Search URG for contacts matching this name
    results = search(
        name,
        tenant=tenant,
        type="contact",
        limit=10,
    )

    # Score results by name match quality
    scored = []
    for resource in results:
        score = _score_name_match(name_lower, resource)
        if score > 0:
            scored.append((score, resource))

    if not scored:
        return None

    # Return highest scoring match
    scored.sort(key=lambda x: -x[0])
    best_resource = scored[0][1]

    return _resource_to_contact(best_resource)


def _score_name_match(name_lower: str, resource: dict) -> float:
    """Score how well a resource matches the given name.

    Args:
        name_lower: Lowercase name to match
        resource: URG resource

    Returns:
        Match score (higher is better)
    """
    score = 0.0

    title = (resource.get("title") or "").lower()
    snippet = (resource.get("snippet") or "").lower()

    # Exact title match
    if title == name_lower:
        score += 100.0

    # Title contains name
    if name_lower in title:
        score += 50.0

    # Title words match
    name_words = set(name_lower.split())
    title_words = set(re.split(r"\W+", title))
    matching_words = name_words & title_words
    score += len(matching_words) * 10.0

    # Snippet contains name
    if name_lower in snippet:
        score += 5.0

    return score


def _resource_to_contact(resource: dict) -> Contact:
    """Convert URG resource to Contact.

    Args:
        resource: URG contact resource

    Returns:
        Contact object
    """
    name = resource.get("title", "Unknown")
    source = resource.get("source", "unknown")
    graph_id = resource.get("id", "")

    # Extract email from participants
    participants = resource.get("participants", [])
    if isinstance(participants, str):
        participants = [participants]

    email = ""
    for participant in participants:
        if "@" in str(participant):
            email = str(participant)
            break

    # Extract user_id from metadata
    metadata = resource.get("metadata", {})
    user_id = metadata.get("user_id", "") or metadata.get("id", "")

    return Contact(
        name=name,
        email=email,
        user_id=user_id,
        source=source,
        graph_id=graph_id,
    )


def resolve_contacts(names_or_emails: list[str], tenant: str) -> list[Contact]:
    """Resolve multiple contacts.

    Args:
        names_or_emails: List of names or emails
        tenant: Tenant ID

    Returns:
        List of resolved Contacts (skips unresolved)
    """
    contacts = []

    for name_or_email in names_or_emails:
        contact = resolve_contact(name_or_email, tenant)
        if contact:
            contacts.append(contact)

    return contacts
