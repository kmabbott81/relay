"""Tests for OAuth state context management with replay protection.

Sprint 54: Test store_context() and validate_and_retrieve_context().
"""


from src.auth.oauth.state import store_context, validate_and_retrieve_context


def test_state_roundtrip_valid():
    """Test state roundtrip returns original context and prevents second use."""
    workspace_id = "ws_test_123"
    actor_id = "user_test_456"
    pkce_verifier = "test_verifier_abc"
    extra = {"provider": "google", "redirect_uri": "https://example.com/callback"}

    # Store context
    state = store_context(workspace_id, actor_id, pkce_verifier, extra, ttl_seconds=60)

    assert isinstance(state, str)
    assert len(state) > 20  # URL-safe base64

    # First retrieval should succeed
    context = validate_and_retrieve_context(state)

    assert context is not None
    assert context["workspace_id"] == workspace_id
    assert context["actor_id"] == actor_id
    assert context["pkce_verifier"] == pkce_verifier
    assert context["extra"] == extra
    assert "created_at" in context

    # Second retrieval should fail (replay protection)
    context2 = validate_and_retrieve_context(state)
    assert context2 is None


def test_state_invalid_or_expired():
    """Test invalid/expired state returns None."""
    # Invalid state
    invalid_state = "invalid_state_12345"
    context = validate_and_retrieve_context(invalid_state)
    assert context is None

    # Non-existent state
    nonexistent_state = "nonexistent_abc123xyz"
    context = validate_and_retrieve_context(nonexistent_state)
    assert context is None
