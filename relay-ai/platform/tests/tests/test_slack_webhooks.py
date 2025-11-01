"""Test Slack webhook event normalization.

Tests for ingest_event() with Slack Events API payloads.
"""

import json
from pathlib import Path

from src.connectors.webhooks import ingest_event


def test_slack_message_event():
    """Test normalizing Slack message.channels event."""
    # Load sample webhook data
    webhook_path = Path("tests/data/slack/webhooks/message_created.json")

    if webhook_path.exists():
        with open(webhook_path) as f:
            payload = json.load(f)
    else:
        # Fallback inline payload if file doesn't exist yet
        payload = {
            "type": "event_callback",
            "event": {
                "type": "message",
                "channel": "C1234567890",
                "user": "U1234567890",
                "text": "Hello, world!",
                "ts": "1609459200.000100",
                "event_ts": "1609459200.000100",
            },
        }

    normalized = ingest_event("slack", payload)

    # Verify normalized structure
    assert normalized["connector_type"] == "slack"
    assert normalized["event_type"] == "message"
    assert normalized["resource_type"] == "message"
    assert normalized["resource_id"] == "1609459200.000100"
    assert "timestamp" in normalized
    assert "data" in normalized
    assert normalized["data"]["text"] == "Hello, world!"
    assert "raw_payload" in normalized


def test_slack_url_verification():
    """Test Slack URL verification challenge."""
    payload = {
        "type": "url_verification",
        "challenge": "3eZbrw1aBm2rZgRNFdxV2595E9CY3gmdALWMmHkvFXO7tYXAYM8P",
        "token": "Jhj5dZrVaK7ZwHHjRyZWjbDl",
    }

    normalized = ingest_event("slack", payload)

    assert normalized["connector_type"] == "slack"
    assert normalized["event_type"] == "url_verification"
    assert normalized["resource_type"] == "challenge"
    assert normalized["data"]["challenge"] == payload["challenge"]


def test_slack_channel_event():
    """Test Slack channel event."""
    payload = {
        "type": "event_callback",
        "event": {
            "type": "channel_created",
            "channel": "C1234567890",
            "event_ts": "1609459200.000100",
        },
    }

    normalized = ingest_event("slack", payload)

    assert normalized["connector_type"] == "slack"
    assert normalized["event_type"] == "channel_created"
    assert normalized["resource_type"] == "channel"
    assert normalized["resource_id"] == "C1234567890"


def test_slack_user_event():
    """Test Slack user event."""
    payload = {
        "type": "event_callback",
        "event": {
            "type": "user_change",
            "user": "U1234567890",
            "event_ts": "1609459200.000100",
        },
    }

    normalized = ingest_event("slack", payload)

    assert normalized["connector_type"] == "slack"
    assert normalized["event_type"] == "user_change"
    assert normalized["resource_type"] == "user"
    assert normalized["resource_id"] == "U1234567890"


def test_slack_unknown_event():
    """Test unknown Slack event type."""
    payload = {
        "type": "unknown_type",
        "data": {"foo": "bar"},
    }

    normalized = ingest_event("slack", payload)

    assert normalized["connector_type"] == "slack"
    assert normalized["event_type"] == "unknown_type"
    assert normalized["resource_type"] == "unknown"
