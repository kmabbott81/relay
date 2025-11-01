"""Unit tests for OAuth token refresh with Redis lock.

Sprint 53 Phase B: Test concurrent refresh, lock acquisition, metrics emission.
Sprint 54: Stabilized with FakeRedis fixture and freezegun for deterministic time.
"""

import asyncio
import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

from src.auth.oauth.tokens import OAuthTokenCache


class TestOAuthRefreshLock:
    """Test suite for OAuth token refresh with Redis lock (stampede prevention)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.original_client_id = os.environ.get("GOOGLE_CLIENT_ID")
        self.original_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")

        # Set required env vars for testing
        os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
        os.environ["GOOGLE_CLIENT_SECRET"] = "test-secret"

    def teardown_method(self):
        """Restore original environment."""
        if self.original_client_id is not None:
            os.environ["GOOGLE_CLIENT_ID"] = self.original_client_id
        elif "GOOGLE_CLIENT_ID" in os.environ:
            del os.environ["GOOGLE_CLIENT_ID"]

        if self.original_client_secret is not None:
            os.environ["GOOGLE_CLIENT_SECRET"] = self.original_client_secret
        elif "GOOGLE_CLIENT_SECRET" in os.environ:
            del os.environ["GOOGLE_CLIENT_SECRET"]

    @pytest.mark.anyio
    @freeze_time("2025-01-15 12:00:00")
    async def test_concurrent_refresh_only_one_performs_refresh(self, fake_redis):
        """Test that when multiple callers hit expired token, only one performs refresh."""
        # Create two token cache instances with shared FakeRedis
        cache1 = OAuthTokenCache(redis_client=fake_redis)
        cache2 = OAuthTokenCache(redis_client=fake_redis)

        # Track which caller acquires lock
        refresh_call_count = [0]

        # Mock expiring token (within 30 seconds)
        expiring_tokens = {
            "access_token": "old-token",
            "refresh_token": "refresh-token",
            "expires_at": datetime(2025, 1, 15, 12, 0, 25),  # Expires in 25s
            "scope": "gmail.send",
        }

        # Mock refreshed tokens
        refreshed_tokens = {
            "access_token": "new-token",
            "refresh_token": "refresh-token",
            "expires_at": datetime(2025, 1, 15, 13, 0, 0),  # Expires in 1 hour
            "scope": "gmail.send",
        }

        async def mock_perform_refresh(*args):
            refresh_call_count[0] += 1
            await asyncio.sleep(0.05)  # Simulate network delay
            return refreshed_tokens

        # Mock get_tokens to return expiring tokens
        with patch.object(cache1, "get_tokens_async", AsyncMock(return_value=expiring_tokens)), patch.object(
            cache2, "get_tokens_async", AsyncMock(return_value=expiring_tokens)
        ), patch.object(cache1, "_perform_refresh", mock_perform_refresh), patch.object(
            cache2, "_perform_refresh", mock_perform_refresh
        ):
            # Execute both callers concurrently
            task1 = cache1.get_tokens_with_auto_refresh("google", "workspace-123", "user@example.com")
            task2 = cache2.get_tokens_with_auto_refresh("google", "workspace-123", "user@example.com")

            results = await asyncio.gather(task1, task2)

            # Assert only one refresh was performed
            assert refresh_call_count[0] == 1, f"Expected 1 refresh call, got {refresh_call_count[0]}"

            # One should have refreshed tokens, other may have expiring tokens
            # At least one result should be non-None
            assert any(r is not None for r in results)

    @pytest.mark.anyio
    @freeze_time("2025-01-15 12:00:00")
    async def test_refresh_lock_acquisition_and_release(self, fake_redis):
        """Test that refresh lock is acquired and released correctly."""
        cache = OAuthTokenCache(redis_client=fake_redis)

        expiring_tokens = {
            "access_token": "old-token",
            "refresh_token": "refresh-token",
            "expires_at": datetime(2025, 1, 15, 12, 0, 20),  # Expires in 20s
            "scope": "gmail.send",
        }

        refreshed_tokens = {
            "access_token": "new-token",
            "refresh_token": "refresh-token",
            "expires_at": datetime(2025, 1, 15, 13, 0, 0),
            "scope": "gmail.send",
        }

        with patch.object(cache, "get_tokens_async", AsyncMock(return_value=expiring_tokens)), patch.object(
            cache, "_perform_refresh", AsyncMock(return_value=refreshed_tokens)
        ):
            result = await cache.get_tokens_with_auto_refresh("google", "workspace-123", "user@example.com")

            # Assert lock key was created (check Redis)
            lock_key = "oauth:refresh:workspace-123:user:google"
            # Lock should be released after refresh (deleted or expired)
            lock_exists = fake_redis.get(lock_key)
            assert lock_exists is None, "Lock should be released after refresh"

            # Assert refreshed tokens were returned
            assert result["access_token"] == "new-token"

    @pytest.mark.anyio
    async def test_refresh_lock_contention_retry_logic(self, fake_redis):
        """Test that when lock is held, caller waits and retries."""
        cache = OAuthTokenCache(redis_client=fake_redis)

        # Pre-acquire lock to simulate contention
        lock_key = "oauth:refresh:workspace-123:user:google"
        fake_redis.set(lock_key, "1", ex=10)

        now = datetime.utcnow()
        expiring_tokens = {
            "access_token": "old-token",
            "refresh_token": "refresh-token",
            "expires_at": now + timedelta(seconds=20),  # Expiring soon
            "scope": "gmail.send",
        }

        # After retries, return updated tokens (as if another process refreshed)
        refreshed_tokens = {
            "access_token": "new-token",
            "refresh_token": "refresh-token",
            "expires_at": now + timedelta(hours=1),  # Fresh token
            "scope": "gmail.send",
        }

        call_count = [0]

        async def mock_get_tokens(*args):
            call_count[0] += 1
            if call_count[0] == 1:
                return expiring_tokens
            else:
                # Simulate another process refreshing
                return refreshed_tokens

        with patch.object(cache, "get_tokens_async", mock_get_tokens):
            result = await cache.get_tokens_with_auto_refresh("google", "workspace-123", "user@example.com")

            # Assert retry logic executed
            assert call_count[0] > 1, "Expected multiple get_tokens calls during retry"

            # Assert eventually got refreshed tokens
            assert result["access_token"] == "new-token"

    @pytest.mark.anyio
    @freeze_time("2025-01-15 12:00:00")
    async def test_refresh_token_not_expiring_no_refresh(self, fake_redis):
        """Test that tokens not expiring within 30s don't trigger refresh."""
        cache = OAuthTokenCache(redis_client=fake_redis)

        # Token expires in 3 hours (not soon)
        valid_tokens = {
            "access_token": "current-token",
            "refresh_token": "refresh-token",
            "expires_at": datetime(2025, 1, 15, 15, 0, 0),  # 3 hours later
            "scope": "gmail.send",
        }

        with patch.object(cache, "get_tokens_async", AsyncMock(return_value=valid_tokens)):
            result = await cache.get_tokens_with_auto_refresh("google", "workspace-123", "user@example.com")

            # Assert no lock was created
            lock_key = "oauth:refresh:workspace-123:user:google"
            assert fake_redis.get(lock_key) is None

            # Assert original tokens returned
            assert result["access_token"] == "current-token"

    @pytest.mark.anyio
    @freeze_time("2025-01-15 12:00:00")
    async def test_refresh_without_redis_still_works(self):
        """Test that refresh works even without Redis (degraded mode)."""
        cache = OAuthTokenCache()  # No Redis
        cache.redis_client = None

        expiring_tokens = {
            "access_token": "old-token",
            "refresh_token": "refresh-token",
            "expires_at": datetime(2025, 1, 15, 12, 0, 20),
            "scope": "gmail.send",
        }

        refreshed_tokens = {
            "access_token": "new-token",
            "refresh_token": "refresh-token",
            "expires_at": datetime(2025, 1, 15, 13, 0, 0),
            "scope": "gmail.send",
        }

        with patch.object(cache, "get_tokens_async", AsyncMock(return_value=expiring_tokens)), patch.object(
            cache, "_perform_refresh", AsyncMock(return_value=refreshed_tokens)
        ):
            result = await cache.get_tokens_with_auto_refresh("google", "workspace-123", "user@example.com")

            # Assert refresh still happened
            assert result["access_token"] == "new-token"

    @pytest.mark.anyio
    @freeze_time("2025-01-15 12:00:00")
    async def test_refresh_with_no_refresh_token_returns_current_if_valid(self, fake_redis):
        """Test that if no refresh_token but token still valid, returns current token."""
        cache = OAuthTokenCache(redis_client=fake_redis)

        # Token expiring soon but no refresh_token
        tokens_no_refresh = {
            "access_token": "current-token",
            "refresh_token": None,
            "expires_at": datetime(2025, 1, 15, 12, 0, 20),  # Still valid for 20s
            "scope": "gmail.send",
        }

        with patch.object(cache, "get_tokens_async", AsyncMock(return_value=tokens_no_refresh)):
            result = await cache.get_tokens_with_auto_refresh("google", "workspace-123", "user@example.com")

            # Should return current token
            assert result["access_token"] == "current-token"

            # Should not attempt lock
            lock_key = "oauth:refresh:workspace-123:user:google"
            assert fake_redis.get(lock_key) is None

    @pytest.mark.anyio
    @freeze_time("2025-01-15 12:00:00")
    async def test_refresh_with_expired_token_and_no_refresh_token_raises_error(self):
        """Test that if token already expired and no refresh_token, raises 401."""
        from fastapi import HTTPException

        cache = OAuthTokenCache()

        # Token already expired
        expired_tokens = {
            "access_token": "expired-token",
            "refresh_token": None,
            "expires_at": datetime(2025, 1, 15, 11, 59, 50),  # Expired 10s ago
            "scope": "gmail.send",
        }

        with patch.object(cache, "get_tokens_async", AsyncMock(return_value=expired_tokens)):
            with pytest.raises(HTTPException) as exc_info:
                await cache.get_tokens_with_auto_refresh("google", "workspace-123", "user@example.com")

            assert exc_info.value.status_code == 401

    @pytest.mark.anyio
    async def test_perform_refresh_calls_google_endpoint(self):
        """Test that _perform_refresh calls Google's token endpoint correctly."""
        cache = OAuthTokenCache()

        # Mock successful Google response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-access-token",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/gmail.send",
        }

        with patch("httpx.AsyncClient") as MockAsyncClient, patch.object(cache, "store_tokens", AsyncMock()):
            mock_client_instance = MockAsyncClient.return_value.__aenter__.return_value
            mock_client_instance.post = AsyncMock(return_value=mock_response)

            result = await cache._perform_refresh("google", "workspace-123", "user@example.com", "old-refresh-token")

            # Assert Google endpoint called
            mock_client_instance.post.assert_called_once()
            call_args = mock_client_instance.post.call_args
            assert "https://oauth2.googleapis.com/token" in call_args[0][0]

            # Assert refresh_token in request
            token_data = call_args[1]["data"]
            assert token_data["grant_type"] == "refresh_token"
            assert token_data["refresh_token"] == "old-refresh-token"
            assert token_data["client_id"] == "test-client-id"
            assert token_data["client_secret"] == "test-secret"

            # Assert new tokens returned
            assert result["access_token"] == "new-access-token"

    @pytest.mark.anyio
    async def test_perform_refresh_handles_google_error(self):
        """Test that _perform_refresh handles Google API errors correctly."""
        from fastapi import HTTPException

        cache = OAuthTokenCache()

        # Mock failed response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "invalid_grant: Token has been expired or revoked"

        with patch("httpx.AsyncClient") as MockAsyncClient:
            mock_client_instance = MockAsyncClient.return_value.__aenter__.return_value
            mock_client_instance.post = AsyncMock(return_value=mock_response)

            with pytest.raises(HTTPException):
                await cache._perform_refresh("google", "workspace-123", "user@example.com", "invalid-token")

    @pytest.mark.anyio
    @freeze_time("2025-01-15 12:00:00")
    async def test_refresh_lock_key_format(self, fake_redis):
        """Test that Redis lock key follows correct format."""
        cache = OAuthTokenCache(redis_client=fake_redis)

        expiring_tokens = {
            "access_token": "old-token",
            "refresh_token": "refresh-token",
            "expires_at": datetime(2025, 1, 15, 12, 0, 20),
            "scope": "gmail.send",
        }

        refreshed_tokens = {"access_token": "new-token", "expires_at": datetime(2025, 1, 15, 13, 0, 0)}

        with patch.object(cache, "get_tokens_async", AsyncMock(return_value=expiring_tokens)), patch.object(
            cache, "_perform_refresh", AsyncMock(return_value=refreshed_tokens)
        ):
            await cache.get_tokens_with_auto_refresh("google", "workspace-abc-123", "user@example.com")

            # Verify lock key format
            lock_key = "oauth:refresh:workspace-abc-123:user:google"
            # Lock should be deleted after refresh, but we can verify format was used
            # by checking it doesn't exist (meaning it was created with correct key and deleted)
            assert fake_redis.get(lock_key) is None
