"""Tests for Unified Resource Graph Action Router."""

from unittest.mock import MagicMock, patch

import pytest

from relay_ai.graph.actions import (
    ACTION_REGISTRY,
    ActionError,
    RBACDenied,
    execute_action,
    list_actions,
    register_action,
)
from relay_ai.graph.index import get_index


@pytest.fixture
def index():
    """Populate URG index with sample data (isolated by clean_graph_env)."""
    idx = get_index()

    # Add sample message
    idx.upsert(
        {
            "id": "msg-123",
            "type": "message",
            "title": "Test Message",
            "snippet": "This is a test message",
            "timestamp": "2025-01-15T10:00:00Z",
            "metadata": {"original_id": "msg-123"},
        },
        source="teams",
        tenant="test-tenant",
    )

    # Add sample contact
    idx.upsert(
        {
            "id": "contact-456",
            "type": "contact",
            "title": "Alice Anderson",
            "snippet": "alice@example.com",
            "participants": ["alice@example.com"],
            "metadata": {"original_id": "contact-456"},
        },
        source="outlook",
        tenant="test-tenant",
    )

    return idx


def test_action_registry_lookup(index):
    """Test action registry has registered actions."""
    assert "message" in ACTION_REGISTRY
    assert "reply" in ACTION_REGISTRY["message"]
    assert "forward" in ACTION_REGISTRY["message"]
    assert "delete" in ACTION_REGISTRY["message"]


def test_register_action_decorator():
    """Test registering custom action."""

    @register_action("custom", "test_action")
    def custom_action(resource, payload, *, user_id, tenant):
        return {"result": "ok"}

    assert "custom" in ACTION_REGISTRY
    assert "test_action" in ACTION_REGISTRY["custom"]


def test_execute_action_requires_admin_role(index):
    """Test execute_action requires Admin role."""
    graph_id = "urn:teams:message:msg-123"

    # Mock get_team_role to return non-Admin role
    with patch("src.graph.actions.get_team_role", return_value="Viewer"):
        with pytest.raises(RBACDenied, match="Admin role required"):
            execute_action(
                "message.reply",
                graph_id,
                {"body": "Test reply"},
                user_id="user-123",
                tenant="test-tenant",
            )


def test_execute_action_resource_not_found(index):
    """Test execute_action with non-existent resource."""
    with patch("src.graph.actions.get_team_role", return_value="Admin"):
        with pytest.raises(ValueError, match="Resource not found"):
            execute_action(
                "message.reply",
                "urn:teams:message:nonexistent",
                {"body": "Test"},
                user_id="admin",
                tenant="test-tenant",
            )


def test_execute_action_invalid_format(index):
    """Test execute_action with invalid action format."""
    graph_id = "urn:teams:message:msg-123"

    with patch("src.graph.actions.get_team_role", return_value="Admin"):
        with pytest.raises(ValueError, match="Invalid action format"):
            execute_action(
                "invalidaction",
                graph_id,
                {},
                user_id="admin",
                tenant="test-tenant",
            )


def test_execute_action_type_mismatch(index):
    """Test execute_action with type mismatch."""
    graph_id = "urn:teams:message:msg-123"

    with patch("src.graph.actions.get_team_role", return_value="Admin"):
        with pytest.raises(ValueError, match="Resource type mismatch"):
            execute_action(
                "contact.email",  # Contact action on message resource
                graph_id,
                {},
                user_id="admin",
                tenant="test-tenant",
            )


def test_execute_action_unknown_action(index):
    """Test execute_action with unknown action name."""
    graph_id = "urn:teams:message:msg-123"

    with patch("src.graph.actions.get_team_role", return_value="Admin"):
        with pytest.raises(ValueError, match="Unknown action"):
            execute_action(
                "message.unknown_action",
                graph_id,
                {},
                user_id="admin",
                tenant="test-tenant",
            )


def test_execute_action_success_with_admin(index):
    """Test successful action execution with Admin role."""
    graph_id = "urn:teams:message:msg-123"

    # Mock RBAC and connector
    with patch("src.graph.actions.get_team_role", return_value="Admin"):
        with patch("src.graph.actions._get_connector") as mock_get_connector:
            # Mock connector
            mock_connector = MagicMock()
            mock_connector.create_resource.return_value = MagicMock(status="success", data={"id": "reply-123"})
            mock_get_connector.return_value = mock_connector

            result = execute_action(
                "message.reply",
                graph_id,
                {"body": "Test reply"},
                user_id="admin",
                tenant="test-tenant",
            )

            assert result["status"] == "success"
            assert result["action"] == "message.reply"
            assert result["graph_id"] == graph_id


def test_message_reply_action(index):
    """Test message.reply action handler."""
    from src.graph.actions import message_reply

    resource = index.get("urn:teams:message:msg-123", tenant="test-tenant")

    with patch("src.graph.actions._get_connector") as mock_get_connector:
        mock_connector = MagicMock()
        mock_connector.create_resource.return_value = MagicMock(status="success", data={})
        mock_get_connector.return_value = mock_connector

        result = message_reply(
            resource,
            {"body": "Reply text"},
            user_id="user-123",
            tenant="test-tenant",
        )

        assert result["status"] == "replied"


def test_message_delete_action(index):
    """Test message.delete action handler."""
    from src.graph.actions import message_delete

    resource = index.get("urn:teams:message:msg-123", tenant="test-tenant")

    with patch("src.graph.actions._get_connector") as mock_get_connector:
        mock_connector = MagicMock()
        mock_connector.delete_resource.return_value = MagicMock(status="success")
        mock_get_connector.return_value = mock_connector

        result = message_delete(resource, {}, user_id="user-123", tenant="test-tenant")

        assert result["status"] == "deleted"


def test_contact_email_action(index):
    """Test contact.email action handler."""
    from src.graph.actions import contact_email

    resource = index.get("urn:outlook:contact:contact-456", tenant="test-tenant")

    with patch("src.graph.actions._get_connector") as mock_get_connector:
        mock_connector = MagicMock()
        mock_connector.create_resource.return_value = MagicMock(status="success", data={})
        mock_get_connector.return_value = mock_connector

        result = contact_email(
            resource,
            {"subject": "Test", "body": "Hello"},
            user_id="user-123",
            tenant="test-tenant",
        )

        assert result["status"] == "sent"


def test_action_audit_logging_success(index):
    """Test action execution logs audit event on success."""
    graph_id = "urn:teams:message:msg-123"

    with patch("src.graph.actions.get_team_role", return_value="Admin"):
        with patch("src.graph.actions._get_connector") as mock_get_connector:
            with patch("src.graph.actions.AuditLogger") as mock_audit:
                mock_connector = MagicMock()
                mock_connector.create_resource.return_value = MagicMock(status="success")
                mock_get_connector.return_value = mock_connector

                mock_logger = MagicMock()
                mock_audit.return_value = mock_logger

                execute_action(
                    "message.reply",
                    graph_id,
                    {"body": "Test"},
                    user_id="admin",
                    tenant="test-tenant",
                )

                # Verify audit log called
                assert mock_logger.log.called


def test_action_audit_logging_denied(index):
    """Test action execution logs audit event when RBAC denied."""
    graph_id = "urn:teams:message:msg-123"

    with patch("src.graph.actions.get_team_role", return_value="Viewer"):
        with patch("src.graph.actions.AuditLogger") as mock_audit:
            mock_logger = MagicMock()
            mock_audit.return_value = mock_logger

            with pytest.raises(RBACDenied):
                execute_action(
                    "message.reply",
                    graph_id,
                    {"body": "Test"},
                    user_id="viewer",
                    tenant="test-tenant",
                )

            # Verify denied event logged
            assert mock_logger.log.called


def test_action_routing_to_correct_connector(index):
    """Test actions route to correct connector based on source."""
    graph_id = "urn:teams:message:msg-123"

    with patch("src.graph.actions.get_team_role", return_value="Admin"):
        # Patch TeamsConnector where it's imported (in the connectors module)
        with patch("src.connectors.teams.TeamsConnector") as mock_teams:
            mock_connector = MagicMock()
            mock_connector.create_resource.return_value = MagicMock(status="success")
            mock_teams.return_value = mock_connector

            execute_action(
                "message.reply",
                graph_id,
                {"body": "Test"},
                user_id="admin",
                tenant="test-tenant",
            )

            # Verify Teams connector was instantiated
            mock_teams.assert_called_once()


def test_list_actions_all():
    """Test listing all available actions."""
    actions = list_actions()

    assert "message" in actions
    assert "reply" in actions["message"]
    assert "forward" in actions["message"]
    assert "delete" in actions["message"]


def test_list_actions_by_type():
    """Test listing actions for specific resource type."""
    actions = list_actions("message")

    assert "message" in actions
    assert len(actions) == 1
    assert "reply" in actions["message"]


def test_list_actions_unknown_type():
    """Test listing actions for unknown type returns empty."""
    actions = list_actions("unknown_type")

    assert "unknown_type" in actions
    assert len(actions["unknown_type"]) == 0


def test_action_error_on_missing_original_id(index):
    """Test action fails if original_id missing from metadata.

    Note: URGIndex.upsert() automatically adds original_id to metadata,
    so we manually modify the resource after upserting to remove it.
    """
    # Add resource normally
    index.upsert(
        {
            "id": "msg-no-original",
            "type": "message",
            "title": "No Original ID",
        },
        source="teams",
        tenant="test-tenant",
    )

    graph_id = "urn:teams:message:msg-no-original"

    # Manually remove original_id from metadata to test the error case
    if graph_id in index.resources:
        index.resources[graph_id]["metadata"] = {}

    with patch("src.graph.actions.get_team_role", return_value="Admin"):
        # Mock TeamsConnector so it doesn't fail with RBAC before we get to the original_id check
        with patch("src.connectors.teams.TeamsConnector") as mock_teams:
            mock_connector = MagicMock()
            mock_teams.return_value = mock_connector

            # The action handler should raise ActionError for missing original_id
            with pytest.raises(ActionError, match="original_id not found"):
                execute_action(
                    "message.reply",
                    graph_id,
                    {"body": "Test"},
                    user_id="admin",
                    tenant="test-tenant",
                )


def test_get_connector_for_each_source():
    """Test _get_connector returns correct connector class."""
    from src.connectors.gmail import GmailConnector
    from src.connectors.outlook_api import OutlookConnector
    from src.connectors.slack import SlackConnector
    from src.connectors.teams import TeamsConnector
    from src.graph.actions import _get_connector

    teams = _get_connector("teams", "test-user", "test-tenant")
    assert isinstance(teams, TeamsConnector)

    outlook = _get_connector("outlook", "test-user", "test-tenant")
    assert isinstance(outlook, OutlookConnector)

    slack = _get_connector("slack", "test-user", "test-tenant")
    assert isinstance(slack, SlackConnector)

    gmail = _get_connector("gmail", "test-user", "test-tenant")
    assert isinstance(gmail, GmailConnector)


def test_get_connector_unknown_source():
    """Test _get_connector raises error for unknown source."""
    from src.graph.actions import _get_connector

    with pytest.raises(ActionError, match="Unknown source connector"):
        _get_connector("unknown-source", "user", "tenant")
