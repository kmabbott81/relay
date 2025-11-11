"""Tests for mock Outlook connector."""

import json
import os

import pytest

from relay_ai.connectors.mock_outlook import MockOutlookConnector


@pytest.fixture
def mock_outlook(tmp_path, monkeypatch):
    """Mock Outlook connector with temp storage."""
    monkeypatch.setattr("src.connectors.base.get_team_role", lambda u, t: "Admin")
    monkeypatch.setenv("OUTLOOK_TOKEN", "test-token")
    monkeypatch.setenv("DRY_RUN", "false")

    # Use temp directory for storage
    storage_path = tmp_path / "mock_outlook_tenant1.jsonl"
    connector = MockOutlookConnector("outlook", "tenant1", "user1")
    connector.storage_path = storage_path

    return connector


def test_mock_outlook_initialization():
    """Mock Outlook connector initializes."""
    os.environ["OUTLOOK_TOKEN"] = "test-token"
    connector = MockOutlookConnector("outlook", "tenant1", "user1")

    assert connector.connector_id == "outlook"
    assert connector.tenant_id == "tenant1"
    assert connector.user_id == "user1"
    assert connector.token == "test-token"


def test_mock_outlook_dry_run_default():
    """Mock Outlook defaults to dry-run mode."""
    if "DRY_RUN" in os.environ:
        del os.environ["DRY_RUN"]

    connector = MockOutlookConnector("outlook", "tenant1", "user1")
    assert connector.dry_run is True


def test_mock_outlook_connect_success(mock_outlook):
    """Mock Outlook connect succeeds with token."""
    result = mock_outlook.connect()

    assert result.status == "success"
    assert "Connected to mock Outlook" in result.message
    assert mock_outlook.connected is True


def test_mock_outlook_connect_no_token(monkeypatch):
    """Mock Outlook connect fails without token."""
    monkeypatch.setattr("src.connectors.base.get_team_role", lambda u, t: "Admin")
    monkeypatch.setenv("OUTLOOK_TOKEN", "")

    connector = MockOutlookConnector("outlook", "tenant1", "user1")
    result = connector.connect()

    assert result.status == "error"
    assert "OUTLOOK_TOKEN not configured" in result.message


def test_mock_outlook_disconnect(mock_outlook):
    """Mock Outlook disconnect succeeds."""
    mock_outlook.connect()
    result = mock_outlook.disconnect()

    assert result.status == "success"
    assert mock_outlook.connected is False


def test_mock_outlook_create_message(mock_outlook):
    """Mock Outlook create message works."""
    mock_outlook.connect()

    payload = {"to": "alice@example.com", "subject": "Test", "body": "Hello World"}
    result = mock_outlook.create_resource("messages", payload)

    assert result.status == "success"
    assert result.data["to"] == "alice@example.com"
    assert result.data["subject"] == "Test"
    assert "id" in result.data
    assert "created_at" in result.data


def test_mock_outlook_create_dry_run(tmp_path, monkeypatch):
    """Mock Outlook create in dry-run mode doesn't write."""
    monkeypatch.setattr("src.connectors.base.get_team_role", lambda u, t: "Admin")
    monkeypatch.setenv("OUTLOOK_TOKEN", "test-token")
    monkeypatch.setenv("DRY_RUN", "true")

    storage_path = tmp_path / "mock_outlook_tenant1.jsonl"
    connector = MockOutlookConnector("outlook", "tenant1", "user1")
    connector.storage_path = storage_path
    connector.connect()

    payload = {"to": "alice@example.com", "subject": "Test"}
    result = connector.create_resource("messages", payload)

    assert result.status == "success"
    assert "[DRY-RUN]" in result.message
    assert not storage_path.exists()  # No file created in dry-run


def test_mock_outlook_list_messages_empty(mock_outlook):
    """Mock Outlook list returns empty initially."""
    mock_outlook.connect()

    result = mock_outlook.list_resources("messages")

    assert result.status == "success"
    assert result.data == []


def test_mock_outlook_list_messages_populated(mock_outlook):
    """Mock Outlook list returns created messages."""
    mock_outlook.connect()

    mock_outlook.create_resource("messages", {"id": "msg1", "to": "alice@example.com", "subject": "Msg 1"})
    mock_outlook.create_resource("messages", {"id": "msg2", "to": "bob@example.com", "subject": "Msg 2"})

    result = mock_outlook.list_resources("messages")

    assert result.status == "success"
    assert len(result.data) == 2


def test_mock_outlook_list_with_filters(mock_outlook):
    """Mock Outlook list supports filters."""
    mock_outlook.connect()

    mock_outlook.create_resource("messages", {"id": "msg1", "folder": "Inbox", "unread": True})
    mock_outlook.create_resource("messages", {"id": "msg2", "folder": "Inbox", "unread": False})
    mock_outlook.create_resource("messages", {"id": "msg3", "folder": "Sent", "unread": False})

    result = mock_outlook.list_resources("messages", filters={"folder": "Inbox", "unread": True})

    assert result.status == "success"
    assert len(result.data) == 1
    assert result.data[0]["id"] == "msg1"


def test_mock_outlook_get_message(mock_outlook):
    """Mock Outlook get retrieves message."""
    mock_outlook.connect()

    payload = {"id": "msg1", "subject": "Test Message"}
    mock_outlook.create_resource("messages", payload)

    result = mock_outlook.get_resource("messages", "msg1")

    assert result.status == "success"
    assert result.data["id"] == "msg1"
    assert result.data["subject"] == "Test Message"


def test_mock_outlook_get_message_not_found(mock_outlook):
    """Mock Outlook get returns error for missing message."""
    mock_outlook.connect()

    result = mock_outlook.get_resource("messages", "nonexistent")

    assert result.status == "error"
    assert "not found" in result.message


def test_mock_outlook_update_message(mock_outlook):
    """Mock Outlook update modifies message."""
    mock_outlook.connect()

    mock_outlook.create_resource("messages", {"id": "msg1", "subject": "Original"})
    result = mock_outlook.update_resource("messages", "msg1", {"subject": "Updated", "flag": "important"})

    assert result.status == "success"
    assert result.data["subject"] == "Updated"
    assert result.data["flag"] == "important"
    assert "updated_at" in result.data


def test_mock_outlook_delete_message(mock_outlook):
    """Mock Outlook delete removes message."""
    mock_outlook.connect()

    mock_outlook.create_resource("messages", {"id": "msg1", "subject": "To Delete"})
    result = mock_outlook.delete_resource("messages", "msg1")

    assert result.status == "success"
    assert "Deleted messages/msg1" in result.message


def test_mock_outlook_delete_dry_run(tmp_path, monkeypatch):
    """Mock Outlook delete in dry-run mode doesn't write."""
    monkeypatch.setattr("src.connectors.base.get_team_role", lambda u, t: "Admin")
    monkeypatch.setenv("OUTLOOK_TOKEN", "test-token")
    monkeypatch.setenv("DRY_RUN", "true")

    storage_path = tmp_path / "mock_outlook_tenant1.jsonl"
    connector = MockOutlookConnector("outlook", "tenant1", "user1")
    connector.storage_path = storage_path
    connector.connect()

    # Create in live mode first
    connector.dry_run = False
    connector.create_resource("messages", {"id": "msg1", "subject": "Test"})

    # Delete in dry-run mode
    connector.dry_run = True
    result = connector.delete_resource("messages", "msg1")

    assert result.status == "success"
    assert "[DRY-RUN]" in result.message


def test_mock_outlook_jsonl_persistence(mock_outlook):
    """Mock Outlook persists data to JSONL."""
    mock_outlook.connect()

    mock_outlook.create_resource("messages", {"id": "msg1", "subject": "Test"})

    # Read JSONL directly
    lines = mock_outlook.storage_path.read_text().strip().split("\n")
    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert entry["type"] == "messages"
    assert entry["operation"] == "create"
    assert entry["data"]["id"] == "msg1"


def test_mock_outlook_last_wins_semantics(mock_outlook):
    """Mock Outlook uses last-wins for duplicate IDs."""
    mock_outlook.connect()

    mock_outlook.create_resource("messages", {"id": "msg1", "version": 1})
    mock_outlook.update_resource("messages", "msg1", {"version": 2})

    result = mock_outlook.get_resource("messages", "msg1")

    assert result.status == "success"
    assert result.data["version"] == 2


def test_mock_outlook_requires_connection(mock_outlook):
    """Mock Outlook operations require connection."""
    result = mock_outlook.list_resources("messages")

    assert result.status == "error"
    assert result.message == "Not connected"


def test_mock_outlook_rbac_denied(monkeypatch):
    """Mock Outlook connect fails without sufficient role."""
    monkeypatch.setattr("src.connectors.base.get_team_role", lambda u, t: "Viewer")
    monkeypatch.setenv("OUTLOOK_TOKEN", "test-token")

    connector = MockOutlookConnector("outlook", "tenant1", "user1")
    result = connector.connect()

    assert result.status == "denied"
    assert "lacks Operator role" in result.message
