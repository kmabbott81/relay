"""Tests for Teams connector dry-run CRUD operations.

All tests are CI-safe (offline by default, no real API calls).
"""

import json

import pytest

from relay_ai.connectors.teams import TeamsConnector


@pytest.fixture
def teams_dryrun(monkeypatch, tmp_path):
    """Teams connector in DRY_RUN mode with mocked dependencies."""
    monkeypatch.setattr("src.connectors.base.get_team_role", lambda u, t: "Admin")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("LIVE", "false")
    monkeypatch.setenv("TEAMS_DEFAULT_TEAM_ID", "team-123")
    monkeypatch.setenv("TEAMS_DEFAULT_CHANNEL_ID", "channel-456")

    # Mock metrics path
    metrics_path = tmp_path / "metrics.jsonl"
    monkeypatch.setenv("CONNECTOR_METRICS_PATH", str(metrics_path))

    # Mock Teams mock data path
    mock_path = tmp_path / "teams_mock.jsonl"
    connector = TeamsConnector("teams", "tenant1", "user1")
    connector.mock_path = mock_path

    return connector


def test_teams_dryrun_list_resources(teams_dryrun):
    """Dry-run list operations return mock data."""
    assert isinstance(teams_dryrun.list_resources("teams"), list)
    assert isinstance(teams_dryrun.list_resources("channels", team_id="team-123"), list)
    assert isinstance(teams_dryrun.list_resources("messages", team_id="team-123", channel_id="channel-456"), list)


def test_teams_dryrun_get_resources(teams_dryrun):
    """Dry-run get operations return mock data."""
    assert isinstance(teams_dryrun.get_resource("teams", "team-123"), dict)
    assert isinstance(teams_dryrun.get_resource("channels", "channel-456", team_id="team-123"), dict)
    assert isinstance(
        teams_dryrun.get_resource("messages", "msg-789", team_id="team-123", channel_id="channel-456"), dict
    )


def test_teams_dryrun_crud_operations(teams_dryrun, monkeypatch):
    """Dry-run create/update/delete operations return mock responses."""
    # CRUD operations require Admin role
    monkeypatch.setenv("USER_ROLE", "Admin")

    payload = {"body": {"content": "Test message", "contentType": "text"}}

    # Create
    result = teams_dryrun.create_resource("messages", payload, team_id="team-123", channel_id="channel-456")
    assert isinstance(result, dict)

    # Update
    result = teams_dryrun.update_resource("messages", "msg-789", payload, team_id="team-123", channel_id="channel-456")
    assert isinstance(result, dict)

    # Delete
    result = teams_dryrun.delete_resource("messages", "msg-789", team_id="team-123", channel_id="channel-456")
    assert result is True


def test_teams_dryrun_metrics_recorded(teams_dryrun, monkeypatch, tmp_path):
    """Dry-run operations record metrics."""
    metrics_path = tmp_path / "metrics.jsonl"
    monkeypatch.setenv("CONNECTOR_METRICS_PATH", str(metrics_path))

    teams_dryrun.list_resources("teams")
    assert metrics_path.exists()

    with open(metrics_path, encoding="utf-8") as f:
        entry = json.loads(f.readline())
        assert entry["connector_id"] == "teams"
        assert entry["status"] == "success"
        assert "duration_ms" in entry


def test_teams_dryrun_no_real_api_calls(teams_dryrun):
    """Dry-run mode never makes real API calls."""
    assert teams_dryrun.dry_run is True
    assert isinstance(teams_dryrun.list_resources("teams"), list)


@pytest.mark.live
def test_teams_live_mode_requires_token(monkeypatch):
    """Live mode requires OAuth2 token (marked @pytest.mark.live)."""
    monkeypatch.setattr("src.connectors.base.get_team_role", lambda u, t: "Admin")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("LIVE", "true")

    connector = TeamsConnector("teams", "tenant1", "user1")

    # Should fail without token in live mode
    with pytest.raises(Exception, match="No OAuth2 token found"):
        connector.list_resources("teams")
