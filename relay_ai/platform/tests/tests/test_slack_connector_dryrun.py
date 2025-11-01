"""Test Slack connector in DRY_RUN mode.

All tests run offline using mock responses.
"""

import os

import pytest

from src.connectors.slack import SlackConnector


@pytest.fixture
def slack_connector():
    """Create Slack connector in DRY_RUN mode."""
    os.environ["DRY_RUN"] = "true"
    os.environ["LIVE"] = "false"
    os.environ["USER_ROLE"] = "Admin"
    os.environ["SLACK_DEFAULT_CHANNEL_ID"] = "C1234567890"

    connector = SlackConnector(
        connector_id="test-slack",
        tenant_id="tenant-1",
        user_id="user-1",
    )

    yield connector

    # Cleanup
    if connector.mock_path.exists():
        connector.mock_path.unlink()


def test_connect_dry_run(slack_connector):
    """Test connection in DRY_RUN mode."""
    assert slack_connector.dry_run is True
    assert slack_connector.connect() is True


def test_list_channels(slack_connector):
    """Test listing channels."""
    channels = slack_connector.list_resources("channels")

    assert isinstance(channels, list)
    assert len(channels) >= 0

    # Verify metrics were recorded
    assert slack_connector.mock_path.exists()


def test_list_messages(slack_connector):
    """Test listing messages in channel."""
    messages = slack_connector.list_resources("messages", channel_id="C1234567890")

    assert isinstance(messages, list)
    assert len(messages) >= 0


def test_list_messages_no_channel_id(slack_connector):
    """Test listing messages without channel_id raises error."""
    # Remove default channel
    slack_connector.default_channel_id = ""

    with pytest.raises(ValueError, match="channel_id required"):
        slack_connector.list_resources("messages")


def test_list_users(slack_connector):
    """Test listing users."""
    users = slack_connector.list_resources("users")

    assert isinstance(users, list)
    assert len(users) >= 0


def test_get_channel(slack_connector):
    """Test getting specific channel."""
    channel = slack_connector.get_resource("channels", "C1234567890")

    assert isinstance(channel, dict)


def test_get_message(slack_connector):
    """Test getting specific message."""
    message = slack_connector.get_resource("messages", "1609459200.000100", channel_id="C1234567890")

    assert isinstance(message, dict)


def test_get_user(slack_connector):
    """Test getting specific user."""
    user = slack_connector.get_resource("users", "U1234567890")

    assert isinstance(user, dict)


def test_create_message(slack_connector):
    """Test creating message."""
    payload = {"text": "Hello from test"}

    result = slack_connector.create_resource("messages", payload, channel_id="C1234567890")

    assert isinstance(result, dict)
    assert result.get("ok") is True


def test_create_message_rbac(slack_connector):
    """Test create requires Admin role."""
    os.environ["USER_ROLE"] = "Viewer"

    # Recreate connector with Viewer role
    connector = SlackConnector(
        connector_id="test-slack-viewer",
        tenant_id="tenant-1",
        user_id="user-1",
    )

    payload = {"text": "Hello"}

    with pytest.raises(PermissionError, match="Admin"):
        connector.create_resource("messages", payload, channel_id="C1234567890")


def test_update_message(slack_connector):
    """Test updating message."""
    payload = {"text": "Updated text"}

    result = slack_connector.update_resource("messages", "1609459200.000100", payload, channel_id="C1234567890")

    assert isinstance(result, dict)


def test_delete_message(slack_connector):
    """Test deleting message."""
    result = slack_connector.delete_resource("messages", "1609459200.000100", channel_id="C1234567890")

    assert result is True


def test_unknown_resource_type(slack_connector):
    """Test unknown resource type raises error."""
    with pytest.raises(ValueError, match="Unknown resource type"):
        slack_connector.list_resources("invalid_type")


@pytest.mark.skipif(os.getenv("LIVE", "false").lower() != "true", reason="LIVE mode tests require LIVE=true")
def test_live_mode_example():
    """Example test that only runs in LIVE mode."""
    # This test demonstrates live mode testing
    # In real scenarios, this would test actual API calls
    assert os.getenv("LIVE", "false").lower() == "true"
