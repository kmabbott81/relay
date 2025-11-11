"""Tests for Cross-Platform Connector Abstraction Layer (CP-CAL)."""

import pytest

from relay_ai.connectors.cp_cal import (
    ENDPOINT_REGISTRY,
    EndpointMap,
    SchemaAdapter,
    get_endpoint_map,
)


def test_endpoint_map_creation():
    """EndpointMap can be created with URL templates."""
    endpoint_map = EndpointMap(
        list_url="teams/{team_id}/channels/{channel_id}/messages",
        get_url="teams/{team_id}/channels/{channel_id}/messages/{resource_id}",
        create_url="teams/{team_id}/channels/{channel_id}/messages",
        update_url="teams/{team_id}/channels/{channel_id}/messages/{resource_id}",
        delete_url="teams/{team_id}/channels/{channel_id}/messages/{resource_id}/softDelete",
    )

    assert "{team_id}" in endpoint_map.list_url
    assert "{resource_id}" in endpoint_map.get_url


def test_endpoint_registry_lookup():
    """ENDPOINT_REGISTRY provides endpoints for services and resource types."""
    # Teams messages
    teams_messages = get_endpoint_map("teams", "messages")
    assert teams_messages is not None
    assert "teams" in teams_messages.list_url

    # Outlook messages
    outlook_messages = get_endpoint_map("outlook", "messages")
    assert outlook_messages is not None
    assert "users" in outlook_messages.list_url

    # Unknown service/resource
    unknown = get_endpoint_map("unknown", "unknown")
    assert unknown is None


def test_schema_adapter_normalize_teams_message():
    """SchemaAdapter normalizes Teams message to unified format."""
    teams_message = {
        "id": "msg-123",
        "subject": "Test Subject",
        "body": {"content": "Test body content"},
        "from": {"user": {"displayName": "John Doe"}},
        "createdDateTime": "2025-10-04T12:00:00Z",
        "importance": "high",
        "messageType": "message",
    }

    normalized = SchemaAdapter.normalize_message("teams", teams_message)

    assert normalized["id"] == "msg-123"
    assert normalized["subject"] == "Test Subject"
    assert normalized["body"] == "Test body content"
    assert normalized["from"] == "John Doe"
    assert normalized["timestamp"] == "2025-10-04T12:00:00Z"
    assert normalized["metadata"]["importance"] == "high"


def test_schema_adapter_normalize_outlook_message():
    """SchemaAdapter normalizes Outlook message to unified format."""
    outlook_message = {
        "id": "msg-456",
        "subject": "Email Subject",
        "body": {"content": "Email body content"},
        "from": {"emailAddress": {"address": "sender@example.com"}},
        "receivedDateTime": "2025-10-04T13:00:00Z",
        "importance": "normal",
        "hasAttachments": True,
    }

    normalized = SchemaAdapter.normalize_message("outlook", outlook_message)

    assert normalized["id"] == "msg-456"
    assert normalized["subject"] == "Email Subject"
    assert normalized["body"] == "Email body content"
    assert normalized["from"] == "sender@example.com"
    assert normalized["timestamp"] == "2025-10-04T13:00:00Z"
    assert normalized["metadata"]["hasAttachments"] is True


def test_schema_adapter_normalize_slack_message():
    """SchemaAdapter normalizes Slack message to unified format."""
    slack_message = {
        "ts": "1696424400.123456",
        "text": "Slack message text",
        "user": "U12345",
        "thread_ts": "1696424300.111111",
        "channel": "C67890",
    }

    normalized = SchemaAdapter.normalize_message("slack", slack_message)

    assert normalized["id"] == "1696424400.123456"
    assert normalized["subject"] == ""  # Slack doesn't have subjects
    assert normalized["body"] == "Slack message text"
    assert normalized["from"] == "U12345"
    assert normalized["metadata"]["thread_ts"] == "1696424300.111111"


def test_schema_adapter_denormalize_teams_message():
    """SchemaAdapter converts unified format back to Teams schema."""
    normalized = {
        "subject": "Test Subject",
        "body": "Test body",
        "metadata": {"importance": "high"},
    }

    denormalized = SchemaAdapter.denormalize_message("teams", normalized)

    assert denormalized["subject"] == "Test Subject"
    assert denormalized["body"]["content"] == "Test body"
    assert denormalized["body"]["contentType"] == "text"
    assert denormalized["importance"] == "high"


def test_schema_adapter_denormalize_outlook_message():
    """SchemaAdapter converts unified format back to Outlook schema."""
    normalized = {
        "subject": "Email Subject",
        "body": "Email body",
        "metadata": {
            "importance": "normal",
            "toRecipients": [{"emailAddress": {"address": "test@example.com"}}],
        },
    }

    denormalized = SchemaAdapter.denormalize_message("outlook", normalized)

    assert denormalized["subject"] == "Email Subject"
    assert denormalized["body"]["content"] == "Email body"
    assert denormalized["importance"] == "normal"
    assert len(denormalized["toRecipients"]) == 1


def test_schema_adapter_normalize_outlook_contact():
    """SchemaAdapter normalizes Outlook contact to unified format."""
    outlook_contact = {
        "id": "contact-123",
        "displayName": "Jane Doe",
        "emailAddresses": [{"address": "jane@example.com"}],
        "mobilePhone": "+1-555-0100",
        "jobTitle": "Engineer",
        "companyName": "Acme Corp",
    }

    normalized = SchemaAdapter.normalize_contact("outlook", outlook_contact)

    assert normalized["id"] == "contact-123"
    assert normalized["name"] == "Jane Doe"
    assert normalized["email"] == "jane@example.com"
    assert normalized["phone"] == "+1-555-0100"
    assert normalized["metadata"]["jobTitle"] == "Engineer"


def test_schema_adapter_normalize_outlook_event():
    """SchemaAdapter normalizes Outlook event to unified format."""
    outlook_event = {
        "id": "event-123",
        "subject": "Team Meeting",
        "start": {"dateTime": "2025-10-05T10:00:00"},
        "end": {"dateTime": "2025-10-05T11:00:00"},
        "location": {"displayName": "Conference Room A"},
        "organizer": {"emailAddress": {"address": "organizer@example.com"}},
        "isOnlineMeeting": True,
    }

    normalized = SchemaAdapter.normalize_event("outlook", outlook_event)

    assert normalized["id"] == "event-123"
    assert normalized["title"] == "Team Meeting"
    assert normalized["start"] == "2025-10-05T10:00:00"
    assert normalized["end"] == "2025-10-05T11:00:00"
    assert normalized["location"] == "Conference Room A"
    assert normalized["metadata"]["isOnlineMeeting"] is True


def test_schema_adapter_unsupported_service():
    """SchemaAdapter raises ValueError for unsupported services."""
    with pytest.raises(ValueError, match="Unsupported service"):
        SchemaAdapter.normalize_message("unsupported", {})

    with pytest.raises(ValueError, match="Unsupported service"):
        SchemaAdapter.denormalize_message("unsupported", {})


def test_endpoint_registry_has_multiple_services():
    """ENDPOINT_REGISTRY contains entries for multiple services."""
    assert ("teams", "messages") in ENDPOINT_REGISTRY
    assert ("outlook", "messages") in ENDPOINT_REGISTRY
    assert ("slack", "messages") in ENDPOINT_REGISTRY
    assert ("outlook", "contacts") in ENDPOINT_REGISTRY
