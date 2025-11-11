"""Tests for Natural Language Plan Executor."""

from unittest.mock import Mock, patch

import pytest

from relay_ai.nl.executor import execute_plan, resume_plan
from relay_ai.nl.intents import Intent
from relay_ai.nl.planner import ActionStep, Plan


@pytest.fixture
def mock_action_router():
    """Mock action router."""
    with patch("src.nl.executor.execute_action") as mock:
        mock.return_value = {"status": "success", "result": {}}
        yield mock


@pytest.fixture
def mock_checkpoints():
    """Mock checkpoint functions."""
    with patch("src.nl.executor.create_checkpoint") as mock_create, patch("src.nl.executor.get_checkpoint") as mock_get:
        mock_create.return_value = {
            "checkpoint_id": "chk-123",
            "status": "pending",
            "metadata": {},
        }
        mock_get.return_value = {
            "checkpoint_id": "chk-123",
            "status": "approved",
            "metadata": {
                "plan": {
                    "plan_id": "nlp-abc",
                    "intent": {"verb": "email", "original_command": "test"},
                    "steps": [],
                    "metadata": {},
                }
            },
        }
        yield mock_create, mock_get


@pytest.fixture
def mock_audit():
    """Mock audit logger."""
    with patch("src.nl.executor.AuditLogger") as mock:
        logger_instance = Mock()
        logger_instance.log.return_value = "audit-123"
        mock.return_value = logger_instance
        yield mock


@pytest.fixture
def simple_plan():
    """Create a simple test plan."""
    intent = Intent(
        verb="email",
        targets=["alice@example.com"],
        original_command="Email Alice",
    )

    step = ActionStep(
        action="contact.email",
        graph_id="contact-123",
        resource={"type": "contact", "title": "Alice"},
        payload={"subject": "Test", "body": "Hello"},
        description="Send email to Alice",
    )

    plan = Plan(
        plan_id="nlp-test-123",
        intent=intent,
        steps=[step],
        risk_level="low",
        requires_approval=False,
        preview="Test plan",
        metadata={"tenant": "test-tenant", "user_id": "user1"},
    )

    return plan


@pytest.fixture
def high_risk_plan():
    """Create a high-risk test plan requiring approval."""
    intent = Intent(
        verb="delete",
        original_command="Delete messages",
    )

    step = ActionStep(
        action="message.delete",
        graph_id="msg-123",
        resource={"type": "message", "title": "Message"},
        payload={},
        description="Delete message",
    )

    plan = Plan(
        plan_id="nlp-test-456",
        intent=intent,
        steps=[step],
        risk_level="high",
        requires_approval=True,
        preview="High risk plan",
        metadata={"tenant": "test-tenant", "user_id": "user1"},
    )

    return plan


class TestDryRun:
    """Test dry run execution."""

    def test_dry_run_returns_preview(self, simple_plan):
        """Test dry run returns preview without executing."""
        result = execute_plan(
            simple_plan,
            tenant="test-tenant",
            user_id="user1",
            dry_run=True,
        )

        assert result.status == "dry"
        assert len(result.results) == 1
        assert result.results[0]["preview"] == simple_plan.steps[0].description

    def test_dry_run_no_action_execution(self, simple_plan, mock_action_router):
        """Test dry run doesn't execute actions."""
        execute_plan(
            simple_plan,
            tenant="test-tenant",
            user_id="user1",
            dry_run=True,
        )

        # Action router should not be called
        mock_action_router.assert_not_called()


class TestApprovalGating:
    """Test approval checkpoint creation."""

    def test_high_risk_creates_checkpoint(self, high_risk_plan, mock_checkpoints, mock_audit):
        """Test high-risk plan creates checkpoint."""
        mock_create, _ = mock_checkpoints

        result = execute_plan(
            high_risk_plan,
            tenant="test-tenant",
            user_id="user1",
            dry_run=False,
        )

        assert result.status == "paused"
        assert result.checkpoint_id is not None
        mock_create.assert_called_once()

    def test_checkpoint_includes_plan_data(self, high_risk_plan, mock_checkpoints, mock_audit):
        """Test checkpoint includes plan data for resume."""
        mock_create, _ = mock_checkpoints

        result = execute_plan(
            high_risk_plan,
            tenant="test-tenant",
            user_id="user1",
            dry_run=False,
        )

        # Check checkpoint was created with correct data
        call_args = mock_create.call_args
        assert call_args[1]["tenant"] == "test-tenant"
        assert call_args[1]["prompt"] == high_risk_plan.preview

    def test_low_risk_skips_checkpoint(self, simple_plan, mock_action_router, mock_audit):
        """Test low-risk plan skips checkpoint."""
        result = execute_plan(
            simple_plan,
            tenant="test-tenant",
            user_id="user1",
            dry_run=False,
        )

        assert result.status == "success"
        assert result.checkpoint_id is None


class TestExecution:
    """Test plan execution."""

    def test_successful_execution(self, simple_plan, mock_action_router, mock_audit):
        """Test successful plan execution."""
        result = execute_plan(
            simple_plan,
            tenant="test-tenant",
            user_id="user1",
            dry_run=False,
        )

        assert result.status == "success"
        assert len(result.results) == 1
        assert result.results[0]["status"] == "success"

    def test_action_router_called(self, simple_plan, mock_action_router, mock_audit):
        """Test action router is called correctly."""
        execute_plan(
            simple_plan,
            tenant="test-tenant",
            user_id="user1",
            dry_run=False,
        )

        mock_action_router.assert_called_once()
        call_kwargs = mock_action_router.call_args[1]
        assert call_kwargs["user_id"] == "user1"
        assert call_kwargs["tenant"] == "test-tenant"

    def test_multiple_steps_executed(self, mock_action_router, mock_audit):
        """Test multiple steps are executed in order."""
        intent = Intent(verb="email", original_command="test")

        steps = [
            ActionStep(
                action="contact.email",
                graph_id=f"contact-{i}",
                resource={"type": "contact"},
                payload={},
                description=f"Step {i}",
            )
            for i in range(3)
        ]

        plan = Plan(
            plan_id="nlp-multi",
            intent=intent,
            steps=steps,
            requires_approval=False,
        )

        result = execute_plan(plan, tenant="test", user_id="user1", dry_run=False)

        assert result.status == "success"
        assert len(result.results) == 3
        assert mock_action_router.call_count == 3

    def test_search_step_handled(self, mock_audit):
        """Test search step (no action execution)."""
        intent = Intent(verb="find", original_command="test")

        step = ActionStep(
            action="search.execute",
            graph_id="search-result",
            resource={"type": "search"},
            payload={"results": [{"id": "1"}]},
            description="Search",
        )

        plan = Plan(
            plan_id="nlp-search",
            intent=intent,
            steps=[step],
            requires_approval=False,
        )

        result = execute_plan(plan, tenant="test", user_id="user1", dry_run=False)

        assert result.status == "success"
        assert result.results[0]["status"] == "success"


class TestErrorHandling:
    """Test error handling during execution."""

    def test_action_error_stops_execution(self, simple_plan, mock_action_router, mock_audit):
        """Test action error stops execution."""
        mock_action_router.side_effect = Exception("Action failed")

        result = execute_plan(
            simple_plan,
            tenant="test-tenant",
            user_id="user1",
            dry_run=False,
        )

        assert result.status == "error"
        assert "Action failed" in result.error

    def test_partial_execution_recorded(self, mock_action_router, mock_audit):
        """Test partial execution is recorded on error."""
        intent = Intent(verb="email", original_command="test")

        steps = [
            ActionStep(
                action="contact.email",
                graph_id=f"contact-{i}",
                resource={"type": "contact"},
                payload={},
                description=f"Step {i}",
            )
            for i in range(3)
        ]

        plan = Plan(
            plan_id="nlp-partial",
            intent=intent,
            steps=steps,
            requires_approval=False,
        )

        # First call succeeds, second fails
        mock_action_router.side_effect = [
            {"status": "success"},
            Exception("Failed"),
            {"status": "success"},
        ]

        result = execute_plan(plan, tenant="test", user_id="user1", dry_run=False)

        assert result.status == "error"
        # First step succeeded, second failed
        assert result.results[0]["status"] == "success"
        assert result.results[1]["status"] == "error"
        # Third step not executed
        assert len(result.results) == 2


class TestAuditLogging:
    """Test audit logging during execution."""

    def test_audit_events_logged(self, simple_plan, mock_action_router, mock_audit):
        """Test audit events are logged."""
        result = execute_plan(
            simple_plan,
            tenant="test-tenant",
            user_id="user1",
            dry_run=False,
        )

        assert len(result.audit_ids) > 0

    def test_audit_includes_steps(self, simple_plan, mock_action_router, mock_audit):
        """Test audit includes step execution."""
        result = execute_plan(
            simple_plan,
            tenant="test-tenant",
            user_id="user1",
            dry_run=False,
        )

        # Should have start, step, and completion audit events
        assert len(result.audit_ids) >= 2

    def test_audit_on_error(self, simple_plan, mock_action_router, mock_audit):
        """Test audit events logged on error."""
        mock_action_router.side_effect = Exception("Failed")

        result = execute_plan(
            simple_plan,
            tenant="test-tenant",
            user_id="user1",
            dry_run=False,
        )

        # Should still have audit events
        assert len(result.audit_ids) > 0


class TestResume:
    """Test resuming execution after approval."""

    def test_resume_after_approval(self, mock_checkpoints, mock_action_router, mock_audit):
        """Test resume after approval."""
        _, mock_get = mock_checkpoints

        result = resume_plan(
            checkpoint_id="chk-123",
            tenant="test-tenant",
            user_id="user1",
        )

        assert result.status == "success"
        mock_get.assert_called_once_with("chk-123")

    def test_resume_not_approved_error(self, mock_checkpoints):
        """Test resume fails if not approved."""
        _, mock_get = mock_checkpoints
        mock_get.return_value = {
            "checkpoint_id": "chk-123",
            "status": "pending",  # Not approved
        }

        with pytest.raises(ValueError, match="not approved"):
            resume_plan(
                checkpoint_id="chk-123",
                tenant="test-tenant",
                user_id="user1",
            )

    def test_resume_not_found_error(self, mock_checkpoints):
        """Test resume fails if checkpoint not found."""
        _, mock_get = mock_checkpoints
        mock_get.return_value = None

        with pytest.raises(ValueError, match="not found"):
            resume_plan(
                checkpoint_id="chk-123",
                tenant="test-tenant",
                user_id="user1",
            )


class TestExecutionHistory:
    """Test execution history retrieval."""

    def test_get_execution_history(self):
        """Test get execution history."""
        from src.nl.executor import get_execution_history

        # Should not raise error even if no history
        history = get_execution_history("test-tenant", limit=10)
        assert isinstance(history, list)
