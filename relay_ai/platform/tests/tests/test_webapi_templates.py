"""Tests for web API templates and triage endpoints."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from relay_ai.webapi import app

client = TestClient(app)


def test_root_endpoint():
    """Root endpoint returns API info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "endpoints" in data
    assert "/api/templates" in data["endpoints"]["templates"]


def test_get_templates():
    """/api/templates returns non-empty list."""
    response = client.get("/api/templates")
    assert response.status_code == 200

    templates = response.json()
    assert isinstance(templates, list)
    assert len(templates) > 0  # Should have built-in templates

    # Check template structure
    template = templates[0]
    assert "name" in template
    assert "version" in template
    assert "description" in template
    assert "inputs" in template


@pytest.mark.bizlogic_asserts  # Sprint 52: Template render assertion failing
def test_render_template_valid():
    """/api/render returns HTML and creates artifact."""
    # First, get a template
    templates_response = client.get("/api/templates")
    templates = templates_response.json()
    template_name = templates[0]["name"]

    # Build minimal inputs
    inputs = {}
    for inp in templates[0]["inputs"]:
        if inp["required"]:
            if inp["type"] == "enum":
                inputs[inp["id"]] = inp["enum"][0]
            elif inp["type"] == "integer":
                inputs[inp["id"]] = 1
            else:
                inputs[inp["id"]] = "test value"

    # Render template
    response = client.post(
        "/api/render",
        json={"template_name": template_name, "inputs": inputs, "output_format": "html"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["html"] is not None
    assert len(data["html"]) > 0
    assert data["artifact_path"] is not None


def test_render_template_missing():
    """/api/render returns 404 for missing template."""
    response = client.post(
        "/api/render",
        json={"template_name": "NonexistentTemplate", "inputs": {}, "output_format": "html"},
    )

    assert response.status_code == 404


@pytest.mark.bizlogic_asserts  # Sprint 52: Template DOCX render assertion failing
def test_render_template_docx():
    """/api/render can return DOCX (base64)."""
    templates_response = client.get("/api/templates")
    templates = templates_response.json()
    template_name = templates[0]["name"]

    inputs = {}
    for inp in templates[0]["inputs"]:
        if inp["required"]:
            inputs[inp["id"]] = "test"

    response = client.post(
        "/api/render",
        json={"template_name": template_name, "inputs": inputs, "output_format": "docx"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["docx_base64"] is not None


@pytest.mark.bizlogic_asserts  # Sprint 52: Triage endpoint returning 500
def test_triage_content():
    """/api/triage returns artifact metadata."""
    response = client.post(
        "/api/triage",
        json={"content": "This is a test email content", "subject": "Test Subject", "from_email": "test@example.com"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["artifact_id"] is not None
    assert data["status"] in ("published", "advisory_only", "none")
    assert data["provider"] is not None
    assert data["preview"] is not None
    assert len(data["preview"]) > 0


@pytest.mark.bizlogic_asserts  # Sprint 52: Triage endpoint returning 500
def test_triage_creates_artifact():
    """/api/triage creates artifact file."""
    response = client.post(
        "/api/triage",
        json={"content": "Create artifact test", "subject": "Artifact Test"},
    )

    assert response.status_code == 200
    data = response.json()

    # Check artifact file exists
    artifact_path = Path(data["artifact_path"])
    assert artifact_path.exists()

    # Check artifact contents
    artifact_data = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact_data["artifact_id"] == data["artifact_id"]
    assert "result" in artifact_data


@pytest.mark.bizlogic_asserts  # Sprint 52: CORS headers not in OPTIONS response
def test_cors_headers():
    """API includes CORS headers for cross-origin requests."""
    response = client.options("/api/templates")

    # FastAPI CORS middleware adds these headers
    assert "access-control-allow-origin" in response.headers
