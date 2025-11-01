"""
Tests for Secure Artifact I/O - Sprint 33B

Covers encrypted storage with classification labels and access control.
"""


import pytest

from src.storage.secure_io import (
    get_artifact_metadata,
    read_encrypted,
    write_encrypted,
)


@pytest.fixture
def temp_storage(tmp_path, monkeypatch):
    """Setup temporary storage and keyring."""
    storage_path = tmp_path / "artifacts"
    storage_path.mkdir()

    keyring_path = tmp_path / "keyring.jsonl"

    monkeypatch.setenv("STORAGE_BASE_PATH", str(storage_path))
    monkeypatch.setenv("KEYRING_PATH", str(keyring_path))
    monkeypatch.setenv("ENCRYPTION_ENABLED", "true")
    monkeypatch.setenv("DEFAULT_LABEL", "Internal")

    return storage_path


def test_write_encrypted_creates_files(temp_storage):
    """Test write_encrypted creates .enc and .json files."""
    artifact_path = temp_storage / "test.md"
    data = b"secret content"

    write_encrypted(artifact_path, data, "Confidential", "tenant-a")

    # Should create .enc and .json
    assert (temp_storage / "test.md.enc").exists()
    assert (temp_storage / "test.md.json").exists()


def test_write_encrypted_metadata(temp_storage):
    """Test write_encrypted creates correct metadata."""
    artifact_path = temp_storage / "test.md"
    data = b"content"

    meta = write_encrypted(artifact_path, data, "Confidential", "tenant-a")

    assert meta["label"] == "Confidential"
    assert meta["tenant"] == "tenant-a"
    assert meta["encrypted"] is True
    assert meta["size"] == len(data)
    assert "key_id" in meta
    assert "created_at" in meta


def test_read_encrypted_roundtrip(temp_storage):
    """Test write/read roundtrip with encryption."""
    artifact_path = temp_storage / "test.md"
    plaintext = b"secret data"

    write_encrypted(artifact_path, plaintext, "Internal", "tenant-a")
    decrypted = read_encrypted(artifact_path, "Internal")

    assert decrypted == plaintext


def test_read_encrypted_access_control(temp_storage):
    """Test read_encrypted enforces clearance."""
    artifact_path = temp_storage / "test.md"
    data = b"classified"

    write_encrypted(artifact_path, data, "Confidential", "tenant-a")

    # Should succeed with sufficient clearance
    decrypted = read_encrypted(artifact_path, "Confidential")
    assert decrypted == data

    # Should fail with insufficient clearance
    with pytest.raises(PermissionError, match="Insufficient clearance"):
        read_encrypted(artifact_path, "Internal")


def test_write_encrypted_label_fallback(temp_storage, monkeypatch):
    """Test write_encrypted uses DEFAULT_LABEL fallback."""
    monkeypatch.setenv("DEFAULT_LABEL", "Internal")

    artifact_path = temp_storage / "test.md"
    data = b"content"

    meta = write_encrypted(artifact_path, data, label=None, tenant="tenant-a")

    assert meta["label"] == "Internal"


def test_get_artifact_metadata(temp_storage):
    """Test get_artifact_metadata reads sidecar."""
    artifact_path = temp_storage / "test.md"
    data = b"content"

    write_encrypted(artifact_path, data, "Confidential", "tenant-a")
    meta = get_artifact_metadata(artifact_path)

    assert meta is not None
    assert meta["label"] == "Confidential"
    assert meta["tenant"] == "tenant-a"


def test_get_artifact_metadata_missing(temp_storage):
    """Test get_artifact_metadata returns None for missing sidecar."""
    artifact_path = temp_storage / "nonexistent.md"
    meta = get_artifact_metadata(artifact_path)

    assert meta is None


def test_write_encrypted_disabled(temp_storage, monkeypatch):
    """Test write_encrypted with encryption disabled."""
    monkeypatch.setenv("ENCRYPTION_ENABLED", "false")

    artifact_path = temp_storage / "test.md"
    data = b"plaintext"

    meta = write_encrypted(artifact_path, data, "Internal", "tenant-a")

    # Should create plaintext file
    assert artifact_path.exists()
    assert artifact_path.read_bytes() == data

    # Metadata should indicate not encrypted
    assert meta["encrypted"] is False

    # Sidecar should still exist
    assert (temp_storage / "test.md.json").exists()


def test_read_encrypted_plaintext_fallback(temp_storage, monkeypatch):
    """Test read_encrypted reads plaintext when encryption disabled."""
    monkeypatch.setenv("ENCRYPTION_ENABLED", "false")

    artifact_path = temp_storage / "test.md"
    data = b"plaintext"

    write_encrypted(artifact_path, data, "Internal", "tenant-a")
    read_data = read_encrypted(artifact_path, "Internal")

    assert read_data == data


def test_write_encrypted_creates_parent_dirs(temp_storage):
    """Test write_encrypted creates parent directories."""
    artifact_path = temp_storage / "subdir" / "nested" / "test.md"
    data = b"content"

    write_encrypted(artifact_path, data, "Internal", "tenant-a")

    assert artifact_path.parent.exists()
    assert (temp_storage / "subdir" / "nested" / "test.md.enc").exists()


def test_read_encrypted_missing_sidecar(temp_storage):
    """Test read_encrypted fails with missing sidecar."""
    artifact_path = temp_storage / "test.md"

    with pytest.raises(FileNotFoundError, match="Sidecar not found"):
        read_encrypted(artifact_path, "Internal")


def test_read_encrypted_missing_encrypted_file(temp_storage, monkeypatch):
    """Test read_encrypted fails with missing .enc file."""
    monkeypatch.setenv("ENCRYPTION_ENABLED", "true")

    artifact_path = temp_storage / "test.md"

    # Create sidecar but not .enc file
    import json

    sidecar_path = artifact_path.with_suffix(artifact_path.suffix + ".json")
    sidecar_path.write_text(
        json.dumps({"label": "Internal", "encrypted": True}),
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match="Encrypted artifact not found"):
        read_encrypted(artifact_path, "Internal")


def test_write_encrypted_empty_data(temp_storage):
    """Test write_encrypted with empty data."""
    artifact_path = temp_storage / "test.md"
    data = b""

    meta = write_encrypted(artifact_path, data, "Internal", "tenant-a")

    assert meta["size"] == 0

    decrypted = read_encrypted(artifact_path, "Internal")
    assert decrypted == b""


def test_write_encrypted_large_data(temp_storage):
    """Test write_encrypted with large data."""
    artifact_path = temp_storage / "test.md"
    data = b"x" * 1024 * 100  # 100 KB

    meta = write_encrypted(artifact_path, data, "Internal", "tenant-a")

    assert meta["size"] == len(data)

    decrypted = read_encrypted(artifact_path, "Internal")
    assert decrypted == data


def test_read_encrypted_higher_clearance_allowed(temp_storage):
    """Test read with clearance higher than label."""
    artifact_path = temp_storage / "test.md"
    data = b"public data"

    write_encrypted(artifact_path, data, "Public", "tenant-a")

    # All clearances should be able to read Public
    for clearance in ["Public", "Internal", "Confidential", "Restricted"]:
        decrypted = read_encrypted(artifact_path, clearance)
        assert decrypted == data


def test_read_encrypted_exact_clearance(temp_storage):
    """Test read with exact clearance match."""
    artifact_path = temp_storage / "test.md"
    data = b"restricted data"

    write_encrypted(artifact_path, data, "Restricted", "tenant-a")

    # Exact match should work
    decrypted = read_encrypted(artifact_path, "Restricted")
    assert decrypted == data
