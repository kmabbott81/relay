"""Tests for policy pack validation and functionality."""

import json
from pathlib import Path
from typing import Any

import pytest

try:
    import jsonschema

    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False

from src.config import load_policy


def load_policy_schema() -> dict[str, Any]:
    """Load the policy JSON schema."""
    schema_path = Path("schemas/policy.json")
    with open(schema_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.skipif(not JSONSCHEMA_AVAILABLE, reason="jsonschema not available")
def test_policy_schema_validation():
    """Test that all policy files validate against schema."""
    schema = load_policy_schema()

    policies_dir = Path("policies")
    policy_files = list(policies_dir.glob("*.json"))

    assert len(policy_files) > 0, "No policy files found"

    for policy_file in policy_files:
        with open(policy_file, encoding="utf-8") as f:
            policy_data = json.load(f)

        # Validate against schema
        try:
            jsonschema.validate(policy_data, schema)
        except jsonschema.ValidationError as e:
            pytest.fail(f"Policy {policy_file.name} failed validation: {e.message}")


def test_policy_loading():
    """Test that policies can be loaded by name and path."""
    # Test loading by name
    models = load_policy("openai_only")
    assert isinstance(models, list)
    assert len(models) > 0
    assert all("openai/" in model for model in models)

    # Test loading by path
    models = load_policy("policies/openai_preferred.json")
    assert isinstance(models, list)
    assert len(models) > 0


def test_none_policy_forces_advisory():
    """Test that none.json policy forces advisory_only status."""
    from src.publish import select_publish_text
    from src.schemas import Draft, Judgment, ScoredDraft

    # Load none policy
    allowed_models = load_policy("none")
    assert len(allowed_models) == 0, "None policy should have empty allow list"

    # Create a mock judgment with a winning draft
    winning_draft = ScoredDraft(
        provider="openai/gpt-4o",
        answer="Test response content",
        evidence=["source 1", "source 2"],
        confidence=0.9,
        safety_flags=[],
        score=8.5,
        reasons="Good response",
        subscores={"task_fit": 4, "support": 3, "clarity": 1.5},
    )

    judgment = Judgment(ranked=[winning_draft], winner_provider="openai/gpt-4o")

    original_drafts = [
        Draft(
            provider="openai/gpt-4o",
            answer="Test response content",
            evidence=["source 1", "source 2"],
            confidence=0.9,
            safety_flags=[],
        )
    ]

    # Test publish selection with empty allow list
    status, provider, text, reason, _reason = select_publish_text(judgment, original_drafts, allowed_models)

    assert status == "advisory_only", f"Expected advisory_only, got {status}"
    assert provider == "openai/gpt-4o"
    assert text == "Test response content"
    assert "not in allowed list" in reason


def test_openai_only_policy():
    """Test openai_only policy contains only OpenAI models."""
    models = load_policy("openai_only")

    assert len(models) > 0
    for model in models:
        assert model.startswith("openai/"), f"Non-OpenAI model in openai_only policy: {model}"


def test_openai_preferred_policy():
    """Test openai_preferred policy contains OpenAI and other models."""
    models = load_policy("openai_preferred")

    assert len(models) > 0
    openai_models = [m for m in models if m.startswith("openai/")]
    other_models = [m for m in models if not m.startswith("openai/")]

    assert len(openai_models) > 0, "openai_preferred should contain OpenAI models"
    assert len(other_models) > 0, "openai_preferred should contain non-OpenAI models"


def test_policy_file_not_found():
    """Test handling of missing policy file."""
    with pytest.raises(FileNotFoundError):
        load_policy("nonexistent_policy")


def test_invalid_policy_format():
    """Test handling of invalid policy JSON format."""
    # Create a temporary invalid policy file
    invalid_policy_path = Path("policies/test_invalid.json")

    try:
        with open(invalid_policy_path, "w") as f:
            json.dump({"WRONG_KEY": ["openai/gpt-4o"]}, f)

        with pytest.raises(KeyError):
            load_policy("test_invalid")

    finally:
        # Clean up
        if invalid_policy_path.exists():
            invalid_policy_path.unlink()


@pytest.mark.skipif(not JSONSCHEMA_AVAILABLE, reason="jsonschema not available")
def test_policy_schema_structure():
    """Test that policy schema has required structure."""
    schema = load_policy_schema()

    assert schema["type"] == "object"
    assert "ALLOWED_PUBLISH_MODELS" in schema["required"]

    # Check ALLOWED_PUBLISH_MODELS property
    models_prop = schema["properties"]["ALLOWED_PUBLISH_MODELS"]
    assert models_prop["type"] == "array"
    assert models_prop["items"]["type"] == "string"
    assert models_prop["uniqueItems"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
