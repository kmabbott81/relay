"""Tests for webhook approval handlers."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from relay_ai.webhooks import app

client = TestClient(app)


def create_test_artifact(artifact_id: str, status: str = "pending_approval") -> Path:
    """Helper to create a test artifact."""
    artifact_dir = Path("runs/test")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    artifact_path = artifact_dir / f"{artifact_id}.json"

    artifact_data = {
        "artifact_id": artifact_id,
        "timestamp": "2025-10-01T12:00:00",
        "result": {"status": status, "provider": "openai/gpt-4o", "text": "Test content", "reason": "Test reason"},
    }

    artifact_path.write_text(json.dumps(artifact_data, indent=2), encoding="utf-8")

    return artifact_path


def test_root_endpoint():
    """Root endpoint returns webhook info."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "endpoints" in data


def test_approve_artifact():
    """Approve action updates artifact status to published."""
    artifact_id = "test-approve-123"
    artifact_path = create_test_artifact(artifact_id, status="pending_approval")

    try:
        response = client.post(
            "/webhooks/approval",
            json={"artifact_id": artifact_id, "action": "approve", "user": "test-user"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["artifact_id"] == artifact_id
        assert data["new_status"] == "published"

        # Verify artifact updated
        artifact_data = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert artifact_data["result"]["status"] == "published"

    finally:
        artifact_path.unlink(missing_ok=True)


def test_reject_artifact():
    """Reject action updates artifact status to advisory_only."""
    artifact_id = "test-reject-456"
    artifact_path = create_test_artifact(artifact_id, status="pending_approval")

    try:
        response = client.post(
            "/webhooks/approval",
            json={"artifact_id": artifact_id, "action": "reject", "reason": "Not good enough", "user": "test-user"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["artifact_id"] == artifact_id
        assert data["new_status"] == "advisory_only"

        # Verify artifact updated
        artifact_data = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert artifact_data["result"]["status"] == "advisory_only"
        assert "Not good enough" in artifact_data["result"]["reason"]

    finally:
        artifact_path.unlink(missing_ok=True)


def test_invalid_action():
    """Invalid action returns 400 error."""
    response = client.post(
        "/webhooks/approval",
        json={"artifact_id": "test-789", "action": "invalid"},
    )

    assert response.status_code == 400


def test_artifact_not_found():
    """Non-existent artifact returns error."""
    response = client.post(
        "/webhooks/approval",
        json={"artifact_id": "nonexistent-artifact", "action": "approve"},
    )

    assert response.status_code == 200  # Returns success=false
    data = response.json()

    assert data["success"] is False
    assert "not found" in data["error"].lower()


def test_approval_history():
    """Approval actions add to history."""
    artifact_id = "test-history-999"
    artifact_path = create_test_artifact(artifact_id, status="pending_approval")

    try:
        # First approve
        client.post(
            "/webhooks/approval",
            json={"artifact_id": artifact_id, "action": "approve"},
        )

        # Check history
        artifact_data = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert "approval_history" in artifact_data
        assert len(artifact_data["approval_history"]) == 1
        assert artifact_data["approval_history"][0]["action"] == "approve"

    finally:
        artifact_path.unlink(missing_ok=True)


def test_slack_interactive_approve():
    """Slack interactive message callback approves artifact."""
    artifact_id = "test-slack-123"
    artifact_path = create_test_artifact(artifact_id, status="pending_approval")

    try:
        # Simulate Slack payload (form-encoded)
        slack_payload = {
            "actions": [{"action_id": "approve_artifact", "value": artifact_id}],
            "user": {"name": "testuser"},
        }

        response = client.post(
            "/webhooks/slack",
            data={"payload": json.dumps(slack_payload)},
        )

        assert response.status_code == 200
        data = response.json()

        assert "testuser" in data["text"]
        assert "approved" in data["text"].lower()

        # Verify artifact updated
        artifact_data = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert artifact_data["result"]["status"] == "published"

    finally:
        artifact_path.unlink(missing_ok=True)


def test_teams_actionable_approve():
    """Teams actionable message callback approves artifact."""
    artifact_id = "test-teams-456"
    artifact_path = create_test_artifact(artifact_id, status="pending_approval")

    try:
        response = client.post(
            "/webhooks/teams",
            json={"action": "approve", "artifact_id": artifact_id, "user": {"displayName": "Test User"}},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["type"] == "message"
        assert "approved" in data["text"].lower()

        # Verify artifact updated
        artifact_data = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert artifact_data["result"]["status"] == "published"

    finally:
        artifact_path.unlink(missing_ok=True)
