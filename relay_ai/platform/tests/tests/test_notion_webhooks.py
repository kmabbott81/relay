"""Test Notion webhook event normalization.

Tests for ingest_event() with Notion webhook payloads.
"""

import json
from pathlib import Path

from relay_ai.connectors.webhooks import ingest_event


def test_notion_page_updated_event():
    """Test normalizing Notion page.updated event."""
    # Load sample webhook data
    webhook_path = Path("tests/data/notion/webhooks/page_updated.json")

    if webhook_path.exists():
        with open(webhook_path) as f:
            payload = json.load(f)
    else:
        # Fallback inline payload if file doesn't exist yet
        payload = {
            "type": "page.updated",
            "page": {
                "object": "page",
                "id": "page-abc-123",
                "created_time": "2023-01-01T10:00:00.000Z",
                "last_edited_time": "2023-01-02T15:30:00.000Z",
                "properties": {
                    "Name": {
                        "id": "title",
                        "type": "title",
                        "title": [{"plain_text": "Updated Project Plan"}],
                    }
                },
            },
            "timestamp": "2023-01-02T15:30:00.000Z",
        }

    normalized = ingest_event("notion", payload)

    # Verify normalized structure
    assert normalized["connector_type"] == "notion"
    assert normalized["event_type"] == "page.updated"
    assert normalized["resource_type"] == "page"
    assert normalized["resource_id"] == "page-abc-123"
    assert "timestamp" in normalized
    assert normalized["timestamp"] == "2023-01-02T15:30:00.000Z"
    assert "data" in normalized
    assert normalized["data"]["object"] == "page"
    assert "raw_payload" in normalized


def test_notion_page_created_event():
    """Test normalizing Notion page.created event."""
    payload = {
        "type": "page.created",
        "page": {
            "object": "page",
            "id": "page-new-456",
            "created_time": "2023-01-03T10:00:00.000Z",
            "last_edited_time": "2023-01-03T10:00:00.000Z",
            "properties": {
                "Name": {
                    "id": "title",
                    "type": "title",
                    "title": [{"plain_text": "New Page"}],
                }
            },
        },
        "timestamp": "2023-01-03T10:00:00.000Z",
    }

    normalized = ingest_event("notion", payload)

    assert normalized["connector_type"] == "notion"
    assert normalized["event_type"] == "page.created"
    assert normalized["resource_type"] == "page"
    assert normalized["resource_id"] == "page-new-456"


def test_notion_database_updated_event():
    """Test normalizing Notion database.updated event."""
    payload = {
        "type": "database.updated",
        "database": {
            "object": "database",
            "id": "database-xyz-789",
            "created_time": "2023-01-01T10:00:00.000Z",
            "last_edited_time": "2023-01-03T14:00:00.000Z",
            "title": [{"plain_text": "Project Tracker"}],
        },
        "timestamp": "2023-01-03T14:00:00.000Z",
    }

    normalized = ingest_event("notion", payload)

    assert normalized["connector_type"] == "notion"
    assert normalized["event_type"] == "database.updated"
    assert normalized["resource_type"] == "database"
    assert normalized["resource_id"] == "database-xyz-789"


def test_notion_block_updated_event():
    """Test normalizing Notion block.updated event."""
    payload = {
        "type": "block.updated",
        "block": {
            "object": "block",
            "id": "block-123",
            "type": "paragraph",
            "created_time": "2023-01-01T10:00:00.000Z",
            "last_edited_time": "2023-01-03T14:30:00.000Z",
        },
        "timestamp": "2023-01-03T14:30:00.000Z",
    }

    normalized = ingest_event("notion", payload)

    assert normalized["connector_type"] == "notion"
    assert normalized["event_type"] == "block.updated"
    assert normalized["resource_type"] == "block"
    assert normalized["resource_id"] == "block-123"


def test_notion_unknown_event():
    """Test normalizing unknown Notion event type."""
    payload = {
        "type": "unknown.event",
        "data": {"id": "some-id"},
        "timestamp": "2023-01-03T14:00:00.000Z",
    }

    normalized = ingest_event("notion", payload)

    assert normalized["connector_type"] == "notion"
    assert normalized["event_type"] == "unknown.event"
    # Unknown events should default to 'unknown' resource type
    assert normalized["resource_type"] == "unknown"
