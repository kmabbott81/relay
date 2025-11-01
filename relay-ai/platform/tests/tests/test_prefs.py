"""Tests for user preferences with RBAC and tenant isolation."""


import pytest

from src.prefs import (
    PrefsAuthorizationError,
    PrefsValidationError,
    delete_pref,
    get_favorite_templates,
    get_prefs,
    is_template_favorite,
    set_pref,
    toggle_favorite_template,
)
from src.security.authz import Principal, Role


def test_set_and_get_pref_same_tenant():
    """Can set and get preferences for same tenant."""
    user_id = "user1"
    tenant_id = "tenant1"
    principal = Principal(user_id=user_id, tenant_id=tenant_id, role=Role.EDITOR)

    # Set a preference
    set_pref(user_id, tenant_id, "default_preset", "production", principal)

    # Get preferences
    prefs = get_prefs(user_id, tenant_id, principal)

    assert "default_preset" in prefs
    assert prefs["default_preset"] == "production"


def test_get_prefs_returns_empty_for_new_user():
    """Get prefs returns empty dict for new user."""
    user_id = "newuser"
    tenant_id = "tenant1"
    principal = Principal(user_id=user_id, tenant_id=tenant_id, role=Role.VIEWER)

    prefs = get_prefs(user_id, tenant_id, principal)

    assert prefs == {}


def test_set_pref_json_encoding():
    """Preferences are JSON-encoded automatically."""
    user_id = "user2"
    tenant_id = "tenant1"
    principal = Principal(user_id=user_id, tenant_id=tenant_id, role=Role.EDITOR)

    # Set a list preference
    templates = ["template1", "template2", "template3"]
    set_pref(user_id, tenant_id, "favorite_templates", templates, principal)

    # Get and verify
    prefs = get_prefs(user_id, tenant_id, principal)
    assert prefs["favorite_templates"] == templates


def test_set_pref_invalid_key():
    """Setting invalid preference key raises error."""
    user_id = "user3"
    tenant_id = "tenant1"
    principal = Principal(user_id=user_id, tenant_id=tenant_id, role=Role.EDITOR)

    with pytest.raises(PrefsValidationError, match="Invalid preference key"):
        set_pref(user_id, tenant_id, "invalid_key", "value", principal)


def test_set_pref_value_too_large():
    """Setting oversized preference value raises error."""
    user_id = "user4"
    tenant_id = "tenant1"
    principal = Principal(user_id=user_id, tenant_id=tenant_id, role=Role.EDITOR)

    # Try to set a theme longer than 256 bytes
    large_value = "x" * 300

    with pytest.raises(PrefsValidationError, match="exceeds max size"):
        set_pref(user_id, tenant_id, "theme", large_value, principal)


def test_cross_tenant_read_blocked():
    """Cannot read preferences from another tenant."""
    user_id = "user5"
    tenant_id = "tenant1"
    other_tenant = "tenant2"

    # Set pref in tenant1
    principal1 = Principal(user_id=user_id, tenant_id=tenant_id, role=Role.EDITOR)
    set_pref(user_id, tenant_id, "theme", "dark", principal1)

    # Try to read from tenant2 (should be blocked by RBAC)
    principal2 = Principal(user_id=user_id, tenant_id=other_tenant, role=Role.VIEWER)

    with pytest.raises(PrefsAuthorizationError, match="cannot read prefs"):
        get_prefs(user_id, tenant_id, principal2)


def test_cross_tenant_write_blocked():
    """Cannot write preferences to another tenant."""
    user_id = "user6"
    tenant_id = "tenant1"
    other_tenant = "tenant2"

    # Try to write to tenant1 as tenant2 user
    principal = Principal(user_id=user_id, tenant_id=other_tenant, role=Role.EDITOR)

    with pytest.raises(PrefsAuthorizationError, match="cannot write prefs"):
        set_pref(user_id, tenant_id, "theme", "light", principal)


def test_delete_pref():
    """Can delete a preference."""
    user_id = "user7"
    tenant_id = "tenant1"
    principal = Principal(user_id=user_id, tenant_id=tenant_id, role=Role.ADMIN)

    # Set and verify
    set_pref(user_id, tenant_id, "layout", "grid", principal)
    prefs = get_prefs(user_id, tenant_id, principal)
    assert "layout" in prefs

    # Delete
    delete_pref(user_id, tenant_id, "layout", principal)

    # Verify deleted
    prefs = get_prefs(user_id, tenant_id, principal)
    assert "layout" not in prefs


def test_toggle_favorite_template_add():
    """Toggling favorite adds template to favorites."""
    user_id = "user8"
    tenant_id = "tenant1"
    template_slug = "template-abc"
    principal = Principal(user_id=user_id, tenant_id=tenant_id, role=Role.EDITOR)

    # Toggle on
    is_fav = toggle_favorite_template(user_id, tenant_id, template_slug, principal)

    assert is_fav is True

    # Verify in favorites
    favorites = get_favorite_templates(user_id, tenant_id, principal)
    assert template_slug in favorites


def test_toggle_favorite_template_remove():
    """Toggling favorite again removes template from favorites."""
    user_id = "user9"
    tenant_id = "tenant1"
    template_slug = "template-xyz"
    principal = Principal(user_id=user_id, tenant_id=tenant_id, role=Role.EDITOR)

    # Toggle on
    toggle_favorite_template(user_id, tenant_id, template_slug, principal)

    # Toggle off
    is_fav = toggle_favorite_template(user_id, tenant_id, template_slug, principal)

    assert is_fav is False

    # Verify not in favorites
    favorites = get_favorite_templates(user_id, tenant_id, principal)
    assert template_slug not in favorites


def test_is_template_favorite():
    """Can check if template is favorited."""
    user_id = "user10"
    tenant_id = "tenant1"
    template_slug = "template-check"
    principal = Principal(user_id=user_id, tenant_id=tenant_id, role=Role.EDITOR)

    # Initially not favorite
    assert is_template_favorite(user_id, tenant_id, template_slug, principal) is False

    # Add to favorites
    toggle_favorite_template(user_id, tenant_id, template_slug, principal)

    # Now is favorite
    assert is_template_favorite(user_id, tenant_id, template_slug, principal) is True


def test_multiple_users_isolated_prefs():
    """Different users have isolated preferences."""
    user1 = "user_a"
    user2 = "user_b"
    tenant_id = "tenant1"

    principal1 = Principal(user_id=user1, tenant_id=tenant_id, role=Role.EDITOR)
    principal2 = Principal(user_id=user2, tenant_id=tenant_id, role=Role.EDITOR)

    # User 1 sets theme
    set_pref(user1, tenant_id, "theme", "dark", principal1)

    # User 2 sets different theme
    set_pref(user2, tenant_id, "theme", "light", principal2)

    # Verify isolation
    prefs1 = get_prefs(user1, tenant_id, principal1)
    prefs2 = get_prefs(user2, tenant_id, principal2)

    assert prefs1["theme"] == "dark"
    assert prefs2["theme"] == "light"


def test_viewer_cannot_write_prefs():
    """Viewer role cannot write preferences (unless own prefs)."""
    user_id = "viewer_user"
    tenant_id = "tenant1"
    principal = Principal(user_id=user_id, tenant_id=tenant_id, role=Role.VIEWER)

    # Viewer can read own prefs
    prefs = get_prefs(user_id, tenant_id, principal)
    assert prefs == {}

    # Viewer cannot write (blocked by RBAC on CONFIG resource)
    with pytest.raises(PrefsAuthorizationError, match="cannot write prefs"):
        set_pref(user_id, tenant_id, "theme", "dark", principal)


def test_update_existing_pref():
    """Updating existing preference overwrites value."""
    user_id = "user11"
    tenant_id = "tenant1"
    principal = Principal(user_id=user_id, tenant_id=tenant_id, role=Role.ADMIN)

    # Set initial value
    set_pref(user_id, tenant_id, "default_preset", "staging", principal)

    # Update value
    set_pref(user_id, tenant_id, "default_preset", "production", principal)

    # Verify updated
    prefs = get_prefs(user_id, tenant_id, principal)
    assert prefs["default_preset"] == "production"


def test_favorites_list_handles_duplicates():
    """Toggling favorite twice doesn't create duplicates."""
    user_id = "user12"
    tenant_id = "tenant1"
    template_slug = "template-dup"
    principal = Principal(user_id=user_id, tenant_id=tenant_id, role=Role.EDITOR)

    # Toggle on twice
    toggle_favorite_template(user_id, tenant_id, template_slug, principal)
    toggle_favorite_template(user_id, tenant_id, template_slug, principal)  # Off

    # Toggle on again
    toggle_favorite_template(user_id, tenant_id, template_slug, principal)

    # Should only appear once
    favorites = get_favorite_templates(user_id, tenant_id, principal)
    assert favorites.count(template_slug) == 1
