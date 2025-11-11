"""Unit tests for AI Orchestrator security permissions - Sprint 58 Slice 5.

Tests action allowlist enforcement with:
- Basic allowlist checks
- Wildcard support (provider.*)
- Global denylist priority
- Permissive defaults
"""

import os
from unittest.mock import patch

import pytest

from relay_ai.security.permissions import (
    GLOBAL_ACTION_DENYLIST,
    add_to_denylist,
    can_execute,
    get_allowed_actions,
    is_action_globally_denied,
    remove_from_denylist,
)


@pytest.fixture(autouse=True)
def reset_denylist_and_env():
    """Reset global action denylist and environment before/after each test to prevent isolation issues."""
    # Save original denylist state
    original_denylist = GLOBAL_ACTION_DENYLIST.copy()
    GLOBAL_ACTION_DENYLIST.clear()

    # Save and clear ACTION_ALLOWLIST env var
    original_allowlist_env = os.environ.get("ACTION_ALLOWLIST")
    if "ACTION_ALLOWLIST" in os.environ:
        del os.environ["ACTION_ALLOWLIST"]

    yield

    # Restore original denylist
    GLOBAL_ACTION_DENYLIST.clear()
    GLOBAL_ACTION_DENYLIST.extend(original_denylist)

    # Restore original environment
    if original_allowlist_env is not None:
        os.environ["ACTION_ALLOWLIST"] = original_allowlist_env
    elif "ACTION_ALLOWLIST" in os.environ:
        del os.environ["ACTION_ALLOWLIST"]


class TestPermissions:
    """Tests for action permission checks."""

    def test_allowed_action(self):
        """Allowed action passes permission check."""
        with patch.dict(os.environ, {"ACTION_ALLOWLIST": "gmail.send,outlook.send"}, clear=False):
            assert can_execute("gmail.send") is True
            assert can_execute("outlook.send") is True

    def test_disallowed_action(self):
        """Disallowed action fails permission check."""
        with patch.dict(os.environ, {"ACTION_ALLOWLIST": "gmail.send"}, clear=False):
            assert can_execute("system.shutdown") is False
            assert can_execute("gmail.delete") is False

    def test_empty_allowlist_allows_all(self):
        """Empty allowlist allows all actions (permissive default)."""
        with patch.dict(os.environ, {"ACTION_ALLOWLIST": ""}, clear=False):
            # Permissive default: empty allowlist = allow all
            assert can_execute("gmail.send") is True
            assert can_execute("system.shutdown") is True
            assert can_execute("any.action") is True

    def test_no_env_var_allows_all(self):
        """No ACTION_ALLOWLIST env var allows all actions (permissive default)."""
        with patch.dict(os.environ, {}, clear=True):
            # Permissive default: no env var = allow all
            assert can_execute("gmail.send") is True
            assert can_execute("system.shutdown") is True

    def test_whitespace_handling(self):
        """Allowlist handles whitespace correctly."""
        with patch.dict(os.environ, {"ACTION_ALLOWLIST": " gmail.send , outlook.send "}, clear=False):
            assert can_execute("gmail.send") is True
            assert can_execute("outlook.send") is True

    def test_case_sensitive(self):
        """Action matching is case-sensitive."""
        with patch.dict(os.environ, {"ACTION_ALLOWLIST": "gmail.send"}, clear=False):
            assert can_execute("gmail.send") is True
            assert can_execute("GMAIL.SEND") is False
            assert can_execute("Gmail.Send") is False

    def test_wildcard_all_actions(self):
        """Wildcard '*' allows all actions."""
        with patch.dict(os.environ, {"ACTION_ALLOWLIST": "*"}, clear=False):
            assert can_execute("gmail.send") is True
            assert can_execute("outlook.send") is True
            assert can_execute("system.shutdown") is True
            assert can_execute("any.action") is True

    def test_provider_wildcard(self):
        """Provider-level wildcard (gmail.*) allows all gmail actions."""
        with patch.dict(os.environ, {"ACTION_ALLOWLIST": "gmail.*"}, clear=False):
            assert can_execute("gmail.send") is True
            assert can_execute("gmail.read") is True
            assert can_execute("gmail.delete") is True
            # Other providers not allowed
            assert can_execute("outlook.send") is False
            assert can_execute("calendar.create") is False

    def test_mixed_wildcard_and_explicit(self):
        """Mix of wildcards and explicit actions."""
        with patch.dict(os.environ, {"ACTION_ALLOWLIST": "gmail.*,outlook.send"}, clear=False):
            # gmail wildcard
            assert can_execute("gmail.send") is True
            assert can_execute("gmail.read") is True
            # explicit outlook.send
            assert can_execute("outlook.send") is True
            # outlook.read not allowed
            assert can_execute("outlook.read") is False

    def test_global_denylist_priority(self):
        """Global denylist takes priority over allowlist."""
        # Add to global denylist
        add_to_denylist("dangerous.action")

        try:
            # Even with wildcard allowlist
            with patch.dict(os.environ, {"ACTION_ALLOWLIST": "*"}, clear=False):
                assert can_execute("dangerous.action") is False
                assert can_execute("safe.action") is True

            # Even with provider wildcard
            with patch.dict(os.environ, {"ACTION_ALLOWLIST": "dangerous.*"}, clear=False):
                assert can_execute("dangerous.action") is False
                assert can_execute("dangerous.other") is True

            # Even with explicit allow
            with patch.dict(os.environ, {"ACTION_ALLOWLIST": "dangerous.action"}, clear=False):
                assert can_execute("dangerous.action") is False
        finally:
            # Cleanup
            remove_from_denylist("dangerous.action")

    def test_get_allowed_actions_empty(self):
        """get_allowed_actions returns ['*'] for empty allowlist."""
        with patch.dict(os.environ, {"ACTION_ALLOWLIST": ""}, clear=False):
            allowed = get_allowed_actions()
            assert allowed == ["*"]

    def test_get_allowed_actions_explicit(self):
        """get_allowed_actions returns explicit list."""
        with patch.dict(os.environ, {"ACTION_ALLOWLIST": "gmail.send,outlook.send"}, clear=False):
            allowed = get_allowed_actions()
            assert "gmail.send" in allowed
            assert "outlook.send" in allowed
            assert len(allowed) == 2

    def test_get_allowed_actions_with_denylist(self):
        """get_allowed_actions filters out globally denied actions."""
        add_to_denylist("gmail.delete")

        try:
            with patch.dict(os.environ, {"ACTION_ALLOWLIST": "gmail.send,gmail.delete"}, clear=False):
                allowed = get_allowed_actions()
                assert "gmail.send" in allowed
                assert "gmail.delete" not in allowed
        finally:
            remove_from_denylist("gmail.delete")

    def test_is_action_globally_denied(self):
        """is_action_globally_denied checks denylist correctly."""
        add_to_denylist("test.action")

        try:
            assert is_action_globally_denied("test.action") is True
            assert is_action_globally_denied("other.action") is False
        finally:
            remove_from_denylist("test.action")

    def test_add_remove_denylist(self):
        """add_to_denylist and remove_from_denylist work correctly."""
        action_id = "test.cleanup"

        # Initially not denied
        assert is_action_globally_denied(action_id) is False
        assert can_execute(action_id) is True

        # Add to denylist
        add_to_denylist(action_id)
        assert is_action_globally_denied(action_id) is True
        assert can_execute(action_id) is False

        # Remove from denylist
        remove_from_denylist(action_id)
        assert is_action_globally_denied(action_id) is False
        assert can_execute(action_id) is True

    def test_user_workspace_params_accepted(self):
        """can_execute accepts user_id and workspace_id parameters."""
        with patch.dict(os.environ, {"ACTION_ALLOWLIST": "gmail.send"}, clear=False):
            # These params don't affect logic yet (future RBAC)
            # but should be accepted without error
            assert can_execute("gmail.send", user_id="user_123") is True
            assert can_execute("gmail.send", workspace_id="ws_456") is True
            assert can_execute("gmail.send", user_id="user_123", workspace_id="ws_456") is True

    def test_invalid_action_format_handled(self):
        """Actions without provider.action format are handled gracefully."""
        with patch.dict(os.environ, {"ACTION_ALLOWLIST": "gmail.send"}, clear=False):
            # No dot separator - won't match allowlist
            assert can_execute("send") is False
            assert can_execute("send_email") is False

        # But allowed with empty allowlist (permissive default)
        with patch.dict(os.environ, {"ACTION_ALLOWLIST": ""}, clear=False):
            assert can_execute("send") is True
            assert can_execute("send_email") is True
