"""Tests for batch CSV template processing."""

import tempfile
from pathlib import Path

from src.templates import (
    InputDef,
    TemplateDef,
    estimate_batch_cost,
    load_csv_for_batch,
    process_batch_dry_run,
)


def create_test_template() -> TemplateDef:
    """Helper to create a test template."""
    return TemplateDef(
        path=Path("test.yaml"),
        name="Test Template",
        version="1.0",
        description="Test",
        context="markdown",
        inputs=[
            InputDef(id="name", label="Name", type="string", required=True),
            InputDef(id="email", label="Email", type="email", required=False),
        ],
        body="Hello {{name}}{% if email %} ({{email}}){% endif %}",
    )


def test_load_csv_valid_rows():
    """Should load valid CSV rows."""
    template = create_test_template()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("name,email\n")
        f.write("Alice,alice@example.com\n")
        f.write("Bob,bob@example.com\n")
        f.write("Charlie,charlie@example.com\n")
        csv_path = f.name

    try:
        rows, errors = load_csv_for_batch(csv_path, template)

        assert len(errors) == 0
        assert len(rows) == 3

        assert rows[0]["name"] == "Alice"
        assert rows[0]["email"] == "alice@example.com"
        assert rows[1]["name"] == "Bob"
        assert rows[2]["name"] == "Charlie"
    finally:
        Path(csv_path).unlink()


def test_load_csv_missing_required_column():
    """Should error if required column is missing."""
    template = create_test_template()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("email\n")  # Missing 'name' which is required
        f.write("alice@example.com\n")
        csv_path = f.name

    try:
        rows, errors = load_csv_for_batch(csv_path, template)

        assert len(errors) > 0
        assert "Missing required columns" in errors[0]
        assert "name" in errors[0]
    finally:
        Path(csv_path).unlink()


def test_load_csv_invalid_row_values():
    """Should report validation errors for invalid row values."""
    template = create_test_template()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("name,email\n")
        f.write("Alice,alice@example.com\n")
        f.write("Bob,invalid-email\n")  # Invalid email
        f.write(",charlie@example.com\n")  # Missing required name
        csv_path = f.name

    try:
        rows, errors = load_csv_for_batch(csv_path, template)

        # Only valid row should be loaded
        assert len(rows) == 1
        assert rows[0]["name"] == "Alice"

        # Should have errors for rows 3 and 4
        assert len(errors) == 2
        assert "Row 3" in errors[0]
        assert "Row 4" in errors[1]
    finally:
        Path(csv_path).unlink()


def test_load_csv_file_not_found():
    """Should error if CSV file doesn't exist."""
    template = create_test_template()

    rows, errors = load_csv_for_batch("nonexistent.csv", template)

    assert len(rows) == 0
    assert len(errors) == 1
    assert "not found" in errors[0].lower()


def test_estimate_batch_cost():
    """Should estimate total cost for all rows."""
    template = create_test_template()

    rows = [
        {"name": "Alice", "email": "alice@example.com"},
        {"name": "Bob", "email": "bob@example.com"},
        {"name": "Charlie", "email": "charlie@example.com"},
    ]

    batch_est = estimate_batch_cost(template, rows)

    assert batch_est["num_rows"] == 3
    assert batch_est["total_cost_usd"] > 0
    assert batch_est["total_tokens"] > 0
    assert len(batch_est["per_row_estimates"]) == 3


def test_estimate_batch_cost_empty():
    """Should handle empty row list."""
    template = create_test_template()

    batch_est = estimate_batch_cost(template, [])

    assert batch_est["num_rows"] == 0
    assert batch_est["total_cost_usd"] == 0
    assert batch_est["total_tokens"] == 0


def test_dry_run_within_budget():
    """Dry run should pass when within budget."""
    template = create_test_template()

    rows = [
        {"name": "Alice", "email": "alice@example.com"},
        {"name": "Bob", "email": "bob@example.com"},
    ]

    result = process_batch_dry_run(template, rows, budget_usd=1.0, budget_tokens=100000)

    assert result["num_rows"] == 2
    assert result["total_cost_usd"] > 0
    assert result["within_budget"] is True
    assert len(result["errors"]) == 0


def test_dry_run_exceeds_budget():
    """Dry run should fail when budget exceeded."""
    template = create_test_template()

    rows = [
        {"name": "Alice", "email": "alice@example.com"},
        {"name": "Bob", "email": "bob@example.com"},
        {"name": "Charlie", "email": "charlie@example.com"},
    ]

    # Set very low budget
    result = process_batch_dry_run(template, rows, budget_usd=0.001, budget_tokens=None)

    assert result["within_budget"] is False
    assert len(result["errors"]) > 0
    assert "exceeds budget" in result["errors"][0].lower()


def test_dry_run_warning_at_threshold():
    """Dry run should warn when approaching budget limit."""
    template = create_test_template()

    rows = [{"name": "Alice", "email": "alice@example.com"}]

    # Estimate cost first
    batch_est = estimate_batch_cost(template, rows)

    # Set budget to ~95% of estimated cost
    budget = batch_est["total_cost_usd"] / 0.95

    result = process_batch_dry_run(template, rows, budget_usd=budget, budget_tokens=None)

    assert result["within_budget"] is True
    assert len(result["warnings"]) > 0


def test_batch_csv_end_to_end():
    """End-to-end test: load CSV, validate, estimate cost."""
    template = create_test_template()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("name,email\n")
        f.write("Alice,alice@example.com\n")
        f.write("Bob,bob@example.com\n")
        f.write("Charlie,charlie@example.com\n")
        csv_path = f.name

    try:
        # Load CSV
        rows, errors = load_csv_for_batch(csv_path, template)
        assert len(errors) == 0
        assert len(rows) == 3

        # Estimate cost
        batch_est = estimate_batch_cost(template, rows)
        assert batch_est["num_rows"] == 3

        # Dry run with reasonable budget
        result = process_batch_dry_run(template, rows, budget_usd=1.0, budget_tokens=100000)
        assert result["within_budget"] is True
    finally:
        Path(csv_path).unlink()
