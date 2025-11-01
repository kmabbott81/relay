"""Unit tests for AI Orchestrator schemas - Sprint 58 Slice 5.

Validates Pydantic schemas for AI action planning with strict validation.
Tests PlannedAction and PlanResult schemas from src.schemas.ai_plan.
"""

import pytest
from pydantic import ValidationError

from src.schemas.ai_plan import PlannedAction, PlanResult


class TestPlannedAction:
    """Tests for PlannedAction schema."""

    def test_valid_action(self):
        """Valid action passes validation."""
        action = PlannedAction(
            action_id="gmail.send",
            description="Send test email to user",
            params={"to": "user@example.com", "subject": "Test", "body": "Hello"},
        )

        assert action.action_id == "gmail.send"
        assert action.description == "Send test email to user"
        assert action.params["to"] == "user@example.com"
        assert action.depends_on is None

    def test_action_with_dependencies(self):
        """Action with depends_on field."""
        action = PlannedAction(
            action_id="calendar.create_event",
            description="Schedule follow-up meeting",
            params={"title": "Follow-up", "duration": 30},
            depends_on=[0, 1],
        )

        assert action.action_id == "calendar.create_event"
        assert action.depends_on == [0, 1]

    def test_missing_required_fields(self):
        """Missing required fields raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            PlannedAction(
                action_id="gmail.send",
                # Missing 'description' field
                params={},
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("description",) for e in errors)

    def test_empty_params_allowed(self):
        """Empty params dict is valid."""
        action = PlannedAction(
            action_id="system.healthcheck",
            description="Check system health",
            params={},
        )

        assert action.params == {}

    def test_complex_params(self):
        """Complex nested params are preserved."""
        action = PlannedAction(
            action_id="gmail.send",
            description="Send complex email with attachments",
            params={
                "to": ["user1@example.com", "user2@example.com"],
                "cc": ["cc@example.com"],
                "attachments": [{"name": "doc.pdf", "size": 1024}],
                "metadata": {"priority": "high", "tags": ["urgent", "sales"]},
            },
        )

        assert len(action.params["to"]) == 2
        assert action.params["metadata"]["priority"] == "high"

    def test_action_id_format_validation(self):
        """action_id must follow provider.action format (can have multiple dots)."""
        # Valid: simple format
        PlannedAction(
            action_id="gmail.send",
            description="Send email",
            params={},
        )

        # Valid: multiple dots are allowed (e.g., nested namespaces)
        PlannedAction(
            action_id="gmail.api.send",
            description="Send email",
            params={},
        )

        # Invalid: no dot separator
        with pytest.raises(ValidationError) as exc_info:
            PlannedAction(
                action_id="send_email",
                description="Send email",
                params={},
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("action_id",) for e in errors)

        # Invalid: uppercase not allowed
        with pytest.raises(ValidationError) as exc_info:
            PlannedAction(
                action_id="Gmail.Send",
                description="Send email",
                params={},
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("action_id",) for e in errors)

    def test_depends_on_validation(self):
        """depends_on indices must be non-negative."""
        # Valid: non-negative indices
        PlannedAction(
            action_id="task.create",
            description="Create task",
            params={},
            depends_on=[0, 1, 2],
        )

        # Invalid: negative index
        with pytest.raises(ValidationError) as exc_info:
            PlannedAction(
                action_id="task.create",
                description="Create task",
                params={},
                depends_on=[0, -1],
            )
        assert "non-negative" in str(exc_info.value)


class TestPlanResult:
    """Tests for PlanResult schema."""

    def test_valid_plan_minimal(self):
        """Valid minimal plan passes validation."""
        plan = PlanResult(
            prompt="Send email to ops team",
            intent="send_email",
            steps=[
                PlannedAction(
                    action_id="gmail.send",
                    description="Send email to ops team",
                    params={"to": "ops@example.com", "subject": "Test", "body": "Hello"},
                )
            ],
            confidence=0.95,
            explanation="Clear request with all required information",
        )

        assert plan.prompt == "Send email to ops team"
        assert plan.intent == "send_email"
        assert len(plan.steps) == 1
        assert plan.steps[0].action_id == "gmail.send"
        assert plan.confidence == 0.95

    def test_multi_step_plan(self):
        """Plan with multiple steps."""
        plan = PlanResult(
            prompt="Send email and create task",
            intent="send_email_and_create_task",
            steps=[
                PlannedAction(
                    action_id="gmail.send",
                    description="Send weekly report",
                    params={"to": "ops@example.com", "subject": "Weekly report", "body": "Attached"},
                ),
                PlannedAction(
                    action_id="task.create",
                    description="Create follow-up task",
                    params={"title": "Review report", "due": "2025-01-20"},
                    depends_on=[0],
                ),
            ],
            confidence=0.85,
            explanation="Multi-step workflow with dependency",
        )

        assert len(plan.steps) == 2
        assert plan.steps[0].action_id == "gmail.send"
        assert plan.steps[1].action_id == "task.create"
        assert plan.steps[1].depends_on == [0]

    def test_confidence_boundaries(self):
        """Confidence must be between 0.0 and 1.0."""
        # Valid boundaries
        PlanResult(
            prompt="Test",
            intent="test",
            steps=[PlannedAction(action_id="test.action", description="Test action", params={})],
            confidence=0.0,
            explanation="Low confidence",
        )

        PlanResult(
            prompt="Test",
            intent="test",
            steps=[PlannedAction(action_id="test.action", description="Test action", params={})],
            confidence=1.0,
            explanation="High confidence",
        )

        # Invalid: >1.0
        with pytest.raises(ValidationError) as exc_info:
            PlanResult(
                prompt="Test",
                intent="test",
                steps=[PlannedAction(action_id="test.action", description="Test action", params={})],
                confidence=1.5,
                explanation="Invalid confidence",
            )

        assert any("less than or equal to 1" in str(e["msg"]).lower() for e in exc_info.value.errors())

        # Invalid: <0.0
        with pytest.raises(ValidationError) as exc_info:
            PlanResult(
                prompt="Test",
                intent="test",
                steps=[PlannedAction(action_id="test.action", description="Test action", params={})],
                confidence=-0.1,
                explanation="Invalid confidence",
            )

        assert any("greater than or equal to 0" in str(e["msg"]).lower() for e in exc_info.value.errors())

    def test_empty_steps_list(self):
        """Plan with empty steps list is valid (for clarification requests)."""
        plan = PlanResult(
            prompt="What's the weather?",
            intent="clarification_needed",
            steps=[],
            confidence=0.5,
            explanation="Need more context to create actionable plan",
        )

        assert plan.steps == []

    def test_dependency_validation_forward_only(self):
        """Steps can only depend on earlier steps."""
        # Valid: step 1 depends on step 0
        PlanResult(
            prompt="Test",
            intent="test",
            steps=[
                PlannedAction(action_id="step.one", description="First step", params={}),
                PlannedAction(action_id="step.two", description="Second step", params={}, depends_on=[0]),
            ],
            confidence=0.9,
            explanation="Valid dependency chain",
        )

        # Invalid: step 1 depends on step 1 (self-reference)
        with pytest.raises(ValidationError) as exc_info:
            PlanResult(
                prompt="Test",
                intent="test",
                steps=[
                    PlannedAction(action_id="step.one", description="First step", params={}),
                    PlannedAction(action_id="step.two", description="Second step", params={}, depends_on=[1]),
                ],
                confidence=0.9,
                explanation="Invalid self-reference",
            )
        errors = exc_info.value.errors()
        assert len(errors) > 0  # Validation error occurred

        # Invalid: step 0 depends on step 1 (forward reference)
        with pytest.raises(ValidationError) as exc_info:
            PlanResult(
                prompt="Test",
                intent="test",
                steps=[
                    PlannedAction(action_id="step.one", description="First step", params={}, depends_on=[1]),
                    PlannedAction(action_id="step.two", description="Second step", params={}),
                ],
                confidence=0.9,
                explanation="Invalid forward reference",
            )
        errors = exc_info.value.errors()
        assert len(errors) > 0  # Validation error occurred

    def test_serialization_round_trip(self):
        """Plan can be serialized and deserialized."""
        plan = PlanResult(
            prompt="Send email to ops",
            intent="send_email",
            steps=[
                PlannedAction(
                    action_id="gmail.send",
                    description="Send email",
                    params={"to": "ops@example.com"},
                )
            ],
            confidence=0.95,
            explanation="Clear request",
        )

        # Serialize to dict
        plan_dict = plan.model_dump()

        # Deserialize from dict
        plan_restored = PlanResult(**plan_dict)

        assert plan_restored.prompt == plan.prompt
        assert plan_restored.intent == plan.intent
        assert plan_restored.confidence == plan.confidence
        assert len(plan_restored.steps) == len(plan.steps)

    def test_json_serialization(self):
        """Plan can be serialized to JSON."""
        plan = PlanResult(
            prompt="Send email and create task",
            intent="multi_step",
            steps=[
                PlannedAction(
                    action_id="gmail.send",
                    description="Send email",
                    params={"to": "ops@example.com"},
                ),
                PlannedAction(
                    action_id="task.create",
                    description="Create task",
                    params={"title": "Follow up"},
                ),
            ],
            confidence=0.88,
            explanation="Multi-step workflow",
        )

        # Serialize to JSON string
        json_str = plan.model_dump_json()

        assert "Send email and create task" in json_str
        assert "gmail.send" in json_str
        assert "task.create" in json_str

        # Deserialize from JSON
        plan_restored = PlanResult.model_validate_json(json_str)

        assert plan_restored.confidence == plan.confidence
        assert len(plan_restored.steps) == 2

    def test_missing_required_fields(self):
        """Missing required fields raises ValidationError.

        Note: 'steps' field is optional with default_factory=list, so it won't raise.
        Test missing truly required fields like 'prompt', 'intent', 'confidence', 'explanation'.
        """
        # Missing 'prompt' (truly required)
        with pytest.raises(ValidationError) as exc_info:
            PlanResult(
                # Missing 'prompt' field
                intent="test",
                steps=[],
                confidence=0.9,
                explanation="Test explanation",
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("prompt",) for e in errors)

    def test_optional_steps_field(self):
        """Steps field is optional with default_factory=list."""
        plan = PlanResult(
            prompt="Test",
            intent="test",
            # steps not provided - uses default empty list
            confidence=0.9,
            explanation="Test explanation",
        )

        assert plan.steps == []

    def test_legacy_aliases(self):
        """Legacy ActionStep and ActionPlan aliases work."""
        from src.schemas.ai_plan import ActionPlan, ActionStep

        # ActionStep is alias for PlannedAction
        step = ActionStep(
            action_id="gmail.send",
            description="Send email",
            params={"to": "test@example.com"},
        )
        assert step.action_id == "gmail.send"

        # ActionPlan is alias for PlanResult
        plan = ActionPlan(
            prompt="Test",
            intent="test",
            steps=[step],
            confidence=0.9,
            explanation="Test plan",
        )
        assert plan.prompt == "Test"
        assert len(plan.steps) == 1
