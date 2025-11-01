"""Tests for Teams webhook ingestion and normalization.

Verifies webhook payloads are properly parsed and normalized.
"""

import json
from pathlib import Path


def load_webhook_fixture(filename: str) -> dict:
    """Load webhook fixture from tests/data/teams/webhooks."""
    fixture_path = Path(__file__).parent / "data" / "teams" / "webhooks" / filename
    with open(fixture_path, encoding="utf-8") as f:
        return json.load(f)


def normalize_teams_webhook(webhook_data: dict) -> dict:
    """Normalize Teams webhook to unified format.

    Args:
        webhook_data: Raw webhook payload from Microsoft Teams

    Returns:
        Normalized message dict with standard fields
    """
    resource_data = webhook_data.get("resourceData", {})

    return {
        "id": resource_data.get("id"),
        "event_type": webhook_data.get("changeType"),
        "created_at": resource_data.get("createdDateTime"),
        "author": {
            "id": resource_data.get("from", {}).get("user", {}).get("id"),
            "name": resource_data.get("from", {}).get("user", {}).get("displayName"),
        },
        "content": {
            "type": resource_data.get("body", {}).get("contentType"),
            "text": resource_data.get("body", {}).get("content"),
        },
        "metadata": {
            "resource": webhook_data.get("resource"),
            "subscription_id": webhook_data.get("subscriptionId"),
            "tenant_id": webhook_data.get("tenantId"),
        },
    }


def test_webhook_message_created_structure():
    """Webhook fixture has expected structure."""
    webhook = load_webhook_fixture("message_created.json")

    assert webhook["changeType"] == "created"
    assert webhook["resourceData"]["id"] == "msg-789"
    assert webhook["resourceData"]["from"]["user"]["id"] == "user-001"
    assert webhook["resourceData"]["from"]["user"]["displayName"] == "John Doe"
    assert webhook["resourceData"]["body"]["contentType"] == "text"
    assert webhook["resourceData"]["body"]["content"] == "Hello Teams!"


def test_webhook_normalization_complete():
    """Normalize message_created webhook to unified format."""
    webhook = load_webhook_fixture("message_created.json")
    normalized = normalize_teams_webhook(webhook)

    # Base fields
    assert normalized["id"] == "msg-789"
    assert normalized["event_type"] == "created"
    assert normalized["created_at"] == "2025-10-04T12:00:00Z"

    # Author
    assert normalized["author"]["id"] == "user-001"
    assert normalized["author"]["name"] == "John Doe"

    # Content
    assert normalized["content"]["type"] == "text"
    assert normalized["content"]["text"] == "Hello Teams!"

    # Metadata
    assert normalized["metadata"]["resource"] == "teams/team-123/channels/channel-456/messages/msg-789"
    assert normalized["metadata"]["subscription_id"] == "sub-abc"
    assert normalized["metadata"]["tenant_id"] == "tenant-xyz"


def test_webhook_normalize_handles_missing_fields():
    """Normalization handles missing fields gracefully."""
    minimal_webhook = {"changeType": "created", "resourceData": {"id": "msg-123"}}
    normalized = normalize_teams_webhook(minimal_webhook)

    assert normalized["id"] == "msg-123"
    assert normalized["event_type"] == "created"
    assert normalized["author"]["id"] is None
    assert normalized["author"]["name"] is None
