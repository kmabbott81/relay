"""Tests for blue/green deployment traffic manager."""

import json

import pytest

from relay_ai.deploy.traffic_manager import DeploymentError, DeploymentState, TrafficManager


@pytest.fixture
def traffic_manager(monkeypatch, tmp_path):
    """Create traffic manager with authorized role and temp log dir."""
    monkeypatch.setenv("DEPLOY_RBAC_ROLE", "Deployer")

    # Use temp directory for audit logs
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.chdir(tmp_path)

    return TrafficManager()


def test_traffic_manager_requires_authorized_role(monkeypatch):
    """Traffic manager raises PermissionError for unauthorized roles."""
    monkeypatch.setenv("DEPLOY_RBAC_ROLE", "Viewer")

    with pytest.raises(PermissionError, match="not authorized for deployments"):
        TrafficManager()


def test_traffic_manager_allows_deployer_role(monkeypatch, tmp_path):
    """Traffic manager allows Deployer role."""
    monkeypatch.setenv("DEPLOY_RBAC_ROLE", "Deployer")
    monkeypatch.chdir(tmp_path)

    manager = TrafficManager()
    assert manager.state == DeploymentState.IDLE


def test_traffic_manager_allows_admin_role(monkeypatch, tmp_path):
    """Traffic manager allows Admin role."""
    monkeypatch.setenv("DEPLOY_RBAC_ROLE", "Admin")
    monkeypatch.chdir(tmp_path)

    manager = TrafficManager()
    assert manager.state == DeploymentState.IDLE


def test_provision_green_from_idle(traffic_manager):
    """Can provision green deployment from idle state."""
    traffic_manager.provision_green("app:v2.0-green")

    assert traffic_manager.state == DeploymentState.GREEN_PROVISIONED
    assert traffic_manager.green_image == "app:v2.0-green"
    assert traffic_manager.canary_weight == 0


def test_provision_green_writes_audit_log(traffic_manager, tmp_path):
    """Provision green writes audit event to log file."""
    traffic_manager.provision_green("app:v2.0-green")

    audit_log = tmp_path / "logs" / "deploy_audit.log"
    assert audit_log.exists()

    events = [json.loads(line) for line in audit_log.read_text().splitlines()]
    assert len(events) == 1
    assert events[0]["action"] == "provision_green"
    assert events[0]["image_tag"] == "app:v2.0-green"


def test_start_canary_requires_green_provisioned(traffic_manager):
    """Start canary requires green_provisioned state."""
    with pytest.raises(DeploymentError, match="Cannot start canary from state"):
        traffic_manager.start_canary(10)


def test_start_canary_validates_weight_range(traffic_manager):
    """Start canary validates weight is 0-100."""
    traffic_manager.provision_green("app:v2.0-green")

    with pytest.raises(DeploymentError, match="Invalid canary weight"):
        traffic_manager.start_canary(150)


def test_start_canary_sets_weight_and_state(traffic_manager):
    """Start canary sets weight and transitions to canary state."""
    traffic_manager.provision_green("app:v2.0-green")
    traffic_manager.start_canary(10)

    assert traffic_manager.state == DeploymentState.CANARY
    assert traffic_manager.canary_weight == 10


def test_increase_weight_requires_canary_state(traffic_manager):
    """Increase weight requires canary state."""
    traffic_manager.provision_green("app:v2.0-green")

    with pytest.raises(DeploymentError, match="Cannot increase weight from state"):
        traffic_manager.increase_weight(20)


def test_increase_weight_must_be_greater_than_current(traffic_manager):
    """Increase weight must be greater than current weight."""
    traffic_manager.provision_green("app:v2.0-green")
    traffic_manager.start_canary(25)

    with pytest.raises(DeploymentError, match="must be greater than current"):
        traffic_manager.increase_weight(20)


def test_increase_weight_progression(traffic_manager):
    """Can increase weight progressively."""
    traffic_manager.provision_green("app:v2.0-green")
    traffic_manager.start_canary(10)

    traffic_manager.increase_weight(25)
    assert traffic_manager.canary_weight == 25

    traffic_manager.increase_weight(50)
    assert traffic_manager.canary_weight == 50

    traffic_manager.increase_weight(100)
    assert traffic_manager.canary_weight == 100


def test_promote_green_requires_canary_state(traffic_manager):
    """Promote green requires canary state."""
    traffic_manager.provision_green("app:v2.0-green")

    with pytest.raises(DeploymentError, match="Cannot promote green from state"):
        traffic_manager.promote_green()


def test_promote_green_transitions_to_green_live(traffic_manager):
    """Promote green transitions to green_live state."""
    traffic_manager.provision_green("app:v2.0-green")
    traffic_manager.start_canary(10)
    traffic_manager.increase_weight(100)
    traffic_manager.promote_green()

    assert traffic_manager.state == DeploymentState.GREEN_LIVE
    assert traffic_manager.blue_image == "app:v2.0-green"
    assert traffic_manager.canary_weight == 100


def test_rollback_to_blue_from_canary(traffic_manager):
    """Can rollback to blue from canary state."""
    traffic_manager.provision_green("app:v2.0-green")
    traffic_manager.start_canary(10)

    traffic_manager.rollback_to_blue("High error rate detected")

    assert traffic_manager.state == DeploymentState.IDLE
    assert traffic_manager.canary_weight == 0
    assert traffic_manager.green_image is None


def test_rollback_writes_audit_event_with_reason(traffic_manager, tmp_path):
    """Rollback writes audit event with reason."""
    traffic_manager.provision_green("app:v2.0-green")
    traffic_manager.start_canary(10)
    traffic_manager.rollback_to_blue("P95 latency exceeded threshold")

    audit_log = tmp_path / "logs" / "deploy_audit.log"
    events = [json.loads(line) for line in audit_log.read_text().splitlines()]

    rollback_event = [e for e in events if e["action"] == "rollback_to_blue"][0]
    assert rollback_event["reason"] == "P95 latency exceeded threshold"
    assert rollback_event["old_state"] == "canary"
    assert rollback_event["old_weight"] == 10


def test_get_status_returns_current_state(traffic_manager):
    """Get status returns current deployment state."""
    traffic_manager.provision_green("app:v2.0-green")
    traffic_manager.start_canary(25)

    status = traffic_manager.get_status()

    assert status["state"] == DeploymentState.CANARY
    assert status["green_image"] == "app:v2.0-green"
    assert status["canary_weight"] == 25
    assert status["traffic_split"]["blue"] == 75
    assert status["traffic_split"]["green"] == 25


def test_full_deployment_lifecycle(traffic_manager):
    """Test complete blue/green deployment lifecycle."""
    # Initial state
    assert traffic_manager.state == DeploymentState.IDLE

    # Provision green
    traffic_manager.provision_green("app:v2.0-green")
    assert traffic_manager.state == DeploymentState.GREEN_PROVISIONED

    # Start canary at 2%
    traffic_manager.start_canary(2)
    assert traffic_manager.canary_weight == 2

    # Increase to 10%
    traffic_manager.increase_weight(10)
    assert traffic_manager.canary_weight == 10

    # Increase to 25%
    traffic_manager.increase_weight(25)
    assert traffic_manager.canary_weight == 25

    # Increase to 50%
    traffic_manager.increase_weight(50)
    assert traffic_manager.canary_weight == 50

    # Increase to 100%
    traffic_manager.increase_weight(100)
    assert traffic_manager.canary_weight == 100

    # Promote to live
    traffic_manager.promote_green()
    assert traffic_manager.state == DeploymentState.GREEN_LIVE
    assert traffic_manager.blue_image == "app:v2.0-green"


def test_audit_log_contains_all_deployment_steps(traffic_manager, tmp_path):
    """Audit log captures all deployment steps."""
    traffic_manager.provision_green("app:v2.0-green")
    traffic_manager.start_canary(10)
    traffic_manager.increase_weight(50)
    traffic_manager.promote_green()

    audit_log = tmp_path / "logs" / "deploy_audit.log"
    events = [json.loads(line) for line in audit_log.read_text().splitlines()]

    actions = [e["action"] for e in events]
    assert "provision_green" in actions
    assert "start_canary" in actions
    assert "increase_weight" in actions
    assert "promote_green" in actions


def test_provision_green_from_green_live_moves_old_green_to_blue(traffic_manager):
    """Provisioning new green when green is live moves old green to blue."""
    # Deploy first version
    traffic_manager.provision_green("app:v2.0-green")
    traffic_manager.start_canary(10)
    traffic_manager.increase_weight(100)
    traffic_manager.promote_green()

    # Now deploy second version
    traffic_manager.provision_green("app:v3.0-green")

    assert traffic_manager.blue_image == "app:v2.0-green"
    assert traffic_manager.green_image == "app:v3.0-green"
    assert traffic_manager.state == DeploymentState.GREEN_PROVISIONED
