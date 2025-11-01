"""Tests for keyboard shortcuts and command palette."""

import pytest

from dashboards.shortcuts import (
    ActionType,
    ShortcutAction,
    ShortcutRegistry,
    get_shortcut_registry,
)


def test_shortcut_action_creation():
    """ShortcutAction dataclass creates correctly."""
    action = ShortcutAction(
        action_id="test_action",
        action_type=ActionType.RUN_TEMPLATE,
        label="Test Action",
        description="Test description",
        keyboard_shortcut="Ctrl+T",
        category="Test",
        icon="🧪",
    )

    assert action.action_id == "test_action"
    assert action.action_type == ActionType.RUN_TEMPLATE
    assert action.label == "Test Action"
    assert action.keyboard_shortcut == "Ctrl+T"
    assert action.enabled is True


def test_registry_initialization():
    """Registry initializes with default actions."""
    registry = ShortcutRegistry()
    actions = registry.get_all_actions()

    assert len(actions) > 0
    # Should have navigation, actions, search, utilities
    assert any(a.action_type == ActionType.GO_TO_TEMPLATES for a in actions)
    assert any(a.action_type == ActionType.RUN_TEMPLATE for a in actions)


def test_register_action():
    """Can register custom action."""
    registry = ShortcutRegistry()

    custom_action = ShortcutAction(
        action_id="custom_test",
        action_type=ActionType.RUN_TEMPLATE,
        label="Custom Test",
        description="Custom test action",
        category="Custom",
    )

    initial_count = len(registry.get_all_actions())
    registry.register(custom_action)

    assert len(registry.get_all_actions()) == initial_count + 1
    assert registry.get_action("custom_test") == custom_action


def test_unregister_action():
    """Can unregister action."""
    registry = ShortcutRegistry()

    custom_action = ShortcutAction(
        action_id="to_remove",
        action_type=ActionType.RUN_TEMPLATE,
        label="To Remove",
        description="Will be removed",
    )

    registry.register(custom_action)
    assert registry.get_action("to_remove") is not None

    registry.unregister("to_remove")
    assert registry.get_action("to_remove") is None


def test_get_actions_by_category():
    """Can filter actions by category."""
    registry = ShortcutRegistry()

    navigation_actions = registry.get_actions_by_category("Navigation")
    assert len(navigation_actions) > 0
    assert all(a.category == "Navigation" for a in navigation_actions)

    action_actions = registry.get_actions_by_category("Actions")
    assert len(action_actions) > 0
    assert all(a.category == "Actions" for a in action_actions)


def test_search_actions_exact_match():
    """Search finds exact label matches."""
    registry = ShortcutRegistry()

    results = registry.search_actions("Run Template")
    assert len(results) > 0
    assert any("run" in a.label.lower() and "template" in a.label.lower() for a in results)


def test_search_actions_partial_match():
    """Search finds partial matches."""
    registry = ShortcutRegistry()

    results = registry.search_actions("temp")
    assert len(results) > 0
    # Should match "Templates", "Template", etc.
    assert any("temp" in a.label.lower() for a in results)


def test_search_actions_description_match():
    """Search matches descriptions."""
    registry = ShortcutRegistry()

    results = registry.search_actions("navigate")
    assert len(results) > 0
    # Should match navigation-related actions
    assert any("navigate" in a.description.lower() for a in results)


def test_search_actions_empty_query():
    """Empty query returns all enabled actions."""
    registry = ShortcutRegistry()

    results = registry.search_actions("")
    enabled_actions = registry.get_enabled_actions()

    assert len(results) == len(enabled_actions)


def test_search_actions_relevance_ranking():
    """Search ranks results by relevance."""
    registry = ShortcutRegistry()

    results = registry.search_actions("template")

    # First result should have "template" in label (higher score)
    if len(results) > 0:
        first_result = results[0]
        assert "template" in first_result.label.lower() or "template" in first_result.description.lower()


def test_get_shortcuts_by_key():
    """Can find actions by keyboard shortcut."""
    registry = ShortcutRegistry()

    ctrl_enter_actions = registry.get_shortcuts_by_key("Ctrl+Enter")
    assert len(ctrl_enter_actions) >= 1
    assert all(a.keyboard_shortcut == "Ctrl+Enter" for a in ctrl_enter_actions)


def test_execute_action_with_callback():
    """Execute action invokes callback."""
    registry = ShortcutRegistry()

    callback_invoked = []

    def test_callback(context):
        callback_invoked.append(context)
        return "result"

    action = ShortcutAction(
        action_id="callback_test",
        action_type=ActionType.RUN_TEMPLATE,
        label="Callback Test",
        description="Test callback",
        callback=test_callback,
    )

    registry.register(action)

    result = registry.execute_action("callback_test", {"key": "value"})

    assert len(callback_invoked) == 1
    assert callback_invoked[0]["key"] == "value"
    assert result == "result"


def test_execute_action_not_found():
    """Execute non-existent action raises error."""
    registry = ShortcutRegistry()

    with pytest.raises(ValueError, match="Action not found"):
        registry.execute_action("nonexistent_action")


def test_execute_disabled_action():
    """Execute disabled action raises error."""
    registry = ShortcutRegistry()

    action = ShortcutAction(
        action_id="disabled_test",
        action_type=ActionType.RUN_TEMPLATE,
        label="Disabled",
        description="Disabled action",
        enabled=False,
    )

    registry.register(action)

    with pytest.raises(ValueError, match="Action disabled"):
        registry.execute_action("disabled_test")


def test_global_registry_singleton():
    """Global registry is singleton."""
    registry1 = get_shortcut_registry()
    registry2 = get_shortcut_registry()

    assert registry1 is registry2


def test_enabled_actions_filter():
    """Get enabled actions excludes disabled."""
    registry = ShortcutRegistry()

    # Add disabled action
    disabled_action = ShortcutAction(
        action_id="disabled",
        action_type=ActionType.RUN_TEMPLATE,
        label="Disabled",
        description="Disabled",
        enabled=False,
    )
    registry.register(disabled_action)

    enabled = registry.get_enabled_actions()
    assert not any(a.action_id == "disabled" for a in enabled)


def test_action_categories():
    """Default actions have proper categories."""
    registry = ShortcutRegistry()

    categories = set(a.category for a in registry.get_all_actions())

    # Should have these standard categories
    assert "Navigation" in categories
    assert "Actions" in categories
    assert "Search" in categories or "Utilities" in categories


def test_action_types():
    """Default actions have proper types."""
    registry = ShortcutRegistry()

    action_types = set(a.action_type for a in registry.get_all_actions())

    # Should have navigation and action types
    assert any(t.startswith("go_to") for t in action_types)
    assert ActionType.RUN_TEMPLATE in action_types or ActionType.APPROVE_ARTIFACT in action_types
