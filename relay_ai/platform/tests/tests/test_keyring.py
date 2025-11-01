"""
Tests for Keyring Management - Sprint 33B

Covers keyring creation, rotation, and key retrieval.
"""

import json

import pytest

from src.crypto.keyring import active_key, get_key, list_keys, rotate_key


@pytest.fixture
def temp_keyring(tmp_path, monkeypatch):
    """Setup temporary keyring."""
    keyring_path = tmp_path / "keyring.jsonl"
    monkeypatch.setenv("KEYRING_PATH", str(keyring_path))
    return keyring_path


def test_keyring_auto_created(temp_keyring):
    """Test keyring is auto-created with initial key."""
    key = active_key()

    assert key["key_id"] == "key-001"
    assert key["alg"] == "AES256-GCM"
    assert key["status"] == "active"
    assert "key_material_base64" in key
    assert "created_at" in key


def test_active_key_returns_active(temp_keyring):
    """Test active_key returns only active key."""
    key = active_key()
    assert key["status"] == "active"


def test_get_key_by_id(temp_keyring):
    """Test get_key retrieves specific key."""
    active = active_key()
    key = get_key("key-001")

    assert key is not None
    assert key["key_id"] == "key-001"
    assert key["key_id"] == active["key_id"]


def test_get_key_not_found(temp_keyring):
    """Test get_key returns None for missing key."""
    key = get_key("key-999")
    assert key is None


def test_list_keys_deduplicated(temp_keyring):
    """Test list_keys returns deduplicated keys (last wins)."""
    # Create initial key
    active_key()

    # Rotate twice
    rotate_key()
    rotate_key()

    keys = list_keys()

    # Should have 3 keys (key-001 retired, key-002 retired, key-003 active)
    assert len(keys) == 3

    # Verify key-001 is retired
    key_001 = next(k for k in keys if k["key_id"] == "key-001")
    assert key_001["status"] == "retired"

    # Verify key-003 is active
    key_003 = next(k for k in keys if k["key_id"] == "key-003")
    assert key_003["status"] == "active"


def test_rotate_key_creates_new_active(temp_keyring):
    """Test key rotation creates new active key."""
    # Get initial key
    old_key = active_key()
    old_key_id = old_key["key_id"]

    # Rotate
    new_key = rotate_key()

    # Verify new key is different and active
    assert new_key["key_id"] != old_key_id
    assert new_key["status"] == "active"
    assert new_key["key_id"] == "key-002"


def test_rotate_key_retires_previous(temp_keyring):
    """Test key rotation retires previous active key."""
    # Create initial key
    active_key()

    # Rotate
    rotate_key()

    # Check old key is retired
    old_key = get_key("key-001")
    assert old_key["status"] == "retired"
    assert "retired_at" in old_key


def test_rotate_key_increments_id(temp_keyring):
    """Test key rotation increments key ID."""
    active_key()

    # Rotate multiple times
    key2 = rotate_key()
    assert key2["key_id"] == "key-002"

    key3 = rotate_key()
    assert key3["key_id"] == "key-003"


def test_rotate_key_idempotent_active(temp_keyring):
    """Test active_key returns latest after rotation."""
    active_key()
    rotate_key()
    rotate_key()

    current = active_key()
    assert current["key_id"] == "key-003"
    assert current["status"] == "active"


def test_keyring_file_format(temp_keyring):
    """Test keyring file is valid JSONL."""
    active_key()
    rotate_key()

    with open(temp_keyring) as f:
        lines = f.readlines()

    # Should have multiple entries (initial + retire + new)
    assert len(lines) >= 2

    # Each line should be valid JSON
    for line in lines:
        entry = json.loads(line)
        assert "key_id" in entry
        assert "status" in entry


def test_last_wins_semantics(temp_keyring):
    """Test last-wins semantics for key status."""
    # Create initial key
    active_key()

    # Manually write conflicting status
    with open(temp_keyring, "a") as f:
        f.write(json.dumps({"key_id": "key-001", "status": "compromised"}) + "\n")

    # get_key should return last entry
    key = get_key("key-001")
    assert key["status"] == "compromised"


def test_key_material_present(temp_keyring):
    """Test key material is base64 encoded."""
    key = active_key()

    import base64

    # Should be valid base64
    key_bytes = base64.b64decode(key["key_material_base64"])

    # Should be 32 bytes (256 bits) for AES-256
    assert len(key_bytes) == 32
