"""Tests for template versioning and artifact tagging."""

import json
from pathlib import Path

from relay_ai.templates import InputDef, TemplateDef, create_template_artifact, to_slug


def test_template_has_version():
    """All templates should have a version field."""
    from relay_ai.templates import list_templates

    templates = list_templates()
    for tmpl in templates:
        assert tmpl.version, f"{tmpl.name} missing version"
        assert "." in tmpl.version, f"{tmpl.name} version should be X.Y format"


def test_version_format():
    """Version should be semantic version format."""
    from relay_ai.templates import list_templates

    templates = list_templates()
    for tmpl in templates:
        parts = tmpl.version.split(".")
        assert len(parts) == 2, f"{tmpl.name} version should be major.minor"
        assert all(p.isdigit() for p in parts), f"{tmpl.name} version should be numeric"


def test_artifact_includes_template_metadata():
    """Artifacts should include template name and version."""
    template = TemplateDef(
        path=Path("test.yaml"),
        name="Test Template",
        version="2.5",
        description="Test",
        context="markdown",
        inputs=[],
        body="Hello {{name}}",
    )

    artifact = create_template_artifact(
        template=template,
        variables={"name": "World"},
        rendered_body="Hello World",
        result={"status": "published", "provider": "test", "text": "output", "reason": "", "usage": []},
    )

    assert "template" in artifact
    assert artifact["template"]["name"] == "Test Template"
    assert artifact["template"]["version"] == "2.5"
    assert artifact["template"]["key"] == "test"
    assert artifact["template"]["context"] == "markdown"


def test_artifact_includes_provenance():
    """Artifacts should include provenance with rendered body and inputs."""
    template = TemplateDef(
        path=Path("test.yaml"),
        name="Test",
        version="1.0",
        description="Test",
        context="markdown",
        inputs=[InputDef(id="name", label="Name", type="string")],
        body="Hello {{name}}",
    )

    variables = {"name": "Alice"}
    rendered = "Hello Alice"

    artifact = create_template_artifact(
        template=template,
        variables=variables,
        rendered_body=rendered,
        result={"status": "published", "provider": "test", "text": "output", "reason": "", "usage": []},
    )

    assert "provenance" in artifact
    assert artifact["provenance"]["template_body"] == rendered
    assert artifact["provenance"]["resolved_inputs"] == variables
    assert "timestamp" in artifact["provenance"]


def test_artifact_includes_cost_projection():
    """Artifacts should include cost projection if provided."""
    template = TemplateDef(
        path=Path("test.yaml"),
        name="Test",
        version="1.0",
        description="Test",
        context="markdown",
        inputs=[],
        body="Test",
    )

    cost_projection = {"cost_usd": 0.0123, "tokens_estimated": 1500, "margin_pct": 50.0}

    artifact = create_template_artifact(
        template=template,
        variables={},
        rendered_body="Test",
        result={"status": "published", "provider": "test", "text": "output", "reason": "", "usage": []},
        cost_projection=cost_projection,
    )

    assert "cost_projection" in artifact
    assert artifact["cost_projection"]["cost_usd"] == 0.0123
    assert artifact["cost_projection"]["tokens_estimated"] == 1500


def test_filename_slugging():
    """Template names should be slugified for filenames."""
    assert to_slug("Meeting Recap") == "meeting-recap"
    assert to_slug("Class Brief (2-para + bullets)") == "class-brief-2-para-bullets"
    assert to_slug("Sales Follow-up") == "sales-follow-up"
    assert to_slug("Test & Demo!") == "test-demo"


def test_artifact_filename_convention(tmp_path):
    """Artifact filenames should follow {ts}-{template}-{status} convention."""
    # This is tested in the UI code, but we verify the slug function works
    template_key = "meeting_recap"
    status = "published"
    ts = 1633024800

    # Expected format: {ts}-{template}-{status}.json
    # Note: underscores in original names are preserved
    expected = f"{ts}-{to_slug(template_key)}-{to_slug(status)}.json"
    assert expected == "1633024800-meeting_recap-published.json"


def test_artifact_json_serializable():
    """Artifacts should be JSON serializable."""
    template = TemplateDef(
        path=Path("test.yaml"),
        name="Test",
        version="1.0",
        description="Test",
        context="markdown",
        inputs=[],
        body="Test",
    )

    artifact = create_template_artifact(
        template=template,
        variables={},
        rendered_body="Test",
        result={"status": "published", "provider": "test", "text": "output", "reason": "", "usage": []},
    )

    # Should not raise
    json_str = json.dumps(artifact)
    assert json_str

    # Should be parseable
    parsed = json.loads(json_str)
    assert parsed["template"]["name"] == "Test"
