"""OAuth 2.0 token storage with database persistence and Redis caching.

Implements write-through cache pattern:
- Write: Save to database (encrypted), then cache in Redis
- Read: Check Redis first, fall back to database if not cached
- Refresh: Update both database and cache

Sprint 53: Google OAuth token management for Actions API.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Optional

from cryptography.fernet import Fernet


class OAuthTokenCache:
    """Manage OAuth tokens with encrypted database storage and Redis cache.

    Tokens are stored encrypted in the database (source of truth) and cached
    in Redis for fast access. Uses write-through cache pattern.

    Redis key format: oauth:token:{provider}:{workspace_id}:{actor_id}
    TTL: Match token expiry (or 1 hour default)

    Database table: oauth_tokens
    - Encrypted: access_token, refresh_token
    - Plaintext: provider, workspace_id, actor_id, expires_at, scope

    Example:
        cache = OAuthTokenCache()

        # Store tokens after OAuth callback
        cache.store_tokens(
            provider="google",
            workspace_id="ws_123",
            actor_id="user_456",
            access_token="ya29.a0...",
            refresh_token="1//0g...",
            expires_in=3600,
            scope="https://www.googleapis.com/auth/gmail.send"
        )

        # Retrieve tokens (from cache or DB)
        tokens = cache.get_tokens("google", "ws_123", "user_456")
        if tokens:
            gmail_client = build('gmail', 'v1', credentials=tokens["access_token"])
    """

    def __init__(self, redis_url: Optional[str] = None, encryption_key: Optional[str] = None, redis_client=None):
        """Initialize OAuth token cache.

        Args:
            redis_url: Redis connection URL (default from REDIS_URL env var)
            encryption_key: Fernet encryption key (default from OAUTH_ENCRYPTION_KEY env var)
            redis_client: Pre-configured Redis client for dependency injection (tests)
        """
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        self.redis_client = redis_client  # Allow DI for testing
        self.backend = "db-only"  # or "db+cache"

        # Initialize Redis cache (optional) - skip if client provided via DI
        if not self.redis_client and self.redis_url:
            try:
                import redis

                self.redis_client = redis.from_url(self.redis_url, decode_responses=True, socket_connect_timeout=2)
                self.redis_client.ping()
                self.backend = "db+cache"
                print("[INFO] OAuth token cache: Using database + Redis cache")
            except Exception as e:
                print(f"[WARN] OAuth token cache: Redis unavailable: {e}. Using database only.")
                self.backend = "db-only"
        elif self.redis_client:
            # Client provided via DI (testing)
            self.backend = "db+cache"
        else:
            print("[INFO] OAuth token cache: Using database only (no Redis)")

        # Initialize encryption
        app_env = os.getenv("APP_ENV", "dev").lower()
        encryption_key_str = encryption_key or os.getenv("OAUTH_ENCRYPTION_KEY")

        if not encryption_key_str:
            if app_env in ("dev", "ci"):
                # Dev-only ephemeral key; DO NOT use in prod
                print("[WARN] OAUTH_ENCRYPTION_KEY not set. Using ephemeral key (dev/ci only).")
                self.cipher = Fernet(Fernet.generate_key())
            else:
                raise RuntimeError(
                    "OAUTH_ENCRYPTION_KEY is required in non-dev environments. "
                    f"Current APP_ENV: {app_env}. Set APP_ENV=dev for local development."
                )
        else:
            self.cipher = Fernet(encryption_key_str.encode("utf-8"))

    async def store_tokens(
        self,
        provider: str,
        workspace_id: str,
        actor_id: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_in: Optional[int] = None,
        scope: Optional[str] = None,
    ) -> None:
        """Store OAuth tokens with encryption and caching.

        Args:
            provider: OAuth provider ("google", "microsoft", etc.)
            workspace_id: Workspace identifier
            actor_id: User/actor identifier
            access_token: Access token to encrypt and store
            refresh_token: Refresh token to encrypt and store (optional)
            expires_in: Token lifetime in seconds (default 3600)
            scope: OAuth scopes granted (space-separated)
        """
        # Encrypt tokens
        access_token_encrypted = self.cipher.encrypt(access_token.encode("utf-8")).decode("utf-8")
        refresh_token_encrypted = None
        if refresh_token:
            refresh_token_encrypted = self.cipher.encrypt(refresh_token.encode("utf-8")).decode("utf-8")

        # Calculate expiry (use UTC for consistency)
        expires_in = expires_in or 3600  # Default 1 hour
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        # Store in database (source of truth)
        await self._store_in_db(
            provider=provider,
            workspace_id=workspace_id,
            actor_id=actor_id,
            access_token_encrypted=access_token_encrypted,
            refresh_token_encrypted=refresh_token_encrypted,
            expires_at=expires_at,
            scope=scope,
        )

        # Cache in Redis (if available)
        if self.backend == "db+cache":
            self._cache_in_redis(
                provider=provider,
                workspace_id=workspace_id,
                actor_id=actor_id,
                access_token=access_token,  # Cache decrypted for fast access
                refresh_token=refresh_token,
                expires_at=expires_at,
                scope=scope,
                ttl_seconds=expires_in,
            )

    def get_tokens(self, provider: str, workspace_id: str, actor_id: str) -> Optional[dict[str, any]]:
        """Retrieve OAuth tokens (from cache or database).

        NOTE: This is a synchronous wrapper for backward compatibility.
        For async contexts, use get_tokens_async() instead.

        Args:
            provider: OAuth provider ("google", "microsoft", etc.")
            workspace_id: Workspace identifier
            actor_id: User/actor identifier

        Returns:
            Dictionary with access_token, refresh_token, expires_at, scope
            or None if tokens not found or expired
        """
        # Try cache first (if available)
        if self.backend == "db+cache":
            cached = self._get_from_redis(provider, workspace_id, actor_id)
            if cached:
                return cached

        # Fall back to database (blocking call using asyncio.run)
        import asyncio

        try:
            asyncio.get_running_loop()
            # Already in async context - this shouldn't be called
            raise RuntimeError("get_tokens() called from async context - use get_tokens_async() instead")
        except RuntimeError:
            # No running loop - safe to use asyncio.run()
            tokens = asyncio.run(self._get_from_db(provider, workspace_id, actor_id))

        # Warm cache if found in DB
        if tokens and self.backend == "db+cache":
            ttl_seconds = int((tokens["expires_at"] - datetime.now()).total_seconds())
            if ttl_seconds > 0:
                self._cache_in_redis(
                    provider=provider,
                    workspace_id=workspace_id,
                    actor_id=actor_id,
                    access_token=tokens["access_token"],
                    refresh_token=tokens["refresh_token"],
                    expires_at=tokens["expires_at"],
                    scope=tokens.get("scope"),
                    ttl_seconds=ttl_seconds,
                )

        return tokens

    async def get_tokens_async(self, provider: str, workspace_id: str, actor_id: str) -> Optional[dict[str, any]]:
        """Retrieve OAuth tokens (async version).

        Args:
            provider: OAuth provider ("google", "microsoft", etc.)
            workspace_id: Workspace identifier
            actor_id: User/actor identifier

        Returns:
            Dictionary with access_token, refresh_token, expires_at, scope
            or None if tokens not found or expired
        """
        # Try cache first (if available)
        if self.backend == "db+cache":
            cached = self._get_from_redis(provider, workspace_id, actor_id)
            if cached:
                return cached

        # Fall back to database
        tokens = await self._get_from_db(provider, workspace_id, actor_id)

        # Warm cache if found in DB
        if tokens and self.backend == "db+cache":
            ttl_seconds = int((tokens["expires_at"] - datetime.now()).total_seconds())
            if ttl_seconds > 0:
                self._cache_in_redis(
                    provider=provider,
                    workspace_id=workspace_id,
                    actor_id=actor_id,
                    access_token=tokens["access_token"],
                    refresh_token=tokens["refresh_token"],
                    expires_at=tokens["expires_at"],
                    scope=tokens.get("scope"),
                    ttl_seconds=ttl_seconds,
                )

        return tokens

    def delete_tokens(self, provider: str, workspace_id: str, actor_id: str) -> None:
        """Delete OAuth tokens from both cache and database.

        Args:
            provider: OAuth provider
            workspace_id: Workspace identifier
            actor_id: User/actor identifier
        """
        # Delete from cache
        if self.backend == "db+cache":
            key = f"oauth:token:{provider}:{workspace_id}:{actor_id}"
            self.redis_client.delete(key)

        # Delete from database
        self._delete_from_db(provider, workspace_id, actor_id)

    async def _store_in_db(
        self,
        provider: str,
        workspace_id: str,
        actor_id: str,
        access_token_encrypted: str,
        refresh_token_encrypted: Optional[str],
        expires_at: datetime,
        scope: Optional[str],
    ) -> None:
        """Store encrypted tokens in database using upsert (INSERT ... ON CONFLICT UPDATE)."""
        from uuid import UUID

        from relay_ai.db.connection import get_connection

        # Convert workspace_id to UUID if string
        workspace_uuid = UUID(workspace_id) if isinstance(workspace_id, str) else workspace_id

        async with get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO oauth_tokens (
                    workspace_id, actor_type, actor_id, provider, scopes,
                    encrypted_access_token, encrypted_refresh_token,
                    access_token_expires_at, updated_at
                )
                VALUES ($1, $2::actor_type_enum, $3, $4, $5, $6, $7, $8, now())
                ON CONFLICT (workspace_id, provider, actor_type, actor_id)
                DO UPDATE SET
                    encrypted_access_token = EXCLUDED.encrypted_access_token,
                    encrypted_refresh_token = EXCLUDED.encrypted_refresh_token,
                    access_token_expires_at = EXCLUDED.access_token_expires_at,
                    scopes = EXCLUDED.scopes,
                    updated_at = now()
                """,
                workspace_uuid,
                "user",  # TODO: Get from actor context when available
                actor_id,
                provider,
                scope,
                access_token_encrypted,
                refresh_token_encrypted,
                expires_at,
            )

    async def _get_from_db(self, provider: str, workspace_id: str, actor_id: str) -> Optional[dict[str, any]]:
        """Retrieve and decrypt tokens from database."""
        from uuid import UUID

        from relay_ai.db.connection import get_connection

        # Convert workspace_id to UUID if string
        workspace_uuid = UUID(workspace_id) if isinstance(workspace_id, str) else workspace_id

        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    encrypted_access_token,
                    encrypted_refresh_token,
                    access_token_expires_at,
                    scopes
                FROM oauth_tokens
                WHERE workspace_id = $1
                  AND provider = $2
                  AND actor_type = $3::actor_type_enum
                  AND actor_id = $4
                """,
                workspace_uuid,
                provider,
                "user",  # TODO: Get from actor context
                actor_id,
            )

        if not row:
            return None

        # Decrypt tokens
        try:
            access_token = self._decrypt_token(row["encrypted_access_token"])
            refresh_token = (
                self._decrypt_token(row["encrypted_refresh_token"]) if row["encrypted_refresh_token"] else None
            )

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": row["access_token_expires_at"],
                "scope": row["scopes"],
            }
        except Exception as e:
            # Log decryption error but don't expose details
            print(f"[ERROR] Token decryption failed: {e}")
            return None

    async def _delete_from_db(self, provider: str, workspace_id: str, actor_id: str) -> None:
        """Delete tokens from database."""
        from uuid import UUID

        from relay_ai.db.connection import get_connection

        # Convert workspace_id to UUID if string
        workspace_uuid = UUID(workspace_id) if isinstance(workspace_id, str) else workspace_id

        async with get_connection() as conn:
            await conn.execute(
                """
                DELETE FROM oauth_tokens
                WHERE workspace_id = $1
                  AND provider = $2
                  AND actor_type = $3::actor_type_enum
                  AND actor_id = $4
                """,
                workspace_uuid,
                provider,
                "user",  # TODO: Get from actor context
                actor_id,
            )

    def _cache_in_redis(
        self,
        provider: str,
        workspace_id: str,
        actor_id: str,
        access_token: str,
        refresh_token: Optional[str],
        expires_at: datetime,
        scope: Optional[str],
        ttl_seconds: int,
    ) -> None:
        """Cache tokens in Redis with TTL."""
        key = f"oauth:token:{provider}:{workspace_id}:{actor_id}"
        value = json.dumps(
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": expires_at.isoformat(),
                "scope": scope,
            }
        )

        # Set with TTL matching token expiry
        self.redis_client.setex(key, ttl_seconds, value)

    def _get_from_redis(self, provider: str, workspace_id: str, actor_id: str) -> Optional[dict[str, any]]:
        """Retrieve tokens from Redis cache."""
        key = f"oauth:token:{provider}:{workspace_id}:{actor_id}"
        value = self.redis_client.get(key)

        if not value:
            return None

        try:
            data = json.loads(value)
            # Parse expires_at back to datetime
            data["expires_at"] = datetime.fromisoformat(data["expires_at"])
            return data
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    async def get_tokens_with_auto_refresh(
        self, provider: str, workspace_id: str, actor_id: str
    ) -> Optional[dict[str, any]]:
        """Retrieve tokens and automatically refresh if expiring soon.

        Implements Redis lock to prevent refresh stampedes across multiple instances.

        Args:
            provider: OAuth provider
            workspace_id: Workspace identifier
            actor_id: User/actor identifier

        Returns:
            Token dict with access_token, refresh_token, expires_at, scope
            or None if no tokens exist

        Raises:
            HTTPException: 401 if token expired and refresh failed
        """
        import asyncio

        # Get current tokens
        tokens = await self.get_tokens_async(provider, workspace_id, actor_id)
        if not tokens:
            return None

        # Check if token is expiring soon (within 30 seconds for E2E testing)
        # Note: Reduced from 120s to 30s to allow testing with short-lived tokens
        expires_at = tokens["expires_at"]
        now_utc = datetime.utcnow()

        if expires_at <= now_utc + timedelta(seconds=30):
            # Token needs refresh
            if not tokens.get("refresh_token"):
                # No refresh token available - return current token if still valid
                if expires_at > now_utc:
                    return tokens
                else:
                    from fastapi import HTTPException

                    raise HTTPException(status_code=401, detail="Token expired, no refresh token")

            # Try to acquire refresh lock
            lock_key = f"oauth:refresh:{workspace_id}:user:{provider}"

            if self.redis_client and self.redis_client.set(lock_key, "1", nx=True, ex=10):
                # We got the lock, perform refresh
                try:
                    from relay_ai.telemetry import oauth_events

                    oauth_events.labels(provider=provider, event="refresh_start").inc()

                    refreshed = await self._perform_refresh(provider, workspace_id, actor_id, tokens["refresh_token"])

                    oauth_events.labels(provider=provider, event="refresh_ok").inc()
                    return refreshed
                except Exception:
                    from relay_ai.telemetry import oauth_events

                    oauth_events.labels(provider=provider, event="refresh_failed").inc()

                    # If refresh failed but token still valid, return it
                    if expires_at > now_utc:
                        return tokens
                    else:
                        raise
                finally:
                    if self.redis_client:
                        self.redis_client.delete(lock_key)
            else:
                # Lock held by another request, wait briefly and recheck
                from relay_ai.telemetry import oauth_events

                oauth_events.labels(provider=provider, event="refresh_locked").inc()

                # Wait up to 1s with 4 retries
                for _ in range(4):
                    await asyncio.sleep(0.25)
                    # Recheck cache - another process may have refreshed
                    refreshed_tokens = await self.get_tokens_async(provider, workspace_id, actor_id)
                    if refreshed_tokens and refreshed_tokens["expires_at"] > now_utc + timedelta(seconds=30):
                        # Token was refreshed by another process
                        return refreshed_tokens

                # Still not refreshed, return current token if still valid
                if expires_at > now_utc:
                    return tokens
                else:
                    from fastapi import HTTPException

                    raise HTTPException(status_code=401, detail="Token expired during refresh lock")

        return tokens

    async def _perform_refresh(
        self, provider: str, workspace_id: str, actor_id: str, refresh_token: str
    ) -> dict[str, any]:
        """Perform OAuth token refresh for Google.

        Args:
            provider: OAuth provider (must be "google")
            workspace_id: Workspace identifier
            actor_id: User/actor identifier
            refresh_token: Refresh token to use

        Returns:
            New token dict with access_token, refresh_token (maybe), expires_at, scope

        Raises:
            HTTPException: If refresh fails
        """
        import httpx

        if provider != "google":
            raise ValueError(f"Token refresh not implemented for provider: {provider}")

        # Get Google OAuth credentials
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

        if not client_id or not client_secret:
            from fastapi import HTTPException

            raise HTTPException(status_code=501, detail="Google OAuth not configured")

        # Call Google token refresh endpoint
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(token_url, data=token_data)

                if response.status_code != 200:
                    from fastapi import HTTPException

                    raise HTTPException(
                        status_code=502,
                        detail=f"Token refresh failed: {response.status_code} {response.text[:200]}",
                    )

                token_response = response.json()
        except httpx.TimeoutException as e:
            from fastapi import HTTPException

            raise HTTPException(status_code=504, detail="Token refresh timeout") from e

        # Extract new tokens
        new_access_token = token_response.get("access_token")
        new_refresh_token = token_response.get("refresh_token", refresh_token)  # Google may not return new one
        expires_in = token_response.get("expires_in", 3600)
        scope = token_response.get("scope")

        if not new_access_token:
            from fastapi import HTTPException

            raise HTTPException(status_code=502, detail="No access token in refresh response")

        # Store updated tokens
        await self.store_tokens(
            provider=provider,
            workspace_id=workspace_id,
            actor_id=actor_id,
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            expires_in=expires_in,
            scope=scope,
        )

        # Return new token dict
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "expires_at": expires_at,
            "scope": scope,
        }
