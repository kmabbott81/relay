"""
Secure artifact I/O with encryption and classification labels.

Sprint 33B: Encrypted storage with access control.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from relay_ai.classify.labels import can_access
from relay_ai.classify.policy import label_for_artifact
from relay_ai.crypto.envelope import decrypt, encrypt
from relay_ai.crypto.keyring import active_key


def is_encryption_enabled() -> bool:
    """Check if encryption is enabled via environment."""
    return os.getenv("ENCRYPTION_ENABLED", "false").lower() in ("true", "1", "yes")


def write_encrypted(path: Path, data: bytes, label: str | None = None, tenant: str | None = None) -> dict:
    """
    Write encrypted artifact with metadata sidecar.

    Args:
        path: Target path for encrypted artifact
        data: Raw bytes to encrypt
        label: Classification label (uses DEFAULT_LABEL if None)
        tenant: Tenant ID for isolation

    Returns:
        Metadata dict written to sidecar

    Side effects:
        - Creates path.enc with encrypted data (if encryption enabled)
        - Creates path.json with metadata sidecar
        - If encryption disabled, writes plaintext to path

    Example:
        >>> meta = write_encrypted(Path("artifact.md"), b"content", "Confidential", "acme")
        >>> meta['label']
        'Confidential'
        >>> Path("artifact.md.enc").exists()
        True
        >>> Path("artifact.md.json").exists()
        True
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # Determine effective label
    effective_label = label_for_artifact({"label": label})

    if is_encryption_enabled():
        # Encrypt data
        key = active_key()
        envelope = encrypt(data, key)

        # Write encrypted artifact
        enc_path = path.with_suffix(path.suffix + ".enc")
        enc_data = json.dumps(envelope).encode("utf-8")
        enc_path.write_bytes(enc_data)

        # Metadata
        metadata = {
            "label": effective_label,
            "tenant": tenant,
            "key_id": envelope["key_id"],
            "created_at": datetime.now(UTC).isoformat(),
            "size": len(data),
            "encrypted": True,
        }

        # Write sidecar
        sidecar_path = path.with_suffix(path.suffix + ".json")
        sidecar_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    else:
        # Write plaintext
        path.write_bytes(data)

        # Metadata
        metadata = {
            "label": effective_label,
            "tenant": tenant,
            "created_at": datetime.now(UTC).isoformat(),
            "size": len(data),
            "encrypted": False,
        }

        # Write sidecar
        sidecar_path = path.with_suffix(path.suffix + ".json")
        sidecar_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return metadata


def read_encrypted(path: Path, user_clearance: str) -> bytes:
    """
    Read and decrypt artifact with access control.

    Args:
        path: Path to artifact (without .enc/.json suffix)
        user_clearance: User's clearance level for access control

    Returns:
        Decrypted plaintext bytes

    Raises:
        PermissionError: If user clearance insufficient for label
        FileNotFoundError: If artifact or sidecar not found
        ValueError: If decryption fails

    Example:
        >>> data = read_encrypted(Path("artifact.md"), "Confidential")
        >>> data
        b'content'
    """
    # Read sidecar metadata
    sidecar_path = path.with_suffix(path.suffix + ".json")
    if not sidecar_path.exists():
        raise FileNotFoundError(f"Sidecar not found: {sidecar_path}")

    metadata = json.loads(sidecar_path.read_text(encoding="utf-8"))
    label = metadata.get("label")

    # Check access control
    if label and not can_access(user_clearance, label):
        raise PermissionError(f"Insufficient clearance: {user_clearance} cannot access {label} data")

    # Read and decrypt
    if metadata.get("encrypted", False):
        enc_path = path.with_suffix(path.suffix + ".enc")
        if not enc_path.exists():
            raise FileNotFoundError(f"Encrypted artifact not found: {enc_path}")

        envelope = json.loads(enc_path.read_text(encoding="utf-8"))
        return decrypt(envelope)
    else:
        # Plaintext fallback
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {path}")
        return path.read_bytes()


def get_artifact_metadata(path: Path) -> dict | None:
    """
    Read artifact metadata without decrypting content.

    Args:
        path: Path to artifact (without .json suffix)

    Returns:
        Metadata dict or None if sidecar doesn't exist

    Example:
        >>> meta = get_artifact_metadata(Path("artifact.md"))
        >>> meta['label']
        'Confidential'
    """
    sidecar_path = path.with_suffix(path.suffix + ".json")
    if not sidecar_path.exists():
        return None

    return json.loads(sidecar_path.read_text(encoding="utf-8"))
