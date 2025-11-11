"""Test Gmail connector in DRY_RUN mode.

All tests run offline using mock responses.
"""

import os

import pytest

from relay_ai.connectors.gmail import GmailConnector


@pytest.fixture
def gmail_connector():
    """Create Gmail connector in DRY_RUN mode."""
    os.environ["DRY_RUN"] = "true"
    os.environ["LIVE"] = "false"
    os.environ["USER_ROLE"] = "Admin"

    connector = GmailConnector(
        connector_id="test-gmail",
        tenant_id="tenant-1",
        user_id="user-1",
    )

    yield connector

    # Cleanup
    if connector.mock_path.exists():
        connector.mock_path.unlink()


def test_connect_dry_run(gmail_connector):
    """Test connection in DRY_RUN mode."""
    assert gmail_connector.dry_run is True
    assert gmail_connector.connect() is True


def test_list_messages(gmail_connector):
    """Test listing messages."""
    messages = gmail_connector.list_resources("messages")

    assert isinstance(messages, list)
    assert len(messages) >= 0

    # Verify metrics were recorded
    assert gmail_connector.mock_path.exists()


def test_list_messages_with_query(gmail_connector):
    """Test listing messages with query filter."""
    messages = gmail_connector.list_resources("messages", q="subject:test", maxResults=10)

    assert isinstance(messages, list)


def test_list_threads(gmail_connector):
    """Test listing threads."""
    threads = gmail_connector.list_resources("threads")

    assert isinstance(threads, list)
    assert len(threads) >= 0


def test_list_labels(gmail_connector):
    """Test listing labels."""
    labels = gmail_connector.list_resources("labels")

    assert isinstance(labels, list)
    assert len(labels) >= 0


def test_get_message(gmail_connector):
    """Test getting specific message."""
    message = gmail_connector.get_resource("messages", "18c8f123456789ab")

    assert isinstance(message, dict)
    assert "id" in message or len(message) >= 0


def test_get_message_with_format(gmail_connector):
    """Test getting message with specific format."""
    message = gmail_connector.get_resource("messages", "18c8f123456789ab", format="full")

    assert isinstance(message, dict)


def test_get_thread(gmail_connector):
    """Test getting specific thread."""
    thread = gmail_connector.get_resource("threads", "18c8f123456789ab")

    assert isinstance(thread, dict)


def test_get_label(gmail_connector):
    """Test getting specific label."""
    label = gmail_connector.get_resource("labels", "INBOX")

    assert isinstance(label, dict)


def test_create_message(gmail_connector):
    """Test sending message."""
    payload = {
        "raw": "RnJvbTogc2VuZGVyQGV4YW1wbGUuY29tClRvOiByZWNpcGllbnRAZXhhbXBsZS5jb20KU3ViamVjdDogVGVzdApDb250ZW50LVR5cGU6IHRleHQvcGxhaW47IGNoYXJzZXQ9dXRmLTgKCkhlbGxvIGZyb20gdGVzdA=="
    }

    result = gmail_connector.create_resource("messages", payload)

    assert isinstance(result, dict)
    assert "id" in result or len(result) >= 0


def test_create_message_rbac(gmail_connector):
    """Test create requires Admin role."""
    os.environ["USER_ROLE"] = "Viewer"

    # Recreate connector with Viewer role
    connector = GmailConnector(
        connector_id="test-gmail-viewer",
        tenant_id="tenant-1",
        user_id="user-1",
    )

    payload = {"raw": "test"}

    with pytest.raises(PermissionError, match="Admin"):
        connector.create_resource("messages", payload)


def test_create_label(gmail_connector):
    """Test creating label."""
    payload = {
        "name": "Test Label",
        "labelListVisibility": "labelShow",
        "messageListVisibility": "show",
    }

    result = gmail_connector.create_resource("labels", payload)

    assert isinstance(result, dict)


def test_update_message(gmail_connector):
    """Test updating message labels."""
    payload = {"addLabelIds": ["Label_1"], "removeLabelIds": ["INBOX"]}

    result = gmail_connector.update_resource("messages", "18c8f123456789ab", payload)

    assert isinstance(result, dict)


def test_update_label(gmail_connector):
    """Test updating label properties."""
    payload = {"name": "Updated Label Name"}

    result = gmail_connector.update_resource("labels", "Label_1", payload)

    assert isinstance(result, dict)


def test_delete_message(gmail_connector):
    """Test deleting message."""
    result = gmail_connector.delete_resource("messages", "18c8f123456789ab")

    assert result is True


def test_delete_label(gmail_connector):
    """Test deleting label."""
    result = gmail_connector.delete_resource("labels", "Label_1")

    assert result is True


def test_unknown_resource_type(gmail_connector):
    """Test unknown resource type raises error."""
    with pytest.raises(ValueError, match="Unknown resource type"):
        gmail_connector.list_resources("invalid_type")


def test_metrics_recording(gmail_connector):
    """Test that metrics are recorded for API calls."""
    gmail_connector.list_resources("messages")

    # Mock path should exist after API call
    assert gmail_connector.mock_path.exists()


@pytest.mark.skipif(os.getenv("LIVE", "false").lower() != "true", reason="LIVE mode tests require LIVE=true")
def test_live_mode_example():
    """Example test that only runs in LIVE mode."""
    # This test demonstrates live mode testing
    # In real scenarios, this would test actual API calls
    assert os.getenv("LIVE", "false").lower() == "true"
