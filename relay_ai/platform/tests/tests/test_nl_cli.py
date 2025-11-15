"""Tests for Natural Language Command CLI."""

import json

# Import CLI functions
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.nl import cmd_dry, cmd_resume, cmd_run


@pytest.fixture
def mock_plan():
    """Mock plan object."""
    from relay_ai.nl.intents import Intent
    from relay_ai.nl.planner import ActionStep, Plan

    intent = Intent(
        verb="email",
        targets=["alice@example.com"],
        original_command="Email Alice",
    )

    step = ActionStep(
        action="contact.email",
        graph_id="contact-123",
        resource={"type": "contact"},
        payload={},
        description="Send email to Alice",
    )

    plan = Plan(
        plan_id="nlp-test-123",
        intent=intent,
        steps=[step],
        risk_level="low",
        requires_approval=False,
        preview="Email Alice\nSteps:\n  1. Send email to Alice",
    )

    return plan


@pytest.fixture
def mock_result_success(mock_plan):
    """Mock successful execution result."""
    from relay_ai.nl.executor import ExecutionResult

    return ExecutionResult(
        status="success",
        plan=mock_plan,
        results=[
            {
                "step": 0,
                "action": "contact.email",
                "status": "success",
                "description": "Send email to Alice",
            }
        ],
        audit_ids=["audit-123"],
    )


@pytest.fixture
def mock_result_paused(mock_plan):
    """Mock paused execution result."""
    from relay_ai.nl.executor import ExecutionResult

    return ExecutionResult(
        status="paused",
        plan=mock_plan,
        checkpoint_id="chk-123",
        audit_ids=["audit-123"],
    )


@pytest.fixture
def mock_result_dry(mock_plan):
    """Mock dry run result."""
    from relay_ai.nl.executor import ExecutionResult

    return ExecutionResult(
        status="dry",
        plan=mock_plan,
        results=[{"step": 0, "preview": "Send email to Alice"}],
    )


class TestDryCommand:
    """Test dry command."""

    @patch("scripts.nl.make_plan")
    @patch("scripts.nl.execute_plan")
    def test_dry_success(self, mock_execute, mock_make, mock_plan, mock_result_dry):
        """Test dry command success."""
        mock_make.return_value = mock_plan
        mock_execute.return_value = mock_result_dry

        args = Mock(
            command="Email Alice",
            tenant="test-tenant",
            user_id="user1",
            json=False,
        )

        exit_code = cmd_dry(args)

        assert exit_code == 0
        mock_make.assert_called_once_with(
            command="Email Alice",
            tenant="test-tenant",
            user_id="user1",
        )

    @patch("scripts.nl.make_plan")
    @patch("scripts.nl.execute_plan")
    def test_dry_json_output(self, mock_execute, mock_make, mock_plan, mock_result_dry, capsys):
        """Test dry command JSON output."""
        mock_make.return_value = mock_plan
        mock_execute.return_value = mock_result_dry

        args = Mock(
            command="Email Alice",
            tenant="test-tenant",
            user_id="user1",
            json=True,
        )

        exit_code = cmd_dry(args)

        assert exit_code == 0

        # Check JSON output
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["status"] == "dry"
        assert output["plan"]["plan_id"] == "nlp-test-123"

    @patch("scripts.nl.make_plan")
    def test_dry_error(self, mock_make):
        """Test dry command error."""
        mock_make.side_effect = ValueError("Invalid command")

        args = Mock(
            command="Invalid",
            tenant="test-tenant",
            user_id="user1",
            json=False,
        )

        exit_code = cmd_dry(args)

        assert exit_code == 1


class TestRunCommand:
    """Test run command."""

    @patch("scripts.nl.make_plan")
    @patch("scripts.nl.execute_plan")
    def test_run_success(self, mock_execute, mock_make, mock_plan, mock_result_success):
        """Test run command success."""
        mock_make.return_value = mock_plan
        mock_execute.return_value = mock_result_success

        args = Mock(
            command="Email Alice",
            tenant="test-tenant",
            user_id="user1",
            force=False,
            json=False,
        )

        exit_code = cmd_run(args)

        assert exit_code == 0
        mock_execute.assert_called_once()

    @patch("scripts.nl.make_plan")
    @patch("scripts.nl.execute_plan")
    def test_run_paused_for_approval(self, mock_execute, mock_make, mock_plan, mock_result_paused):
        """Test run command paused for approval."""
        mock_make.return_value = mock_plan
        mock_execute.return_value = mock_result_paused

        args = Mock(
            command="Delete messages",
            tenant="test-tenant",
            user_id="user1",
            force=False,
            json=False,
        )

        exit_code = cmd_run(args)

        assert exit_code == 3  # Paused exit code

    @patch("scripts.nl.make_plan")
    @patch("scripts.nl.execute_plan")
    def test_run_with_force(self, mock_execute, mock_make, mock_result_success):
        """Test run command with --force flag."""
        from relay_ai.nl.intents import Intent
        from relay_ai.nl.planner import ActionStep, Plan

        # Create high-risk plan
        intent = Intent(verb="delete", original_command="Delete")
        step = ActionStep(
            action="message.delete",
            graph_id="msg-123",
            resource={"type": "message"},
            payload={},
            description="Delete message",
        )
        high_risk_plan = Plan(
            plan_id="nlp-delete",
            intent=intent,
            steps=[step],
            requires_approval=True,
            risk_level="high",
        )

        mock_make.return_value = high_risk_plan
        mock_execute.return_value = mock_result_success

        args = Mock(
            command="Delete messages",
            tenant="test-tenant",
            user_id="user1",
            force=True,
            json=False,
        )

        exit_code = cmd_run(args)

        # Should succeed (force bypasses approval)
        assert exit_code == 0
        # Verify approval was bypassed
        assert not mock_make.return_value.requires_approval

    @patch("scripts.nl.make_plan")
    @patch("scripts.nl.execute_plan")
    def test_run_json_output(self, mock_execute, mock_make, mock_plan, mock_result_success, capsys):
        """Test run command JSON output."""
        mock_make.return_value = mock_plan
        mock_execute.return_value = mock_result_success

        args = Mock(
            command="Email Alice",
            tenant="test-tenant",
            user_id="user1",
            force=False,
            json=True,
        )

        exit_code = cmd_run(args)

        assert exit_code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["status"] == "success"
        assert output["steps_completed"] == 1

    @patch("scripts.nl.make_plan")
    def test_run_error(self, mock_make):
        """Test run command error."""
        mock_make.side_effect = Exception("Execution failed")

        args = Mock(
            command="Email Alice",
            tenant="test-tenant",
            user_id="user1",
            force=False,
            json=False,
        )

        exit_code = cmd_run(args)

        assert exit_code == 1

    @patch("scripts.nl.make_plan")
    def test_run_rbac_error(self, mock_make):
        """Test run command RBAC error."""
        mock_make.side_effect = Exception("RBAC permission denied")

        args = Mock(
            command="Email Alice",
            tenant="test-tenant",
            user_id="user1",
            force=False,
            json=False,
        )

        exit_code = cmd_run(args)

        assert exit_code == 2  # RBAC denied exit code


class TestResumeCommand:
    """Test resume command."""

    @patch("scripts.nl.resume_plan")
    def test_resume_success(self, mock_resume, mock_result_success):
        """Test resume command success."""
        mock_resume.return_value = mock_result_success

        args = Mock(
            checkpoint_id="chk-123",
            tenant="test-tenant",
            user_id="user1",
            json=False,
        )

        exit_code = cmd_resume(args)

        assert exit_code == 0
        mock_resume.assert_called_once_with(
            checkpoint_id="chk-123",
            tenant="test-tenant",
            user_id="user1",
        )

    @patch("scripts.nl.resume_plan")
    def test_resume_json_output(self, mock_resume, mock_result_success, capsys):
        """Test resume command JSON output."""
        mock_resume.return_value = mock_result_success

        args = Mock(
            checkpoint_id="chk-123",
            tenant="test-tenant",
            user_id="user1",
            json=True,
        )

        exit_code = cmd_resume(args)

        assert exit_code == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["status"] == "success"
        assert output["checkpoint_id"] == "chk-123"

    @patch("scripts.nl.resume_plan")
    def test_resume_error(self, mock_resume):
        """Test resume command error."""
        mock_resume.side_effect = ValueError("Checkpoint not found")

        args = Mock(
            checkpoint_id="chk-123",
            tenant="test-tenant",
            user_id="user1",
            json=False,
        )

        exit_code = cmd_resume(args)

        assert exit_code == 1


class TestExitCodes:
    """Test CLI exit codes."""

    def test_exit_code_success(self):
        """Test success exit code is 0."""
        # Tested in test_run_success, test_resume_success
        pass

    def test_exit_code_error(self):
        """Test error exit code is 1."""
        # Tested in test_run_error, test_resume_error
        pass

    def test_exit_code_rbac_denied(self):
        """Test RBAC denied exit code is 2."""
        # Tested in test_run_rbac_error
        pass

    def test_exit_code_paused(self):
        """Test paused exit code is 3."""
        # Tested in test_run_paused_for_approval
        pass
