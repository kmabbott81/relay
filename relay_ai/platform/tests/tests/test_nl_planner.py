"""Tests for Natural Language Action Planner."""

from unittest.mock import patch

import pytest

from relay_ai.nl.planner import make_plan


@pytest.fixture
def mock_search():
    """Mock search function."""
    with patch("src.nl.planner.search") as mock:
        yield mock


@pytest.fixture
def mock_resolve_contacts():
    """Mock resolve_contacts function."""
    with patch("src.nl.planner.resolve_contacts") as mock:
        yield mock


@pytest.fixture
def mock_contact():
    """Mock Contact object."""
    from src.nl.ner_contacts import Contact

    return Contact(
        name="Alice Smith",
        email="alice@example.com",
        user_id="alice_id",
        source="outlook",
        graph_id="contact-alice-123",
    )


class TestEmailPlanning:
    """Test email action planning."""

    def test_email_single_recipient(self, mock_resolve_contacts, mock_contact):
        """Test email to single recipient."""
        mock_resolve_contacts.return_value = [mock_contact]

        plan = make_plan(
            "Email alice@example.com about the meeting",
            tenant="test-tenant",
            user_id="user1",
        )

        assert plan.intent.verb == "email"
        assert len(plan.steps) == 1
        assert plan.steps[0].action == "contact.email"
        assert "alice@example.com" in plan.steps[0].description

    def test_email_multiple_recipients(self, mock_resolve_contacts):
        """Test email to multiple recipients."""
        from src.nl.ner_contacts import Contact

        mock_resolve_contacts.return_value = [
            Contact("Alice", "alice@example.com", "alice_id", "outlook", "c1"),
            Contact("Bob", "bob@example.com", "bob_id", "outlook", "c2"),
        ]

        plan = make_plan(
            "Email alice@example.com and bob@example.com",
            tenant="test-tenant",
            user_id="user1",
        )

        assert len(plan.steps) == 2
        assert all(s.action == "contact.email" for s in plan.steps)

    def test_email_with_artifact(self, mock_resolve_contacts, mock_contact):
        """Test email with artifact (document reference)."""
        mock_resolve_contacts.return_value = [mock_contact]

        plan = make_plan(
            'Email the "Q4 Budget" to alice@example.com',
            tenant="test-tenant",
            user_id="user1",
        )

        assert len(plan.steps) == 1
        # Artifact should be in payload
        assert plan.steps[0].payload.get("body") == "Q4 Budget"

    def test_email_no_recipients_error(self, mock_resolve_contacts):
        """Test email without resolvable recipients raises error."""
        mock_resolve_contacts.return_value = []

        with pytest.raises(ValueError, match="Could not resolve"):
            make_plan(
                "Email the report to nobody",
                tenant="test-tenant",
                user_id="user1",
            )


class TestMessagePlanning:
    """Test messaging action planning."""

    def test_message_single_recipient(self, mock_resolve_contacts, mock_contact):
        """Test message to single recipient."""
        mock_resolve_contacts.return_value = [mock_contact]

        plan = make_plan(
            "Message Alice about the project",
            tenant="test-tenant",
            user_id="user1",
        )

        assert plan.intent.verb == "message"
        assert len(plan.steps) == 1
        assert plan.steps[0].action == "contact.message"

    def test_message_with_source_constraint(self, mock_resolve_contacts, mock_contact):
        """Test message with source connector specified."""
        mock_resolve_contacts.return_value = [mock_contact]

        plan = make_plan(
            "Message Alice in Slack",
            tenant="test-tenant",
            user_id="user1",
        )

        assert plan.steps[0].resource["source"] == "slack"


class TestForwardPlanning:
    """Test forward action planning."""

    def test_forward_message(self, mock_search, mock_resolve_contacts, mock_contact):
        """Test forward message."""
        # Mock message to forward
        mock_search.return_value = [
            {
                "id": "msg-123",
                "type": "message",
                "title": "Contract draft",
                "source": "outlook",
            }
        ]

        mock_resolve_contacts.return_value = [mock_contact]

        plan = make_plan(
            "Forward the contract to alice@example.com",
            tenant="test-tenant",
            user_id="user1",
        )

        assert plan.intent.verb == "forward"
        assert len(plan.steps) == 1
        assert plan.steps[0].action == "message.forward"
        assert plan.steps[0].graph_id == "msg-123"
        assert "alice@example.com" in plan.steps[0].payload["to"]

    def test_forward_no_message_error(self, mock_search, mock_resolve_contacts):
        """Test forward when message not found."""
        mock_search.return_value = []
        mock_resolve_contacts.return_value = []

        with pytest.raises(ValueError, match="Could not find message"):
            make_plan(
                "Forward something to alice",
                tenant="test-tenant",
                user_id="user1",
            )


class TestReplyPlanning:
    """Test reply action planning."""

    def test_reply_to_message(self, mock_search):
        """Test reply to message."""
        mock_search.return_value = [
            {
                "id": "msg-456",
                "type": "message",
                "title": "Bob Smith",
                "source": "teams",
            }
        ]

        plan = make_plan(
            'Reply to Bob\'s message with "Sounds good"',
            tenant="test-tenant",
            user_id="user1",
        )

        assert plan.intent.verb == "reply"
        assert len(plan.steps) == 1
        assert plan.steps[0].action == "message.reply"
        assert plan.steps[0].graph_id == "msg-456"
        assert "Sounds good" in plan.steps[0].payload["body"]

    def test_reply_no_message_error(self, mock_search):
        """Test reply when message not found."""
        mock_search.return_value = []

        with pytest.raises(ValueError, match="Could not find message"):
            make_plan(
                "Reply to nonexistent message",
                tenant="test-tenant",
                user_id="user1",
            )


class TestSchedulePlanning:
    """Test schedule action planning."""

    def test_schedule_meeting(self, mock_resolve_contacts):
        """Test schedule meeting."""
        from src.nl.ner_contacts import Contact

        mock_resolve_contacts.return_value = [
            Contact("Alice", "alice@example.com", "alice_id", "outlook", "c1"),
            Contact("Bob", "bob@example.com", "bob_id", "outlook", "c2"),
        ]

        plan = make_plan(
            "Schedule a meeting with Alice and Bob",
            tenant="test-tenant",
            user_id="user1",
        )

        assert plan.intent.verb == "schedule"
        assert len(plan.steps) == 1
        assert plan.steps[0].action == "event.create"
        assert "alice@example.com" in plan.steps[0].payload["attendees"]
        assert "bob@example.com" in plan.steps[0].payload["attendees"]


class TestFindPlanning:
    """Test find/search action planning."""

    def test_find_messages(self, mock_search):
        """Test find messages."""
        mock_search.return_value = [
            {"id": "msg-1", "title": "Message 1"},
            {"id": "msg-2", "title": "Message 2"},
        ]

        plan = make_plan(
            "Find messages from Alice",
            tenant="test-tenant",
            user_id="user1",
        )

        assert plan.intent.verb == "find"
        assert len(plan.steps) == 1
        assert plan.steps[0].action == "search.execute"
        assert len(plan.steps[0].payload["results"]) == 2

    def test_find_with_constraints(self, mock_search):
        """Test find with source and time constraints."""
        mock_search.return_value = []

        plan = make_plan(
            "Find messages in Teams from yesterday",
            tenant="test-tenant",
            user_id="user1",
        )

        # Search should have been called with constraints
        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args[1]
        assert call_kwargs["source"] == "teams"


class TestDeletePlanning:
    """Test delete action planning."""

    def test_delete_single_resource(self, mock_search):
        """Test delete single resource."""
        mock_search.return_value = [{"id": "msg-789", "type": "message", "title": "Old message"}]

        plan = make_plan(
            "Delete old message",
            tenant="test-tenant",
            user_id="user1",
        )

        assert plan.intent.verb == "delete"
        assert len(plan.steps) == 1
        assert plan.steps[0].action == "message.delete"
        assert plan.steps[0].graph_id == "msg-789"

    def test_delete_multiple_resources(self, mock_search):
        """Test delete multiple resources."""
        mock_search.return_value = [{"id": f"msg-{i}", "type": "message", "title": f"Message {i}"} for i in range(5)]

        plan = make_plan(
            "Delete old messages",
            tenant="test-tenant",
            user_id="user1",
        )

        assert len(plan.steps) == 5
        assert all(s.action == "message.delete" for s in plan.steps)


class TestCreatePlanning:
    """Test create action planning."""

    def test_create_page(self):
        """Test create page."""
        plan = make_plan(
            "Create a new page for project roadmap",
            tenant="test-tenant",
            user_id="user1",
        )

        assert plan.intent.verb == "create"
        assert len(plan.steps) == 1
        assert plan.steps[0].action == "page.create"
        assert "roadmap" in plan.steps[0].payload["title"].lower()


class TestUpdatePlanning:
    """Test update action planning."""

    def test_update_resource(self, mock_search):
        """Test update resource."""
        mock_search.return_value = [{"id": "page-1", "type": "page", "title": "Project Plan"}]

        plan = make_plan(
            "Update the project plan",
            tenant="test-tenant",
            user_id="user1",
        )

        assert plan.intent.verb == "update"
        assert len(plan.steps) == 1
        assert plan.steps[0].action == "page.update"
        assert plan.steps[0].graph_id == "page-1"


class TestRiskAssessment:
    """Test risk assessment and approval requirements."""

    def test_delete_is_high_risk(self, mock_search):
        """Test delete operations are high risk."""
        mock_search.return_value = [{"id": "msg-1", "type": "message", "title": "Message"}]

        plan = make_plan(
            "Delete the message",
            tenant="test-tenant",
            user_id="user1",
        )

        assert plan.risk_level == "high"
        assert plan.requires_approval is True

    def test_external_email_is_high_risk(self, mock_resolve_contacts):
        """Test external email is high risk."""
        from src.nl.ner_contacts import Contact

        # External domain (not in tenant domains)
        mock_resolve_contacts.return_value = [Contact("External", "external@external.com", "ext_id", "outlook", "c1")]

        plan = make_plan(
            "Email external@external.com",
            tenant="test-tenant",
            user_id="user1",
        )

        assert plan.risk_level in ["medium", "high"]
        # May require approval depending on config

    def test_bulk_operations_increase_risk(self, mock_search):
        """Test bulk operations increase risk."""
        # Return many resources
        mock_search.return_value = [{"id": f"msg-{i}", "type": "message", "title": f"Message {i}"} for i in range(15)]

        plan = make_plan(
            "Delete old messages",
            tenant="test-tenant",
            user_id="user1",
        )

        # High risk due to delete + bulk
        assert plan.risk_level == "high"
        assert plan.requires_approval is True

    def test_low_risk_operations(self, mock_search):
        """Test low risk operations."""
        mock_search.return_value = [
            {"id": "msg-1", "title": "Message 1"},
        ]

        plan = make_plan(
            "Find messages from Alice",
            tenant="test-tenant",
            user_id="user1",
        )

        assert plan.risk_level == "low"
        assert plan.requires_approval is False


class TestPlanPreview:
    """Test plan preview generation."""

    def test_preview_includes_command(self, mock_resolve_contacts, mock_contact):
        """Test preview includes original command."""
        mock_resolve_contacts.return_value = [mock_contact]

        plan = make_plan(
            "Email alice@example.com",
            tenant="test-tenant",
            user_id="user1",
        )

        assert "Email alice@example.com" in plan.preview

    def test_preview_includes_steps(self, mock_resolve_contacts, mock_contact):
        """Test preview includes step descriptions."""
        mock_resolve_contacts.return_value = [mock_contact]

        plan = make_plan(
            "Email alice@example.com",
            tenant="test-tenant",
            user_id="user1",
        )

        assert "Steps:" in plan.preview
        assert "Send email to Alice" in plan.preview

    def test_preview_includes_approval_warning(self, mock_search):
        """Test preview includes approval warning for high risk."""
        mock_search.return_value = [{"id": "msg-1", "type": "message", "title": "Message"}]

        plan = make_plan(
            "Delete the message",
            tenant="test-tenant",
            user_id="user1",
        )

        assert "APPROVAL REQUIRED" in plan.preview


class TestErrorHandling:
    """Test error handling in planner."""

    def test_invalid_command(self):
        """Test invalid command raises error."""
        with pytest.raises(ValueError, match="Could not parse"):
            make_plan(
                "Blah blah random text",
                tenant="test-tenant",
                user_id="user1",
            )

    def test_unsupported_verb(self):
        """Test unsupported verb raises error (if we add one)."""
        # Currently all verbs are supported, but test pattern
        pass
