"""Tests for Outlook connector dry-run CRUD operations.

All tests are CI-safe (offline by default, no real API calls).
"""

import json

import pytest

from src.connectors.outlook_api import OutlookConnector


@pytest.fixture
def outlook_dryrun(monkeypatch, tmp_path):
    """Outlook connector in DRY_RUN mode with mocked dependencies."""
    monkeypatch.setattr("src.connectors.base.get_team_role", lambda u, t: "Admin")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("LIVE", "false")
    monkeypatch.setenv("OUTLOOK_DEFAULT_USER_ID", "me")
    monkeypatch.setenv("MS_TENANT_ID", "tenant-123")

    # Mock metrics path
    metrics_path = tmp_path / "metrics.jsonl"
    monkeypatch.setenv("CONNECTOR_METRICS_PATH", str(metrics_path))

    # Mock Outlook mock data path
    mock_path = tmp_path / "outlook_mock.jsonl"
    connector = OutlookConnector("outlook", "tenant1", "user1")
    connector.mock_path = mock_path

    return connector


def test_outlook_dryrun_list_messages(outlook_dryrun):
    """Dry-run list messages returns mock data."""
    result = outlook_dryrun.list_resources("messages")
    assert isinstance(result, list)


def test_outlook_dryrun_list_folders(outlook_dryrun):
    """Dry-run list folders returns mock data."""
    result = outlook_dryrun.list_resources("folders")
    assert isinstance(result, list)


def test_outlook_dryrun_list_contacts(outlook_dryrun):
    """Dry-run list contacts returns mock data."""
    result = outlook_dryrun.list_resources("contacts")
    assert isinstance(result, list)


def test_outlook_dryrun_get_resources(outlook_dryrun):
    """Dry-run get operations return mock data."""
    assert isinstance(outlook_dryrun.get_resource("messages", "msg-123"), dict)
    assert isinstance(outlook_dryrun.get_resource("folders", "folder-456"), dict)
    assert isinstance(outlook_dryrun.get_resource("contacts", "contact-789"), dict)


def test_outlook_dryrun_create_message(outlook_dryrun, monkeypatch):
    """Dry-run create message returns mock response."""
    monkeypatch.setenv("USER_ROLE", "Admin")

    payload = {
        "message": {
            "subject": "Test Email",
            "body": {"contentType": "text", "content": "Test body"},
            "toRecipients": [{"emailAddress": {"address": "test@example.com"}}],
        }
    }

    result = outlook_dryrun.create_resource("messages", payload)
    assert isinstance(result, dict)


def test_outlook_dryrun_update_message(outlook_dryrun, monkeypatch):
    """Dry-run update message returns mock response."""
    monkeypatch.setenv("USER_ROLE", "Admin")

    payload = {"isRead": True}

    result = outlook_dryrun.update_resource("messages", "msg-123", payload)
    assert isinstance(result, dict)


def test_outlook_dryrun_delete_message(outlook_dryrun, monkeypatch):
    """Dry-run delete message returns success."""
    monkeypatch.setenv("USER_ROLE", "Admin")

    result = outlook_dryrun.delete_resource("messages", "msg-123")
    assert result is True


def test_outlook_dryrun_metrics_recorded(outlook_dryrun, monkeypatch, tmp_path):
    """Dry-run operations record metrics."""
    metrics_path = tmp_path / "metrics.jsonl"
    monkeypatch.setenv("CONNECTOR_METRICS_PATH", str(metrics_path))

    outlook_dryrun.list_resources("messages")
    assert metrics_path.exists()

    with open(metrics_path, encoding="utf-8") as f:
        entry = json.loads(f.readline())
        assert entry["connector_id"] == "outlook"
        assert entry["status"] == "success"
        assert "duration_ms" in entry


def test_outlook_dryrun_no_real_api_calls(outlook_dryrun):
    """Dry-run mode never makes real API calls."""
    assert outlook_dryrun.dry_run is True
    assert isinstance(outlook_dryrun.list_resources("messages"), list)


def test_outlook_dryrun_rbac_enforcement(outlook_dryrun, monkeypatch):
    """Dry-run mode enforces RBAC for write operations."""
    monkeypatch.setenv("USER_ROLE", "Viewer")

    payload = {"subject": "Test"}

    with pytest.raises(PermissionError, match="Create requires Admin role"):
        outlook_dryrun.create_resource("messages", payload)

    with pytest.raises(PermissionError, match="Update requires Admin role"):
        outlook_dryrun.update_resource("messages", "msg-123", payload)

    with pytest.raises(PermissionError, match="Delete requires Admin role"):
        outlook_dryrun.delete_resource("messages", "msg-123")


@pytest.mark.live
def test_outlook_live_mode_requires_token(monkeypatch):
    """Live mode requires OAuth2 token (marked @pytest.mark.live)."""
    monkeypatch.setattr("src.connectors.base.get_team_role", lambda u, t: "Admin")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("LIVE", "true")
    monkeypatch.setenv("MS_TENANT_ID", "tenant-123")

    connector = OutlookConnector("outlook", "tenant1", "user1")

    # Should fail without token in live mode
    with pytest.raises(Exception, match="No OAuth2 token found"):
        connector.list_resources("messages")
