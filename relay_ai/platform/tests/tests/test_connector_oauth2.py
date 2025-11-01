"""Tests for OAuth2 token store."""

from datetime import datetime, timedelta

import pytest

from src.connectors.oauth2 import load_token, needs_refresh, save_token


@pytest.fixture
def temp_tokens(tmp_path, monkeypatch):
    """Temporary token file."""
    token_path = tmp_path / "tokens.jsonl"
    monkeypatch.setenv("OAUTH_TOKEN_PATH", str(token_path))
    return token_path


def test_save_token_creates_file(temp_tokens):
    """Saving token creates file."""
    save_token("test-conn", "access_token_123")

    assert temp_tokens.exists()


def test_load_token_not_found(temp_tokens):
    """Loading nonexistent token returns None."""
    token = load_token("nonexistent")

    assert token is None


def test_load_token_last_wins(temp_tokens):
    """Load returns latest token."""
    save_token("test-conn", "token_v1")
    save_token("test-conn", "token_v2")

    token = load_token("test-conn")

    assert token["access_token"] == "token_v2"


def test_needs_refresh_no_expiry():
    """Token without expiry doesn't need refresh."""
    token = {"access_token": "test"}

    assert needs_refresh(token) is False


def test_needs_refresh_expired():
    """Expired token needs refresh."""
    expires_at = (datetime.now() - timedelta(minutes=10)).isoformat()
    token = {"access_token": "test", "expires_at": expires_at}

    assert needs_refresh(token) is True


def test_needs_refresh_within_safety_window(monkeypatch):
    """Token expiring soon needs refresh."""
    monkeypatch.setenv("OAUTH_REFRESH_SAFETY_WINDOW_S", "600")

    expires_at = (datetime.now() + timedelta(minutes=5)).isoformat()
    token = {"access_token": "test", "expires_at": expires_at}

    assert needs_refresh(token) is True


def test_needs_refresh_safe():
    """Token not expiring soon doesn't need refresh."""
    expires_at = (datetime.now() + timedelta(hours=1)).isoformat()
    token = {"access_token": "test", "expires_at": expires_at}

    assert needs_refresh(token) is False
