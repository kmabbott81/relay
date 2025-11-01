"""Test Gmail webhook event normalization.

Tests for Gmail Pub/Sub push notification handling.
"""

import json
from pathlib import Path

import pytest

from src.connectors.webhooks import ingest_event


@pytest.fixture
def sample_message_received():
    """Load sample Gmail message received webhook payload."""
    path = Path("tests/data/gmail/webhooks/message_received.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_ingest_gmail_message_received(sample_message_received):
    """Test Gmail message received event normalization."""
    normalized = ingest_event("gmail", sample_message_received)

    assert normalized["connector_type"] == "gmail"
    assert normalized["event_type"] == "message_received"
    assert normalized["resource_type"] == "message"
    assert "resource_id" in normalized
    assert "timestamp" in normalized
    assert "data" in normalized
    assert "raw_payload" in normalized


def test_ingest_gmail_pub_sub_structure():
    """Test Gmail Pub/Sub push notification structure."""
    payload = {
        "message": {
            "data": "eyJlbWFpbEFkZHJlc3MiOiJ0ZXN0QGV4YW1wbGUuY29tIiwiaGlzdG9yeUlkIjoiOTg3NjU0In0=",
            "messageId": "1234567890",
            "publishTime": "2025-01-15T10:30:00.000Z",
        },
        "subscription": "projects/myproject/subscriptions/gmail-push",
    }

    normalized = ingest_event("gmail", payload)

    assert normalized["connector_type"] == "gmail"
    assert normalized["event_type"] == "message_received"
    assert normalized["resource_type"] == "message"
    assert normalized["timestamp"] == "2025-01-15T10:30:00.000Z"


def test_ingest_gmail_history_update():
    """Test Gmail history update event."""
    payload = {
        "message": {
            "data": "eyJlbWFpbEFkZHJlc3MiOiJ1c2VyQGV4YW1wbGUuY29tIiwiaGlzdG9yeUlkIjoiMTExMTExIn0=",
            "messageId": "9876543210",
            "publishTime": "2025-01-15T11:00:00.000Z",
        },
        "subscription": "projects/test/subscriptions/gmail-watch",
    }

    normalized = ingest_event("gmail", payload)

    assert normalized["connector_type"] == "gmail"
    assert "historyId" in str(normalized["data"])
    assert normalized["timestamp"] == "2025-01-15T11:00:00.000Z"


def test_ingest_gmail_missing_fields():
    """Test Gmail webhook with missing optional fields."""
    payload = {
        "message": {
            "messageId": "test123",
            "publishTime": "2025-01-15T12:00:00.000Z",
        }
    }

    normalized = ingest_event("gmail", payload)

    assert normalized["connector_type"] == "gmail"
    assert normalized["resource_type"] == "message"
    assert normalized["timestamp"] == "2025-01-15T12:00:00.000Z"


def test_normalized_event_structure():
    """Test that normalized event has all required fields."""
    payload = {
        "message": {
            "data": "eyJ0ZXN0IjogInZhbHVlIn0=",
            "messageId": "msg001",
            "publishTime": "2025-01-15T13:00:00.000Z",
        }
    }

    normalized = ingest_event("gmail", payload)

    # Required fields
    assert "connector_type" in normalized
    assert "event_type" in normalized
    assert "resource_type" in normalized
    assert "resource_id" in normalized
    assert "timestamp" in normalized
    assert "data" in normalized
    assert "raw_payload" in normalized

    # Verify raw payload is preserved
    assert normalized["raw_payload"] == payload
