"""Tests for template cost projection and budget guards."""

from pathlib import Path

from relay_ai.templates import InputDef, TemplateDef, check_budget, estimate_template_cost


def create_simple_template(body: str = "Test {{name}}") -> TemplateDef:
    """Helper to create a simple template."""
    return TemplateDef(
        path=Path("test.yaml"),
        name="Test",
        version="1.0",
        description="Test",
        context="markdown",
        inputs=[InputDef(id="name", label="Name", type="string", default="World")],
        body=body,
    )


def test_cost_estimation_returns_structure():
    """Cost estimation should return expected structure."""
    template = create_simple_template()
    variables = {"name": "Alice"}

    result = estimate_template_cost(template, variables)

    assert "cost_usd" in result
    assert "tokens_estimated" in result
    assert "margin_pct" in result
    assert isinstance(result["cost_usd"], float)
    assert isinstance(result["tokens_estimated"], int)
    assert result["tokens_estimated"] > 0


def test_longer_template_costs_more():
    """Longer templates should have higher estimated costs."""
    short_template = create_simple_template("Hello {{name}}")
    long_template = create_simple_template("Hello {{name}}\n" + "More content. " * 100)

    variables = {"name": "Alice"}

    short_est = estimate_template_cost(short_template, variables)
    long_est = estimate_template_cost(long_template, variables)

    # Longer template should estimate more tokens
    assert long_est["tokens_estimated"] > short_est["tokens_estimated"]


def test_cost_estimation_with_margin():
    """Cost estimation should include conservative margin."""
    template = create_simple_template()
    variables = {"name": "Alice"}

    result = estimate_template_cost(template, variables)

    # Should have positive margin
    assert result["margin_pct"] > 0
    # Should have breakdown
    assert "breakdown" in result


def test_budget_check_within_budget():
    """Budget check should pass when within limits."""
    within_budget, warning, error = check_budget(
        estimated_cost=0.01, estimated_tokens=1000, budget_usd=0.05, budget_tokens=5000
    )

    assert within_budget is True
    assert error == ""


def test_budget_check_exceeds_usd():
    """Budget check should fail when USD budget exceeded."""
    within_budget, warning, error = check_budget(
        estimated_cost=0.10, estimated_tokens=1000, budget_usd=0.05, budget_tokens=None
    )

    assert within_budget is False
    assert "exceeds budget" in error.lower()
    assert "$0.1" in error or "$0.10" in error


def test_budget_check_exceeds_tokens():
    """Budget check should fail when token budget exceeded."""
    within_budget, warning, error = check_budget(
        estimated_cost=0.01, estimated_tokens=10000, budget_usd=None, budget_tokens=5000
    )

    assert within_budget is False
    assert "exceeds budget" in error.lower()
    assert "10,000" in error or "10000" in error


def test_budget_check_warning_at_90_percent():
    """Budget check should warn at 90% threshold."""
    # 95% of budget
    within_budget, warning, error = check_budget(
        estimated_cost=0.095, estimated_tokens=1000, budget_usd=0.10, budget_tokens=None
    )

    assert within_budget is True
    assert error == ""
    assert warning != ""
    assert "95%" in warning


def test_budget_check_no_budget():
    """Budget check should pass when no budget set."""
    within_budget, warning, error = check_budget(
        estimated_cost=10.0, estimated_tokens=1000000, budget_usd=None, budget_tokens=None
    )

    assert within_budget is True
    assert error == ""
    assert warning == ""


def test_budget_check_zero_budget():
    """Budget check with zero budget should behave correctly."""
    within_budget, warning, error = check_budget(
        estimated_cost=0.01, estimated_tokens=1000, budget_usd=0.0, budget_tokens=None
    )

    # Zero budget means any cost exceeds
    assert within_budget is False
    assert "exceeds" in error.lower()


def test_budget_check_both_limits():
    """Budget check should handle both USD and token limits."""
    # Within both
    within_budget, warning, error = check_budget(
        estimated_cost=0.01, estimated_tokens=1000, budget_usd=0.05, budget_tokens=5000
    )
    assert within_budget is True

    # Exceeds USD
    within_budget, warning, error = check_budget(
        estimated_cost=0.10, estimated_tokens=1000, budget_usd=0.05, budget_tokens=5000
    )
    assert within_budget is False
    assert "$" in error

    # Exceeds tokens
    within_budget, warning, error = check_budget(
        estimated_cost=0.01, estimated_tokens=10000, budget_usd=0.05, budget_tokens=5000
    )
    assert within_budget is False
    assert "token" in error.lower()

    # Exceeds both
    within_budget, warning, error = check_budget(
        estimated_cost=0.10, estimated_tokens=10000, budget_usd=0.05, budget_tokens=5000
    )
    assert within_budget is False
    assert "$" in error and "token" in error.lower()


def test_cost_estimation_fallback():
    """Cost estimation should handle render failures gracefully."""
    # Template with undefined variable
    template = TemplateDef(
        path=Path("test.yaml"),
        name="Test",
        version="1.0",
        description="Test",
        context="markdown",
        inputs=[],
        body="{{undefined_var}}",
    )

    # Should not crash, should use template body length as fallback
    result = estimate_template_cost(template, {})

    assert "cost_usd" in result
    assert result["tokens_estimated"] > 0
