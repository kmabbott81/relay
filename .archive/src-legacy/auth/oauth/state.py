"""OAuth 2.0 state management for CSRF protection.

Stores state parameters in Redis with TTL for OAuth authorization flows.
Falls back to in-memory storage if Redis unavailable.

Sprint 53: Infrastructure foundation for Google OAuth flow.
"""

import hashlib
import os
import secrets
from base64 import urlsafe_b64encode
from datetime import datetime, timedelta
from typing import Optional


class OAuthStateManager:
    """Manage OAuth state parameters with Redis backend.

    OAuth state parameters are used for CSRF protection in authorization flows.
    Each state is valid for 10 minutes (configurable via OAUTH_STATE_TTL_SECONDS).

    Key format: oauth:state:{workspace_id}:{nonce}
    Value: JSON with redirect_uri, provider, code_verifier (PKCE), created_at

    Example:
        manager = OAuthStateManager()
        state = manager.create_state(
            workspace_id="ws_123",
            provider="google",
            redirect_uri="https://example.com/callback"
        )
        # Redirect user to OAuth provider with state parameter

        # On callback:
        data = manager.validate_state(workspace_id="ws_123", state=state)
        if data:
            print(f"Valid state for provider: {data['provider']}")
    """

    def __init__(self, redis_url: Optional[str] = None, ttl_seconds: Optional[int] = None):
        """Initialize OAuth state manager.

        Args:
            redis_url: Redis connection URL (default from REDIS_URL env var)
            ttl_seconds: State TTL in seconds (default 600 = 10 minutes)
        """
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        self.ttl_seconds = ttl_seconds or int(os.getenv("OAUTH_STATE_TTL_SECONDS", "600"))
        self.redis_client = None
        self.backend = "in-memory"  # or "redis"

        # Try to connect to Redis
        if self.redis_url:
            try:
                import redis

                self.redis_client = redis.from_url(self.redis_url, decode_responses=True, socket_connect_timeout=2)
                self.redis_client.ping()
                self.backend = "redis"
                print(f"[INFO] OAuth state manager: Using Redis backend (TTL={self.ttl_seconds}s)")
            except Exception as e:
                print(f"[WARN] OAuth state manager: Redis connection failed: {e}. Using in-memory fallback.")
                self.backend = "in-memory"
                self._memory_store = {}  # {state: data}
        else:
            print(f"[INFO] OAuth state manager: Using in-memory backend (TTL={self.ttl_seconds}s)")
            self._memory_store = {}

    def create_state(
        self,
        workspace_id: str,
        provider: str,
        redirect_uri: str,
        use_pkce: bool = True,
    ) -> dict[str, str]:
        """Create OAuth state parameter with optional PKCE.

        Args:
            workspace_id: Workspace identifier
            provider: OAuth provider ("google", "microsoft", etc.)
            redirect_uri: Callback URL for OAuth flow
            use_pkce: Generate PKCE code_verifier and code_challenge

        Returns:
            Dictionary with:
            - state: Random nonce to include in authorization URL
            - code_challenge: PKCE code challenge (if use_pkce=True)
            - code_challenge_method: "S256" (if use_pkce=True)
        """
        # Generate state nonce (32 bytes = 256 bits)
        state_nonce = urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8").rstrip("=")

        # Generate PKCE code verifier and challenge
        code_verifier = None
        code_challenge = None
        code_challenge_method = None

        if use_pkce:
            # PKCE code verifier: 43-128 characters from [A-Z a-z 0-9 - . _ ~]
            code_verifier = urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8").rstrip("=")

            # PKCE code challenge: SHA256(code_verifier) base64url-encoded
            challenge_bytes = hashlib.sha256(code_verifier.encode("utf-8")).digest()
            code_challenge = urlsafe_b64encode(challenge_bytes).decode("utf-8").rstrip("=")
            code_challenge_method = "S256"

        # Store state data
        state_data = {
            "workspace_id": workspace_id,
            "provider": provider,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
            "created_at": datetime.now().isoformat(),
        }

        if self.backend == "redis":
            self._store_redis(workspace_id, state_nonce, state_data)
        else:
            self._store_memory(state_nonce, state_data)

        result = {"state": state_nonce}
        if use_pkce:
            result["code_challenge"] = code_challenge
            result["code_challenge_method"] = code_challenge_method

        return result

    def validate_state(self, workspace_id: str, state: str) -> Optional[dict]:
        """Validate OAuth state parameter.

        Args:
            workspace_id: Workspace identifier (must match create_state)
            state: State nonce from OAuth callback

        Returns:
            State data dictionary if valid, None if invalid/expired
            Dictionary contains: provider, redirect_uri, code_verifier, created_at
        """
        if self.backend == "redis":
            return self._validate_redis(workspace_id, state)
        else:
            return self._validate_memory(workspace_id, state)

    def _store_redis(self, workspace_id: str, state: str, data: dict) -> None:
        """Store state in Redis with TTL."""
        import json

        key = f"oauth:state:{workspace_id}:{state}"
        value = json.dumps(data)
        self.redis_client.setex(key, self.ttl_seconds, value)

    def _store_memory(self, state: str, data: dict) -> None:
        """Store state in memory with expiry timestamp."""
        expires_at = datetime.now() + timedelta(seconds=self.ttl_seconds)
        self._memory_store[state] = {**data, "_expires_at": expires_at.isoformat()}

    def _validate_redis(self, workspace_id: str, state: str) -> Optional[dict]:
        """Validate state from Redis."""
        import json

        key = f"oauth:state:{workspace_id}:{state}"
        value = self.redis_client.get(key)

        if not value:
            return None

        # Delete state after validation (one-time use)
        self.redis_client.delete(key)

        try:
            data = json.loads(value)
            # Verify workspace_id matches
            if data.get("workspace_id") != workspace_id:
                return None
            return data
        except json.JSONDecodeError:
            return None

    def _validate_memory(self, workspace_id: str, state: str) -> Optional[dict]:
        """Validate state from memory."""
        data = self._memory_store.get(state)

        if not data:
            return None

        # Check expiry
        expires_at = datetime.fromisoformat(data["_expires_at"])
        if datetime.now() > expires_at:
            self._memory_store.pop(state, None)
            return None

        # Verify workspace_id matches
        if data.get("workspace_id") != workspace_id:
            return None

        # Delete state after validation (one-time use)
        self._memory_store.pop(state, None)

        # Remove internal _expires_at field
        data = {k: v for k, v in data.items() if not k.startswith("_")}
        return data

    def cleanup_expired_states(self) -> int:
        """Clean up expired states from in-memory store.

        Only needed for in-memory backend (Redis auto-expires via TTL).

        Returns:
            Number of expired states removed
        """
        if self.backend == "redis":
            return 0  # Redis handles expiry automatically

        now = datetime.now()
        expired = [
            state for state, data in self._memory_store.items() if datetime.fromisoformat(data["_expires_at"]) < now
        ]

        for state in expired:
            self._memory_store.pop(state, None)

        return len(expired)


# Sprint 54: Simpler API for deriving workspace/actor from state
def store_context(
    workspace_id: str,
    actor_id: str,
    pkce_verifier: str,
    extra: Optional[dict] = None,
    ttl_seconds: int = 600,
) -> str:
    """Store OAuth state context in Redis with TTL and replay protection.

    Args:
        workspace_id: Workspace ID for token storage
        actor_id: Actor (user) ID for token storage
        pkce_verifier: PKCE code verifier for token exchange
        extra: Optional additional context (e.g., provider, redirect_uri)
        ttl_seconds: Time-to-live in seconds (default 10 minutes)

    Returns:
        Random URL-safe state string
    """
    import json
    import time

    import redis

    state = secrets.token_urlsafe(32)

    context = {
        "workspace_id": workspace_id,
        "actor_id": actor_id,
        "pkce_verifier": pkce_verifier,
        "used": False,
        "created_at": int(time.time()),
    }

    if extra:
        context["extra"] = extra

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        raise RuntimeError("REDIS_URL environment variable not set")

    redis_client = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
    key = f"oauth:state:{state}"
    redis_client.setex(key, ttl_seconds, json.dumps(context))

    return state


def validate_and_retrieve_context(state: str) -> Optional[dict]:
    """Atomically validate state and retrieve context with replay protection.

    Checks if state exists, not expired, and not already used.
    Marks state as used (deletes) to prevent replay attacks.

    Args:
        state: OAuth state string from callback

    Returns:
        Context dict with workspace_id, actor_id, pkce_verifier, etc.
        None if state is invalid, expired, or already used.
    """
    import json

    import redis

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        raise RuntimeError("REDIS_URL environment variable not set")

    redis_client = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
    key = f"oauth:state:{state}"

    # Fetch context
    context_json = redis_client.get(key)
    if not context_json:
        return None

    try:
        context = json.loads(context_json)
    except json.JSONDecodeError:
        return None

    # Check if already used
    if context.get("used", False):
        return None

    # Delete to prevent replay
    redis_client.delete(key)

    return context
