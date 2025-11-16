"""
Keyring management for envelope encryption.

Sprint 33B: JSONL-based keyring with rotation support.
"""

import base64
import json
import os
from datetime import UTC, datetime
from pathlib import Path


def get_keyring_path() -> Path:
    """Get path to keyring JSONL file."""
    return Path(os.getenv("KEYRING_PATH", "logs/keyring.jsonl"))


def _ensure_keyring_exists():
    """Ensure keyring file exists, create if missing."""
    keyring_path = get_keyring_path()
    keyring_path.parent.mkdir(parents=True, exist_ok=True)

    if not keyring_path.exists():
        # Create initial key
        import secrets

        key_material = secrets.token_bytes(32)  # 256-bit key for AES-256
        key_b64 = base64.b64encode(key_material).decode("utf-8")

        initial_key = {
            "key_id": "key-001",
            "alg": "AES256-GCM",
            "created_at": datetime.now(UTC).isoformat(),
            "status": "active",
            "key_material_base64": key_b64,
        }

        with open(keyring_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(initial_key) + "\n")


def _read_keyring() -> list[dict]:
    """Read all keyring entries."""
    _ensure_keyring_exists()
    keyring_path = get_keyring_path()

    keys = []
    with open(keyring_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    keys.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    return keys


def active_key() -> dict:
    """
    Get the current active key.

    Returns:
        Key record with status='active'

    Raises:
        ValueError: If no active key found

    Example:
        >>> key = active_key()
        >>> key['key_id']
        'key-001'
        >>> key['alg']
        'AES256-GCM'
    """
    keys = _read_keyring()

    # Last active key wins (allows rotation to update status)
    active_keys = [k for k in keys if k.get("status") == "active"]

    if not active_keys:
        raise ValueError("No active key found in keyring")

    return active_keys[-1]


def get_key(key_id: str) -> dict | None:
    """
    Get specific key by ID.

    Args:
        key_id: Key identifier

    Returns:
        Key record or None if not found

    Example:
        >>> key = get_key("key-001")
        >>> key['status']
        'active'
    """
    keys = _read_keyring()

    # Last entry with matching key_id wins
    matches = [k for k in keys if k.get("key_id") == key_id]
    return matches[-1] if matches else None


def list_keys() -> list[dict]:
    """
    List all keys with their current status.

    Returns:
        List of key records (deduplicated by key_id, last wins)

    Example:
        >>> keys = list_keys()
        >>> len(keys)
        2
        >>> keys[0]['status']
        'retired'
    """
    keys = _read_keyring()

    # Deduplicate: last entry per key_id wins
    key_map = {}
    for key in keys:
        key_id = key.get("key_id")
        if key_id:
            key_map[key_id] = key

    return list(key_map.values())


def rotate_key() -> dict:
    """
    Rotate encryption key: create new active key and retire current one.

    Returns:
        New active key record

    Example:
        >>> new_key = rotate_key()
        >>> new_key['status']
        'active'
        >>> old_key = get_key("key-001")
        >>> old_key['status']
        'retired'
    """
    keyring_path = get_keyring_path()
    _ensure_keyring_exists()

    # Get current active key to retire it
    try:
        current = active_key()
        current_id = current["key_id"]
    except ValueError:
        # No active key, start fresh
        current_id = None

    # Retire current key
    if current_id:
        retire_event = {
            "key_id": current_id,
            "alg": current["alg"],
            "created_at": current["created_at"],
            "status": "retired",
            "retired_at": datetime.now(UTC).isoformat(),
            "key_material_base64": current["key_material_base64"],  # Keep key material for decryption
        }
        with open(keyring_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(retire_event) + "\n")

    # Generate new key
    import secrets

    key_material = secrets.token_bytes(32)  # 256-bit key
    key_b64 = base64.b64encode(key_material).decode("utf-8")

    # Determine new key_id
    existing_keys = list_keys()
    max_num = 0
    for key in existing_keys:
        key_id = key.get("key_id", "")
        if key_id.startswith("key-"):
            try:
                num = int(key_id.split("-")[1])
                max_num = max(max_num, num)
            except (IndexError, ValueError):
                pass

    new_key = {
        "key_id": f"key-{max_num + 1:03d}",
        "alg": "AES256-GCM",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "active",
        "key_material_base64": key_b64,
    }

    with open(keyring_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(new_key) + "\n")

    return new_key
