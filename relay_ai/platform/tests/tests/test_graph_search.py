"""Tests for Unified Resource Graph Search."""

import pytest

from relay_ai.graph.index import get_index
from relay_ai.graph.search import search, search_by_source, search_by_type


@pytest.fixture
def index():
    """Populate URG index with sample data."""
    # Use global singleton (isolated by clean_graph_env autouse fixture)
    idx = get_index()

    # Add sample messages
    idx.upsert(
        {
            "id": "msg-1",
            "type": "message",
            "title": "Q4 Planning Meeting",
            "snippet": "Let's discuss the quarterly planning for Q4 2025",
            "timestamp": "2025-01-15T10:00:00Z",
            "participants": ["alice@example.com"],
        },
        source="teams",
        tenant="acme-corp",
    )

    idx.upsert(
        {
            "id": "msg-2",
            "type": "message",
            "title": "Re: Budget Review",
            "snippet": "The budget looks good for approval",
            "timestamp": "2025-01-16T11:00:00Z",
            "participants": ["bob@example.com"],
        },
        source="outlook",
        tenant="acme-corp",
    )

    idx.upsert(
        {
            "id": "msg-3",
            "type": "message",
            "title": "Team standup notes",
            "snippet": "Daily standup summary and action items",
            "timestamp": "2025-01-17T09:00:00Z",
            "participants": ["charlie@example.com"],
        },
        source="slack",
        tenant="acme-corp",
    )

    # Add contacts
    idx.upsert(
        {
            "id": "contact-1",
            "type": "contact",
            "title": "Alice Anderson",
            "snippet": "alice@example.com - 555-1234",
            "participants": ["alice@example.com"],
        },
        source="outlook",
        tenant="acme-corp",
    )

    # Different tenant
    idx.upsert(
        {
            "id": "msg-other",
            "type": "message",
            "title": "Private message",
            "snippet": "This is from another tenant",
        },
        source="teams",
        tenant="other-corp",
    )

    return idx


def test_basic_search(index):
    """Test basic text search."""
    results = search("planning", tenant="acme-corp")

    assert len(results) >= 1
    assert any("planning" in r["title"].lower() for r in results)


def test_search_requires_tenant(index):
    """Test search requires tenant parameter."""
    with pytest.raises(ValueError, match="Tenant is required"):
        search("test", tenant="")


def test_search_tenant_isolation(index):
    """Test search enforces tenant isolation."""
    results = search("message", tenant="acme-corp")

    # Should not include resources from other-corp
    assert all(r["tenant"] == "acme-corp" for r in results)
    assert not any("Private message" in r["title"] for r in results)


def test_search_type_filter(index):
    """Test filtering by resource type."""
    # Search for messages only
    results = search("", tenant="acme-corp", type="message")

    assert len(results) >= 3
    assert all(r["type"] == "message" for r in results)

    # Search for contacts only
    results = search("", tenant="acme-corp", type="contact")

    assert len(results) >= 1
    assert all(r["type"] == "contact" for r in results)


def test_search_source_filter(index):
    """Test filtering by source connector."""
    # Teams messages only
    results = search("", tenant="acme-corp", source="teams")

    assert len(results) >= 1
    assert all(r["source"] == "teams" for r in results)

    # Outlook resources only
    results = search("", tenant="acme-corp", source="outlook")

    assert len(results) >= 2
    assert all(r["source"] == "outlook" for r in results)


def test_search_combined_filters(index):
    """Test combining type and source filters."""
    results = search("", tenant="acme-corp", type="message", source="teams")

    assert len(results) >= 1
    assert all(r["type"] == "message" and r["source"] == "teams" for r in results)


def test_search_limit(index):
    """Test limit parameter."""
    results = search("", tenant="acme-corp", limit=2)

    assert len(results) <= 2


def test_empty_query_returns_all(index):
    """Test empty query returns all resources (filtered)."""
    results = search("", tenant="acme-corp")

    # Should return all acme-corp resources
    assert len(results) >= 4


def test_no_results(index):
    """Test search with no matches."""
    results = search("nonexistent-term-xyz", tenant="acme-corp")

    assert len(results) == 0


def test_search_scoring_title_priority(index):
    """Test search scores title matches higher."""
    # "planning" appears in title of msg-1
    results = search("planning", tenant="acme-corp")

    assert len(results) >= 1
    # Msg-1 should be ranked high due to title match
    top_result = results[0]
    assert "planning" in top_result["title"].lower()


def test_search_snippet_matching(index):
    """Test search matches against snippet."""
    results = search("standup", tenant="acme-corp")

    assert len(results) >= 1
    assert any("standup" in r["snippet"].lower() for r in results)


def test_search_participant_matching(index):
    """Test search matches participants."""
    results = search("alice", tenant="acme-corp")

    # Should match both message and contact with alice
    assert len(results) >= 2
    assert any("alice" in str(r.get("participants", [])).lower() for r in results)


def test_search_case_insensitive(index):
    """Test search is case insensitive."""
    results_lower = search("budget", tenant="acme-corp")
    results_upper = search("BUDGET", tenant="acme-corp")
    results_mixed = search("BuDgEt", tenant="acme-corp")

    assert len(results_lower) == len(results_upper) == len(results_mixed)


def test_search_tokenization(index):
    """Test query tokenization."""
    # Multi-word query
    results = search("team standup", tenant="acme-corp")

    # Should match msg-3 which has both terms
    assert len(results) >= 1
    assert any("standup" in r["title"].lower() for r in results)


def test_search_relevance_sorting(index):
    """Test results sorted by relevance."""
    # "meeting" appears in title of msg-1
    results = search("meeting", tenant="acme-corp")

    if len(results) > 0:
        # First result should have meeting in title (highest score)
        top_result = results[0]
        assert "meeting" in top_result["title"].lower()


def test_search_by_type_helper(index):
    """Test search_by_type helper function."""
    results = search_by_type("message", tenant="acme-corp")

    assert len(results) >= 3
    assert all(r["type"] == "message" for r in results)


def test_search_by_source_helper(index):
    """Test search_by_source helper function."""
    results = search_by_source("slack", tenant="acme-corp")

    assert len(results) >= 1
    assert all(r["source"] == "slack" for r in results)


def test_search_with_type_and_source(index):
    """Test combining type and source in search."""
    results = search("", tenant="acme-corp", type="message", source="outlook")

    assert len(results) >= 1
    for r in results:
        assert r["type"] == "message"
        assert r["source"] == "outlook"


def test_search_returns_sorted_by_timestamp(index):
    """Test results with equal score sorted by timestamp."""
    results = search("", tenant="acme-corp", type="message")

    # With no query, should be sorted by timestamp descending
    if len(results) >= 2:
        # Timestamps should be in descending order
        for i in range(len(results) - 1):
            ts1 = results[i].get("timestamp", "")
            ts2 = results[i + 1].get("timestamp", "")
            # Later timestamp should come first (or equal)
            assert ts1 >= ts2


def test_search_special_characters(index):
    """Test search handles special characters."""
    # Punctuation in query
    results = search("Q4!", tenant="acme-corp")

    # Should still match "Q4" despite punctuation
    assert len(results) >= 1


def test_search_email_addresses(index):
    """Test searching for email addresses."""
    results = search("alice@example.com", tenant="acme-corp")

    assert len(results) >= 1
    # Should match resources with alice@example.com in participants
