"""Unified Resource Graph (URG) Search.

Provides fast search and filter functionality across all indexed resources.
"""

import os
import re
from datetime import datetime
from typing import Optional

from .index import get_index


def _parse_timestamp(ts: str) -> float:
    """Parse ISO timestamp to epoch seconds for sorting.

    Args:
        ts: ISO format timestamp string

    Returns:
        Unix timestamp (epoch seconds), or 0.0 if parsing fails
    """
    if not ts:
        return 0.0
    try:
        # Handle ISO format with Z suffix
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.timestamp()
    except (ValueError, AttributeError):
        return 0.0


def tokenize_query(query: str) -> list[str]:
    """Tokenize search query.

    Args:
        query: Search query string

    Returns:
        List of lowercase tokens
    """
    if not query:
        return []

    # Lowercase and split on non-word characters
    tokens = re.split(r"\W+", query.lower())
    return [t for t in tokens if t]


def search(
    query: str,
    *,
    tenant: str,
    type: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Search URG index with filters.

    Args:
        query: Search query (tokenized and matched against title/snippet/participants)
        tenant: Tenant ID (required for isolation)
        type: Optional resource type filter (message, contact, event, etc.)
        source: Optional source connector filter (teams, outlook, slack, gmail)
        limit: Maximum results to return

    Returns:
        List of matching resources sorted by relevance and timestamp

    Raises:
        ValueError: If tenant not provided
    """
    if not tenant:
        raise ValueError("Tenant is required for search")

    index = get_index()

    # Get max results from env
    max_results = int(os.getenv("URG_MAX_RESULTS", "200"))
    limit = min(limit, max_results)

    # Start with tenant-scoped resources
    candidate_ids = index.tenant_index.get(tenant, set())

    # Apply type filter
    if type:
        type_ids = index.type_index.get(type, set())
        candidate_ids = candidate_ids & type_ids

    # Apply source filter
    if source:
        source_ids = index.source_index.get(source, set())
        candidate_ids = candidate_ids & source_ids

    # If no query, return filtered results sorted by timestamp
    if not query or not query.strip():
        results = []
        for graph_id in candidate_ids:
            if graph_id in index.resources:
                results.append(index.resources[graph_id])

        # Sort deterministically: timestamp DESC, id ASC
        results.sort(
            key=lambda r: (-_parse_timestamp(r.get("timestamp", "")), r.get("id", "")),
        )
        return results[:limit]

    # Tokenize query
    query_tokens = tokenize_query(query)

    if not query_tokens:
        # Empty query after tokenization
        results = []
        for graph_id in candidate_ids:
            if graph_id in index.resources:
                results.append(index.resources[graph_id])

        results.sort(
            key=lambda r: (-_parse_timestamp(r.get("timestamp", "")), r.get("id", "")),
        )
        return results[:limit]

    # Score each candidate resource
    scored_results = []

    for graph_id in candidate_ids:
        if graph_id not in index.resources:
            continue

        resource = index.resources[graph_id]
        score = _score_resource(resource, query_tokens, index)

        if score > 0:
            scored_results.append((score, resource))

    # Sort deterministically: score DESC, timestamp DESC, id ASC
    scored_results.sort(
        key=lambda x: (
            -x[0],  # Higher score first
            -_parse_timestamp(x[1].get("timestamp", "")),  # Newer first
            x[1].get("id", ""),  # Alphabetically by ID as tiebreaker
        ),
    )

    # Extract resources and apply limit
    results = [resource for _, resource in scored_results[:limit]]

    return results


def _score_resource(resource: dict, query_tokens: list[str], index) -> float:
    """Score a resource against query tokens.

    Args:
        resource: Resource to score
        query_tokens: List of query tokens
        index: URG index instance

    Returns:
        Relevance score (higher is better)
    """
    score = 0.0

    # Get resource text for matching
    title = (resource.get("title") or "").lower()
    snippet = (resource.get("snippet") or "").lower()
    participants = resource.get("participants", [])
    if isinstance(participants, str):
        participants = [participants]
    participants_text = " ".join(str(p).lower() for p in participants)

    labels = resource.get("labels", [])
    if isinstance(labels, str):
        labels = [labels]
    labels_text = " ".join(str(label).lower() for label in labels)

    # Combine all text
    full_text = f"{title} {snippet} {participants_text} {labels_text}"

    # Score each query token
    for token in query_tokens:
        # Exact match in title (highest weight)
        if token in title:
            score += 10.0

        # Exact word match in title
        title_words = re.split(r"\W+", title)
        if token in title_words:
            score += 5.0

        # Exact match in snippet
        if token in snippet:
            score += 3.0

        # Match in participants
        if token in participants_text:
            score += 2.0

        # Match in labels
        if token in labels_text:
            score += 2.0

        # Partial match anywhere (lowest weight)
        if token in full_text:
            score += 1.0

    return score


def search_by_type(
    resource_type: str,
    *,
    tenant: str,
    source: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Search resources by type.

    Args:
        resource_type: Type of resource (message, contact, event)
        tenant: Tenant ID (required)
        source: Optional source filter
        limit: Maximum results

    Returns:
        List of matching resources
    """
    return search("", tenant=tenant, type=resource_type, source=source, limit=limit)


def search_by_source(
    source: str,
    *,
    tenant: str,
    type: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Search resources by source connector.

    Args:
        source: Source connector (teams, outlook, slack, gmail)
        tenant: Tenant ID (required)
        type: Optional type filter
        limit: Maximum results

    Returns:
        List of matching resources
    """
    return search("", tenant=tenant, source=source, type=type, limit=limit)


def get_resource_by_id(graph_id: str, *, tenant: str) -> Optional[dict]:
    """Get resource by graph ID.

    Args:
        graph_id: Unique graph ID
        tenant: Tenant ID (required for isolation)

    Returns:
        Resource data or None
    """
    index = get_index()
    return index.get(graph_id, tenant=tenant)


def search_participants(
    participant: str,
    *,
    tenant: str,
    type: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Search resources by participant.

    Args:
        participant: Participant email or name
        tenant: Tenant ID (required)
        type: Optional type filter
        limit: Maximum results

    Returns:
        List of matching resources
    """
    # Use participant as query since it's indexed
    return search(participant, tenant=tenant, type=type, limit=limit)


def search_labels(
    label: str,
    *,
    tenant: str,
    type: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Search resources by label.

    Args:
        label: Label to search for
        tenant: Tenant ID (required)
        type: Optional type filter
        limit: Maximum results

    Returns:
        List of matching resources
    """
    # Use label as query since it's indexed
    return search(label, tenant=tenant, type=type, limit=limit)
