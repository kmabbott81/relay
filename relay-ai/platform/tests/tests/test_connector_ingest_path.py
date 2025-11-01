"""Tests for connector ingestion into URG."""

from unittest.mock import MagicMock, patch

import pytest

from src.connectors.base import ConnectorResult
from src.connectors.ingest import (
    ingest_all_connectors,
    ingest_connector_snapshot,
)
from src.graph.index import get_index


@pytest.fixture
def mock_teams_connector():
    """Create mock Teams connector."""
    connector = MagicMock()
    connector.connect.return_value = ConnectorResult(status="success")
    connector.disconnect.return_value = ConnectorResult(status="success")
    connector.list_resources.return_value = ConnectorResult(
        status="success",
        data=[
            {
                "id": "teams-msg-1",
                "subject": "Teams Meeting",
                "body": {"content": "Let's meet to discuss"},
                "from": {"user": {"displayName": "Alice"}},
                "createdDateTime": "2025-01-15T10:00:00Z",
            }
        ],
    )
    return connector


@pytest.fixture
def mock_outlook_connector():
    """Create mock Outlook connector."""
    connector = MagicMock()
    connector.connect.return_value = ConnectorResult(status="success")
    connector.disconnect.return_value = ConnectorResult(status="success")
    connector.list_resources.return_value = ConnectorResult(
        status="success",
        data=[
            {
                "id": "outlook-msg-1",
                "subject": "Email Subject",
                "body": {"content": "Email body text"},
                "from": {"emailAddress": {"address": "bob@example.com"}},
                "receivedDateTime": "2025-01-16T10:00:00Z",
            }
        ],
    )
    return connector


@pytest.fixture
def mock_slack_connector():
    """Create mock Slack connector."""
    connector = MagicMock()
    connector.connect.return_value = ConnectorResult(status="success")
    connector.disconnect.return_value = ConnectorResult(status="success")
    connector.list_resources.return_value = ConnectorResult(
        status="success",
        data=[
            {
                "ts": "1234567890.123456",
                "text": "Slack message text",
                "user": "U123456",
                "channel": "C123456",
            }
        ],
    )
    return connector


@pytest.fixture
def mock_gmail_connector():
    """Create mock Gmail connector."""
    connector = MagicMock()
    connector.connect.return_value = ConnectorResult(status="success")
    connector.disconnect.return_value = ConnectorResult(status="success")
    connector.list_resources.return_value = ConnectorResult(
        status="success",
        data=[
            {
                "id": "gmail-msg-1",
                "snippet": "Gmail message preview",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Gmail Subject"},
                        {"name": "From", "value": "charlie@example.com"},
                    ]
                },
                "internalDate": "1642252800000",
                "threadId": "thread-123",
            }
        ],
    )
    return connector


def test_ingest_teams_messages(mock_teams_connector):
    """Test ingesting messages from Teams."""
    with patch("src.connectors.ingest.TeamsConnector", return_value=mock_teams_connector):
        result = ingest_connector_snapshot(
            "teams",
            "messages",
            tenant="test-tenant",
            user_id="user-123",
            limit=10,
        )

        assert result["count"] == 1
        assert result["errors"] == 0
        assert result["source"] == "teams"
        assert result["resource_type"] == "messages"

        # Verify resource in index
        index = get_index()
        stats = index.get_stats(tenant="test-tenant")
        assert stats["total"] >= 1


def test_ingest_outlook_messages(mock_outlook_connector):
    """Test ingesting messages from Outlook."""
    with patch("src.connectors.ingest.OutlookConnector", return_value=mock_outlook_connector):
        result = ingest_connector_snapshot(
            "outlook",
            "messages",
            tenant="test-tenant",
            user_id="user-123",
            limit=10,
        )

        assert result["count"] == 1
        assert result["errors"] == 0
        assert result["source"] == "outlook"


def test_ingest_slack_messages(mock_slack_connector):
    """Test ingesting messages from Slack."""
    with patch("src.connectors.ingest.SlackConnector", return_value=mock_slack_connector):
        result = ingest_connector_snapshot(
            "slack",
            "messages",
            tenant="test-tenant",
            user_id="user-123",
            limit=10,
        )

        assert result["count"] == 1
        assert result["errors"] == 0
        assert result["source"] == "slack"


def test_ingest_gmail_messages(mock_gmail_connector):
    """Test ingesting messages from Gmail."""
    with patch("src.connectors.ingest.GmailConnector", return_value=mock_gmail_connector):
        result = ingest_connector_snapshot(
            "gmail",
            "messages",
            tenant="test-tenant",
            user_id="user-123",
            limit=10,
        )

        assert result["count"] == 1
        assert result["errors"] == 0
        assert result["source"] == "gmail"


def test_ingest_applies_cp_cal_normalization(mock_teams_connector):
    """Test ingestion applies CP-CAL normalization."""
    with patch("src.connectors.ingest.TeamsConnector", return_value=mock_teams_connector):
        ingest_connector_snapshot(
            "teams",
            "messages",
            tenant="test-tenant",
            user_id="user-123",
            limit=10,
        )

        # Check normalized fields in index
        index = get_index()
        resources = index.list_by_tenant("test-tenant")

        assert len(resources) >= 1
        resource = resources[0]

        # Should have normalized URG schema fields
        assert "id" in resource
        assert "type" in resource
        assert resource["type"] == "message"
        assert "title" in resource
        assert "snippet" in resource
        assert "timestamp" in resource
        assert "source" in resource
        assert resource["source"] == "teams"


def test_ingest_creates_urg_entries(mock_outlook_connector):
    """Test ingestion creates URG index entries."""
    with patch("src.connectors.ingest.OutlookConnector", return_value=mock_outlook_connector):
        ingest_connector_snapshot(
            "outlook",
            "messages",
            tenant="test-tenant",
            user_id="user-123",
            limit=10,
        )

        index = get_index()

        # Verify entry exists with correct graph ID format
        resources = index.list_by_tenant("test-tenant")
        assert len(resources) >= 1

        resource = resources[0]
        assert resource["id"].startswith("urn:outlook:message:")


def test_ingest_dry_run_mode(mock_teams_connector):
    """Test ingestion works in DRY_RUN mode."""
    # DRY_RUN is default, connector should use mocks
    with patch("src.connectors.ingest.TeamsConnector", return_value=mock_teams_connector):
        result = ingest_connector_snapshot(
            "teams",
            "messages",
            tenant="test-tenant",
            user_id="user-123",
            limit=10,
        )

        # Should succeed with mock data
        assert result["count"] >= 0


def test_ingest_tenant_isolation():
    """Test ingestion respects tenant isolation."""
    # Create a fresh mock for each call with different IDs
    call_count = [0]  # Use list to modify in nested function

    def make_mock(*args, **kwargs):
        call_count[0] += 1
        connector = MagicMock()
        connector.connect.return_value = ConnectorResult(status="success")
        connector.disconnect.return_value = ConnectorResult(status="success")
        # Use different message IDs for each call to avoid overwriting
        connector.list_resources.return_value = ConnectorResult(
            status="success",
            data=[
                {
                    "id": f"teams-msg-{call_count[0]}",
                    "subject": f"Teams Meeting {call_count[0]}",
                    "body": {"content": "Let's meet to discuss"},
                    "from": {"user": {"displayName": "Alice"}},
                    "createdDateTime": "2025-01-15T10:00:00Z",
                }
            ],
        )
        return connector

    with patch("src.connectors.ingest.TeamsConnector", side_effect=make_mock):
        # Ingest for tenant-a
        ingest_connector_snapshot(
            "teams",
            "messages",
            tenant="tenant-a",
            user_id="user-123",
            limit=10,
        )

        # Ingest for tenant-b
        ingest_connector_snapshot(
            "teams",
            "messages",
            tenant="tenant-b",
            user_id="user-123",
            limit=10,
        )

        index = get_index()

        # Each tenant should only see their own resources
        tenant_a_resources = index.list_by_tenant("tenant-a")
        tenant_b_resources = index.list_by_tenant("tenant-b")

        assert len(tenant_a_resources) >= 1
        assert len(tenant_b_resources) >= 1

        # Verify tenant field
        for resource in tenant_a_resources:
            assert resource["tenant"] == "tenant-a"

        for resource in tenant_b_resources:
            assert resource["tenant"] == "tenant-b"


def test_ingest_handles_connector_errors():
    """Test ingestion handles connector errors gracefully."""
    mock_connector = MagicMock()
    mock_connector.connect.return_value = ConnectorResult(status="error", message="Connection failed")

    with patch("src.connectors.ingest.TeamsConnector", return_value=mock_connector):
        with pytest.raises(ValueError, match="Failed to connect"):
            ingest_connector_snapshot(
                "teams",
                "messages",
                tenant="test-tenant",
                user_id="user-123",
                limit=10,
            )


def test_ingest_handles_malformed_resources():
    """Test ingestion handles malformed resources."""
    mock_connector = MagicMock()
    mock_connector.connect.return_value = ConnectorResult(status="success")
    mock_connector.disconnect.return_value = ConnectorResult(status="success")
    mock_connector.list_resources.return_value = ConnectorResult(
        status="success",
        data=[
            # Valid resource
            {
                "id": "valid-msg",
                "subject": "Valid",
                "body": {"content": "Valid message"},
                "from": {"user": {"displayName": "Alice"}},
                "createdDateTime": "2025-01-15T10:00:00Z",
            },
            # Malformed resource (missing required fields)
            {},
        ],
    )

    with patch("src.connectors.ingest.TeamsConnector", return_value=mock_connector):
        result = ingest_connector_snapshot(
            "teams",
            "messages",
            tenant="test-tenant",
            user_id="user-123",
            limit=10,
        )

        # Should have 1 success and 1 error
        assert result["count"] == 1
        assert result["errors"] == 1


def test_ingest_unknown_connector():
    """Test ingestion with unknown connector."""
    with pytest.raises(ValueError, match="Unknown connector"):
        ingest_connector_snapshot(
            "unknown-connector",
            "messages",
            tenant="test-tenant",
            user_id="user-123",
            limit=10,
        )


def test_ingest_with_limit():
    """Test ingestion respects limit parameter."""
    mock_connector = MagicMock()
    mock_connector.connect.return_value = ConnectorResult(status="success")
    mock_connector.disconnect.return_value = ConnectorResult(status="success")
    mock_connector.list_resources.return_value = ConnectorResult(status="success", data=[])

    with patch("src.connectors.ingest.TeamsConnector", return_value=mock_connector):
        ingest_connector_snapshot(
            "teams",
            "messages",
            tenant="test-tenant",
            user_id="user-123",
            limit=50,
        )

        # Verify limit passed to connector
        call_args = mock_connector.list_resources.call_args
        assert call_args[1]["filters"]["limit"] == 50


def test_ingest_outlook_contacts():
    """Test ingesting contacts from Outlook."""
    mock_connector = MagicMock()
    mock_connector.connect.return_value = ConnectorResult(status="success")
    mock_connector.disconnect.return_value = ConnectorResult(status="success")
    mock_connector.list_resources.return_value = ConnectorResult(
        status="success",
        data=[
            {
                "id": "contact-1",
                "displayName": "Alice Anderson",
                "emailAddresses": [{"address": "alice@example.com"}],
                "mobilePhone": "555-1234",
            }
        ],
    )

    with patch("src.connectors.ingest.OutlookConnector", return_value=mock_connector):
        result = ingest_connector_snapshot(
            "outlook",
            "contacts",
            tenant="test-tenant",
            user_id="user-123",
            limit=10,
        )

        assert result["count"] == 1
        assert result["resource_type"] == "contacts"

        # Verify contact in index
        index = get_index()
        resources = index.list_by_tenant("test-tenant")
        assert len(resources) >= 1
        assert resources[0]["type"] == "contact"


def test_ingest_all_connectors():
    """Test ingesting from all connectors."""
    # Mock all connectors
    mock_teams = MagicMock()
    mock_teams.connect.return_value = ConnectorResult(status="success")
    mock_teams.disconnect.return_value = ConnectorResult(status="success")
    mock_teams.list_resources.return_value = ConnectorResult(status="success", data=[])

    with patch("src.connectors.ingest.TeamsConnector", return_value=mock_teams):
        with patch("src.connectors.ingest.OutlookConnector", return_value=mock_teams):
            with patch("src.connectors.ingest.SlackConnector", return_value=mock_teams):
                with patch("src.connectors.ingest.GmailConnector", return_value=mock_teams):
                    results = ingest_all_connectors(tenant="test-tenant", user_id="user-123", limit=10)

                    # Should have results for multiple connector-resource pairs
                    assert len(results) >= 4
                    assert "teams-messages" in results
                    assert "outlook-messages" in results
                    assert "slack-messages" in results
                    assert "gmail-messages" in results
