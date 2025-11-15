"""
Integration tests for Sprint 34A: Collaborative Governance

Tests teams, workspaces, delegations, multi-sign checkpoints, team budgets, and rate limits.
"""

import json
import time
from datetime import UTC, datetime

import pytest


class TestTeamsWorkspaces:
    """Test teams and workspaces functionality."""

    def test_team_creation_and_membership(self, tmp_path, monkeypatch):
        """Test creating team and adding members."""
        monkeypatch.setenv("TEAMS_PATH", str(tmp_path / "teams.jsonl"))

        from relay_ai.security.teams import get_team_role, list_team_members, upsert_team_member

        # Create team with first member
        team = upsert_team_member("team-eng", "alice", "Admin", "Engineering")

        assert team["team_id"] == "team-eng"
        assert team["name"] == "Engineering"
        assert len(team["members"]) == 1
        assert team["members"][0] == {"user": "alice", "role": "Admin"}

        # Add second member
        upsert_team_member("team-eng", "bob", "Operator")

        # Verify membership
        assert get_team_role("alice", "team-eng") == "Admin"
        assert get_team_role("bob", "team-eng") == "Operator"
        assert get_team_role("charlie", "team-eng") is None

        # List members
        members = list_team_members("team-eng")
        assert len(members) == 2

    def test_workspace_creation_with_team(self, tmp_path, monkeypatch):
        """Test creating workspace under team."""
        monkeypatch.setenv("WORKSPACES_PATH", str(tmp_path / "workspaces.jsonl"))

        from relay_ai.security.workspaces import get_workspace_role, upsert_workspace_member

        # Create workspace
        workspace = upsert_workspace_member("ws-project-a", "alice", "Operator", "Project A", "team-eng")

        assert workspace["workspace_id"] == "ws-project-a"
        assert workspace["name"] == "Project A"
        assert workspace["team_id"] == "team-eng"
        assert get_workspace_role("alice", "ws-project-a") == "Operator"

    def test_require_team_role(self, tmp_path, monkeypatch):
        """Test role requirement enforcement."""
        monkeypatch.setenv("TEAMS_PATH", str(tmp_path / "teams.jsonl"))

        from relay_ai.security.teams import require_team_role, upsert_team_member

        upsert_team_member("team-eng", "alice", "Admin")
        upsert_team_member("team-eng", "bob", "Operator")

        # Alice (Admin) can pass Operator requirement
        require_team_role("alice", "team-eng", "Operator")  # Should not raise

        # Bob (Operator) cannot pass Admin requirement
        with pytest.raises(PermissionError, match="Admin is required"):
            require_team_role("bob", "team-eng", "Admin")


class TestDelegation:
    """Test time-bounded delegation system."""

    def test_grant_and_list_delegations(self, tmp_path, monkeypatch):
        """Test granting delegation and listing active ones."""
        monkeypatch.setenv("DELEGATIONS_PATH", str(tmp_path / "delegations.jsonl"))

        from relay_ai.security.delegation import grant_delegation, list_active_delegations

        # Grant delegation
        delegation = grant_delegation("alice", "bob", "team", "team-eng", "Operator", 24, "On-call")

        assert delegation["granter"] == "alice"
        assert delegation["grantee"] == "bob"
        assert delegation["role"] == "Operator"
        assert "delegation_id" in delegation

        # List active
        active = list_active_delegations("team", "team-eng")
        assert len(active) == 1
        assert active[0]["grantee"] == "bob"

    def test_delegation_expiry(self, tmp_path, monkeypatch):
        """Test delegation expiry checking."""
        monkeypatch.setenv("DELEGATIONS_PATH", str(tmp_path / "delegations.jsonl"))

        from relay_ai.security.delegation import grant_delegation, list_active_delegations

        # Grant short delegation (1 second)
        grant_delegation("alice", "bob", "team", "team-eng", "Operator", hours=1 / 3600, reason="Test")

        # Should be active now
        active = list_active_delegations("team", "team-eng", now=datetime.now(UTC))
        assert len(active) == 1

        # Should expire after 2 seconds
        # TODO(Sprint 45): replace with wait_until(...) for faster polling
        time.sleep(2)
        active = list_active_delegations("team", "team-eng", now=datetime.now(UTC))
        assert len(active) == 0

    def test_effective_role_with_delegation(self, tmp_path, monkeypatch):
        """Test effective role resolution with delegation."""
        monkeypatch.setenv("TEAMS_PATH", str(tmp_path / "teams.jsonl"))
        monkeypatch.setenv("DELEGATIONS_PATH", str(tmp_path / "delegations.jsonl"))

        from relay_ai.security.delegation import active_role_for, grant_delegation
        from relay_ai.security.teams import upsert_team_member

        # Bob is normally a Viewer
        upsert_team_member("team-eng", "bob", "Viewer")

        # Verify base role
        assert active_role_for("bob", "team", "team-eng") == "Viewer"

        # Grant Operator delegation
        grant_delegation("alice", "bob", "team", "team-eng", "Operator", 24, "Elevation")

        # Effective role should be elevated
        assert active_role_for("bob", "team", "team-eng") == "Operator"

    def test_revoke_delegation(self, tmp_path, monkeypatch):
        """Test revoking a delegation."""
        monkeypatch.setenv("DELEGATIONS_PATH", str(tmp_path / "delegations.jsonl"))

        from relay_ai.security.delegation import grant_delegation, list_active_delegations, revoke_delegation

        # Grant and revoke
        delegation = grant_delegation("alice", "bob", "team", "team-eng", "Operator", 24, "Test")
        delegation_id = delegation["delegation_id"]

        # Should be active
        active = list_active_delegations("team", "team-eng")
        assert len(active) == 1

        # Revoke
        assert revoke_delegation(delegation_id) is True

        # Should no longer be active
        active = list_active_delegations("team", "team-eng")
        assert len(active) == 0


class TestMultiSignCheckpoints:
    """Test multi-signature checkpoint approvals."""

    def test_create_multisign_checkpoint(self, tmp_path, monkeypatch):
        """Test creating checkpoint with multi-sign requirements."""
        monkeypatch.setenv("CHECKPOINTS_PATH", str(tmp_path / "checkpoints.jsonl"))

        from relay_ai.orchestrator.checkpoints import create_checkpoint, get_checkpoint

        checkpoint = create_checkpoint(
            checkpoint_id="chk-001",
            dag_run_id="run-123",
            task_id="deploy",
            tenant="acme",
            prompt="Approve deployment?",
            required_signers=["alice", "bob", "charlie"],
            min_signatures=2,
        )

        assert checkpoint["checkpoint_id"] == "chk-001"
        assert checkpoint["required_signers"] == ["alice", "bob", "charlie"]
        assert checkpoint["min_signatures"] == 2
        assert checkpoint["approvals"] == []

        # Verify retrieval
        retrieved = get_checkpoint("chk-001")
        assert retrieved is not None
        assert retrieved["min_signatures"] == 2

    def test_add_signatures(self, tmp_path, monkeypatch):
        """Test adding signatures to multi-sign checkpoint."""
        monkeypatch.setenv("CHECKPOINTS_PATH", str(tmp_path / "checkpoints.jsonl"))

        from relay_ai.orchestrator.checkpoints import add_signature, create_checkpoint

        # Create checkpoint
        create_checkpoint(
            "chk-002", "run-456", "deploy", "acme", "Deploy?", required_signers=["alice", "bob"], min_signatures=2
        )

        # Add first signature
        updated = add_signature("chk-002", "alice", {"comment": "LGTM"})
        assert len(updated["approvals"]) == 1
        assert updated["approvals"][0]["user"] == "alice"

        # Add second signature
        updated = add_signature("chk-002", "bob", {"comment": "Approved"})
        assert len(updated["approvals"]) == 2

        # Verify no duplicate signatures
        with pytest.raises(ValueError, match="already signed"):
            add_signature("chk-002", "alice", {})

    def test_is_satisfied(self, tmp_path, monkeypatch):
        """Test checking if checkpoint has sufficient signatures."""
        monkeypatch.setenv("CHECKPOINTS_PATH", str(tmp_path / "checkpoints.jsonl"))

        from relay_ai.orchestrator.checkpoints import add_signature, create_checkpoint, is_satisfied

        # Create 2-of-3 checkpoint
        create_checkpoint(
            "chk-003",
            "run-789",
            "deploy",
            "acme",
            "Deploy?",
            required_signers=["alice", "bob", "charlie"],
            min_signatures=2,
        )

        checkpoint = add_signature("chk-003", "alice", {})
        assert not is_satisfied(checkpoint)  # Only 1 of 2

        checkpoint = add_signature("chk-003", "bob", {})
        assert is_satisfied(checkpoint)  # 2 of 2 satisfied


class TestTeamBudgets:
    """Test team-level budget enforcement."""

    def test_team_budget_configuration(self, tmp_path, monkeypatch):
        """Test team budget retrieval."""
        # Use default budgets
        monkeypatch.setenv("TEAM_BUDGET_DAILY_DEFAULT", "15.0")
        monkeypatch.setenv("TEAM_BUDGET_MONTHLY_DEFAULT", "300.0")

        from relay_ai.cost.budgets import get_team_budget

        budget = get_team_budget("team-eng")
        assert budget["daily"] == 15.0
        assert budget["monthly"] == 300.0

    def test_team_budget_enforcement(self, tmp_path, monkeypatch):
        """Test team budget over-limit detection."""
        monkeypatch.setenv("TEAM_BUDGET_DAILY_DEFAULT", "10.0")

        from relay_ai.cost.budgets import is_over_team_budget

        # Under budget
        status = is_over_team_budget("team-eng", daily_spend=5.0, monthly_spend=50.0)
        assert not status["daily"]
        assert not status["monthly"]

        # Over daily budget
        status = is_over_team_budget("team-eng", daily_spend=15.0, monthly_spend=50.0)
        assert status["daily"]
        assert not status["monthly"]

    def test_team_spend_calculation(self, tmp_path, monkeypatch):
        """Test team spend calculation from ledger."""
        cost_events_path = tmp_path / "cost_events.jsonl"
        monkeypatch.setenv("COST_EVENTS_PATH", str(cost_events_path))

        from relay_ai.cost.ledger import load_cost_events, window_sum

        # Write cost events
        now = datetime.now(UTC)
        events = [
            {
                "timestamp": now.isoformat(),
                "tenant": "acme",
                "team_id": "team-eng",
                "cost_estimate": 2.5,
            },
            {
                "timestamp": now.isoformat(),
                "tenant": "acme",
                "team_id": "team-eng",
                "cost_estimate": 3.5,
            },
            {
                "timestamp": now.isoformat(),
                "tenant": "acme",
                "team_id": "team-ops",
                "cost_estimate": 5.0,
            },
        ]

        with open(cost_events_path, "w", encoding="utf-8") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        # Load and calculate
        loaded = load_cost_events()
        team_eng_spend = window_sum(loaded, team_id="team-eng", days=1)
        team_ops_spend = window_sum(loaded, team_id="team-ops", days=1)

        assert team_eng_spend == 6.0  # 2.5 + 3.5
        assert team_ops_spend == 5.0


class TestTeamRateLimiting:
    """Test team-level rate limiting."""

    def test_team_rate_limiter(self, monkeypatch):
        """Test rate limiter with team_id parameter."""
        monkeypatch.setenv("GLOBAL_QPS_LIMIT", "100")
        monkeypatch.setenv("TEAM_QPS_LIMIT", "2")
        monkeypatch.setenv("TENANT_QPS_LIMIT", "10")

        from relay_ai.queue.ratelimit import RateLimiter

        limiter = RateLimiter()

        # Verify team QPS configured
        assert limiter.team_qps == 2

        # Exhaust team bucket (capacity is 2x rate = 4 tokens)
        for i in range(4):
            result = limiter.allow("acme", tokens=1.0, team_id="team-eng")
            assert result is True, f"Request {i+1} should pass"

        # 5th request should be rate limited
        assert limiter.allow("acme", tokens=1.0, team_id="team-eng") is False


class TestIntegration:
    """End-to-end integration tests."""

    def test_full_governance_workflow(self, tmp_path, monkeypatch):
        """Test complete workflow with teams, delegation, and multi-sign."""
        # Setup paths
        monkeypatch.setenv("TEAMS_PATH", str(tmp_path / "teams.jsonl"))
        monkeypatch.setenv("DELEGATIONS_PATH", str(tmp_path / "delegations.jsonl"))
        monkeypatch.setenv("CHECKPOINTS_PATH", str(tmp_path / "checkpoints.jsonl"))

        from relay_ai.orchestrator.checkpoints import add_signature, create_checkpoint, is_satisfied
        from relay_ai.security.delegation import active_role_for, grant_delegation
        from relay_ai.security.teams import upsert_team_member

        # 1. Setup team
        upsert_team_member("team-eng", "alice", "Admin")
        upsert_team_member("team-eng", "bob", "Viewer")
        upsert_team_member("team-eng", "charlie", "Operator")

        # 2. Delegate Operator role to Bob
        grant_delegation("alice", "bob", "team", "team-eng", "Operator", 24, "On-call")

        # Verify Bob's effective role is elevated
        assert active_role_for("bob", "team", "team-eng") == "Operator"

        # 3. Create multi-sign checkpoint
        checkpoint = create_checkpoint(
            "chk-deploy",
            "run-001",
            "deploy_prod",
            "acme",
            "Approve production deployment",
            required_signers=["alice", "bob", "charlie"],
            min_signatures=2,
        )

        assert not is_satisfied(checkpoint)

        # 4. Add signatures
        checkpoint = add_signature("chk-deploy", "bob", {"comment": "Tests pass"})
        assert not is_satisfied(checkpoint)  # 1 of 2

        checkpoint = add_signature("chk-deploy", "charlie", {"comment": "LGTM"})
        assert is_satisfied(checkpoint)  # 2 of 2 - satisfied!


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
