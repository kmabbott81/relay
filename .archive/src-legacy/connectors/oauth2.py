"""OAuth2 token store for connectors.

CI-safe local token storage with refresh capability.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


def get_token_path() -> Path:
    """Get OAuth token JSONL path from environment."""
    return Path(os.environ.get("OAUTH_TOKEN_PATH", "logs/connectors/tokens.jsonl"))


def load_token(connector_id: str, service_id: str = "default") -> Optional[dict]:
    """Load OAuth token for connector.

    Args:
        connector_id: Connector identifier
        service_id: Service identifier for multi-tenant support (default: "default")

    Returns:
        Token dict or None if not found
    """
    token_path = get_token_path()
    if not token_path.exists():
        return None

    # Token key format: "{connector_id}:{service_id}"
    token_key = f"{connector_id}:{service_id}"

    # Last-wins: find latest token for connector+service
    latest = None
    with open(token_path, encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line.strip())
            # Support both old format (connector_id only) and new format (token_key)
            entry_key = entry.get("token_key", entry.get("connector_id", ""))
            if entry_key == token_key or (
                service_id == "default" and entry.get("connector_id") == connector_id and "token_key" not in entry
            ):
                latest = entry

    return latest


def save_token(
    connector_id: str,
    access_token: str,
    refresh_token: Optional[str] = None,
    expires_at: Optional[str] = None,
    service_id: str = "default",
) -> None:
    """Save OAuth token for connector.

    Args:
        connector_id: Connector identifier
        access_token: Access token
        refresh_token: Refresh token (optional)
        expires_at: Expiry timestamp ISO format (optional)
        service_id: Service identifier for multi-tenant support (default: "default")
    """
    token_path = get_token_path()
    token_path.parent.mkdir(parents=True, exist_ok=True)

    # Token key format: "{connector_id}:{service_id}"
    token_key = f"{connector_id}:{service_id}"

    entry = {
        "connector_id": connector_id,
        "token_key": token_key,
        "service_id": service_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
        "updated_at": datetime.now().isoformat(),
    }

    with open(token_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def needs_refresh(token: dict, safety_window_seconds: Optional[int] = None) -> bool:
    """Check if token needs refresh.

    Args:
        token: Token dict with expires_at field
        safety_window_seconds: Refresh N seconds before expiry (default: 300)

    Returns:
        True if token should be refreshed
    """
    if not token or "expires_at" not in token or not token["expires_at"]:
        return False

    safety_window = safety_window_seconds or int(os.environ.get("OAUTH_REFRESH_SAFETY_WINDOW_S", "300"))

    expires_at = datetime.fromisoformat(token["expires_at"])
    refresh_threshold = datetime.now() + timedelta(seconds=safety_window)

    return expires_at < refresh_threshold


def refresh_token(connector_id: str, refresh_token_value: str) -> Optional[dict]:
    """Refresh OAuth token (placeholder - implement OAuth flow).

    Args:
        connector_id: Connector identifier
        refresh_token_value: Refresh token

    Returns:
        New token dict or None if refresh failed
    """
    # Placeholder: In production, call OAuth provider's refresh endpoint
    # For now, return None to indicate "not implemented"
    return None
