"""Unit tests for Gmail adapter execute method (mocked HTTP).

Sprint 53 Phase B: Test feature flag, OAuth integration, error mapping, metrics.
"""

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.actions.adapters.google import GoogleAdapter


class TestGmailExecuteUnit:
    """Test suite for gmail.send execute method with mocked dependencies."""

    def setup_method(self):
        """Set up test fixtures."""
        # Save original env vars
        self.original_enabled = os.environ.get("PROVIDER_GOOGLE_ENABLED")
        self.original_client_id = os.environ.get("GOOGLE_CLIENT_ID")
        self.original_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
        self.original_internal_only = os.environ.get("GOOGLE_INTERNAL_ONLY")

        # CI Stabilization: Disable internal-only mode for unit tests
        os.environ["GOOGLE_INTERNAL_ONLY"] = "false"

    def teardown_method(self):
        """Restore original environment."""
        if self.original_enabled is not None:
            os.environ["PROVIDER_GOOGLE_ENABLED"] = self.original_enabled
        elif "PROVIDER_GOOGLE_ENABLED" in os.environ:
            del os.environ["PROVIDER_GOOGLE_ENABLED"]

        if self.original_client_id is not None:
            os.environ["GOOGLE_CLIENT_ID"] = self.original_client_id
        elif "GOOGLE_CLIENT_ID" in os.environ:
            del os.environ["GOOGLE_CLIENT_ID"]

        if self.original_client_secret is not None:
            os.environ["GOOGLE_CLIENT_SECRET"] = self.original_client_secret
        elif "GOOGLE_CLIENT_SECRET" in os.environ:
            del os.environ["GOOGLE_CLIENT_SECRET"]

        if self.original_internal_only is not None:
            os.environ["GOOGLE_INTERNAL_ONLY"] = self.original_internal_only
        elif "GOOGLE_INTERNAL_ONLY" in os.environ:
            del os.environ["GOOGLE_INTERNAL_ONLY"]

    @pytest.mark.anyio
    async def test_execute_feature_flag_disabled(self):
        """Test execute fails with 501 when PROVIDER_GOOGLE_ENABLED=false."""
        os.environ["PROVIDER_GOOGLE_ENABLED"] = "false"

        adapter = GoogleAdapter()
        params = {"to": "test@example.com", "subject": "Test", "text": "Body"}

        with pytest.raises(ValueError) as exc_info:
            await adapter.execute("gmail.send", params, "workspace-123", "user@example.com")

        error_msg = str(exc_info.value).lower()
        assert "disabled" in error_msg or "provider" in error_msg

    @pytest.mark.anyio
    async def test_execute_with_valid_token_not_expiring(self):
        """Test execute with valid token that's not expiring (no refresh needed)."""
        os.environ["PROVIDER_GOOGLE_ENABLED"] = "true"
        os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
        os.environ["GOOGLE_CLIENT_SECRET"] = "test-secret"

        adapter = GoogleAdapter()
        params = {"to": "recipient@example.com", "subject": "Test Email", "text": "This is a test email."}

        # Mock OAuthTokenCache to return valid tokens (not expiring)
        expires_at = datetime.utcnow() + timedelta(hours=1)  # Expires in 1 hour
        mock_tokens = {
            "access_token": "mock-access-token",
            "refresh_token": "mock-refresh-token",
            "expires_at": expires_at,
            "scope": "https://www.googleapis.com/auth/gmail.send",
        }

        # Mock HTTP response from Gmail API
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "message-id-123", "threadId": "thread-id-456"}

        with patch("src.auth.oauth.tokens.OAuthTokenCache") as MockTokenCache, patch(
            "httpx.AsyncClient"
        ) as MockAsyncClient:
            # Setup mock token cache
            mock_cache_instance = MockTokenCache.return_value
            mock_cache_instance.get_tokens_with_auto_refresh = AsyncMock(return_value=mock_tokens)

            # Setup mock HTTP client
            mock_client_instance = MockAsyncClient.return_value.__aenter__.return_value
            mock_client_instance.post = AsyncMock(return_value=mock_response)

            # Execute
            result = await adapter.execute("gmail.send", params, "workspace-123", "user@example.com")

            # Assert success
            assert result["status"] == "sent"
            assert result["message_id"] == "message-id-123"
            assert result["thread_id"] == "thread-id-456"
            assert result["to"] == "recipient@example.com"
            assert result["subject"] == "Test Email"

            # Assert Gmail API was called with correct parameters
            mock_client_instance.post.assert_called_once()
            call_args = mock_client_instance.post.call_args
            assert "https://gmail.googleapis.com/gmail/v1/users/me/messages/send" in call_args[0][0]

            # Assert Authorization header was set
            headers = call_args[1]["headers"]
            assert headers["Authorization"] == "Bearer mock-access-token"

    @pytest.mark.anyio
    async def test_execute_with_expiring_token_triggers_refresh(self):
        """Test execute with expiring token (<120s) triggers auto-refresh."""
        os.environ["PROVIDER_GOOGLE_ENABLED"] = "true"
        os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
        os.environ["GOOGLE_CLIENT_SECRET"] = "test-secret"

        adapter = GoogleAdapter()
        params = {"to": "test@example.com", "subject": "Refresh Test", "text": "Test token refresh"}

        # Mock refreshed tokens
        refreshed_tokens = {
            "access_token": "new-access-token",
            "refresh_token": "mock-refresh-token",
            "expires_at": datetime.utcnow() + timedelta(hours=1),
            "scope": "https://www.googleapis.com/auth/gmail.send",
        }

        # Mock Gmail API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "msg-123", "threadId": "thread-123"}

        with patch("src.auth.oauth.tokens.OAuthTokenCache") as MockTokenCache, patch(
            "httpx.AsyncClient"
        ) as MockAsyncClient:
            mock_cache_instance = MockTokenCache.return_value
            # First call returns expiring tokens, which triggers refresh internally
            # The get_tokens_with_auto_refresh should handle this and return refreshed tokens
            mock_cache_instance.get_tokens_with_auto_refresh = AsyncMock(return_value=refreshed_tokens)

            mock_client_instance = MockAsyncClient.return_value.__aenter__.return_value
            mock_client_instance.post = AsyncMock(return_value=mock_response)

            result = await adapter.execute("gmail.send", params, "workspace-123", "user@example.com")

            # Assert success
            assert result["status"] == "sent"

            # Assert Gmail API was called with NEW access token (after refresh)
            headers = mock_client_instance.post.call_args[1]["headers"]
            assert headers["Authorization"] == "Bearer new-access-token"

    @pytest.mark.anyio
    async def test_execute_maps_gmail_4xx_error(self):
        """Test execute maps Gmail API 4xx errors to bounded reason gmail_4xx."""
        os.environ["PROVIDER_GOOGLE_ENABLED"] = "true"
        os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
        os.environ["GOOGLE_CLIENT_SECRET"] = "test-secret"

        adapter = GoogleAdapter()
        params = {"to": "test@example.com", "subject": "Test", "text": "Body"}

        mock_tokens = {"access_token": "mock-token", "expires_at": datetime.utcnow() + timedelta(hours=1)}

        # Mock 400 Bad Request response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request: Invalid email format"
        mock_response.request = MagicMock()

        with patch("src.auth.oauth.tokens.OAuthTokenCache") as MockTokenCache, patch(
            "httpx.AsyncClient"
        ) as MockAsyncClient:
            mock_cache_instance = MockTokenCache.return_value
            mock_cache_instance.get_tokens_with_auto_refresh = AsyncMock(return_value=mock_tokens)

            mock_client_instance = MockAsyncClient.return_value.__aenter__.return_value
            mock_client_instance.post = AsyncMock(return_value=mock_response)

            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                await adapter.execute("gmail.send", params, "workspace-123", "user@example.com")

            # Assert error message contains 4xx and truncated error detail
            error_msg = str(exc_info.value)
            assert "400" in error_msg

    @pytest.mark.anyio
    async def test_execute_maps_gmail_5xx_error(self):
        """Test execute maps Gmail API 5xx errors to bounded reason gmail_5xx."""
        os.environ["PROVIDER_GOOGLE_ENABLED"] = "true"
        os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
        os.environ["GOOGLE_CLIENT_SECRET"] = "test-secret"

        adapter = GoogleAdapter()
        params = {"to": "test@example.com", "subject": "Test", "text": "Body"}

        mock_tokens = {"access_token": "mock-token", "expires_at": datetime.utcnow() + timedelta(hours=1)}

        # Mock 503 Service Unavailable response
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.text = "Service Unavailable"
        mock_response.request = MagicMock()

        with patch("src.auth.oauth.tokens.OAuthTokenCache") as MockTokenCache, patch(
            "httpx.AsyncClient"
        ) as MockAsyncClient:
            mock_cache_instance = MockTokenCache.return_value
            mock_cache_instance.get_tokens_with_auto_refresh = AsyncMock(return_value=mock_tokens)

            mock_client_instance = MockAsyncClient.return_value.__aenter__.return_value
            mock_client_instance.post = AsyncMock(return_value=mock_response)

            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                await adapter.execute("gmail.send", params, "workspace-123", "user@example.com")

            error_msg = str(exc_info.value)
            assert "503" in error_msg or "server error" in error_msg.lower()

    @pytest.mark.anyio
    async def test_execute_maps_timeout_error(self):
        """Test execute maps timeout to bounded reason gmail_timeout."""
        os.environ["PROVIDER_GOOGLE_ENABLED"] = "true"
        os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
        os.environ["GOOGLE_CLIENT_SECRET"] = "test-secret"

        adapter = GoogleAdapter()
        params = {"to": "test@example.com", "subject": "Test", "text": "Body"}

        mock_tokens = {"access_token": "mock-token", "expires_at": datetime.utcnow() + timedelta(hours=1)}

        with patch("src.auth.oauth.tokens.OAuthTokenCache") as MockTokenCache, patch(
            "httpx.AsyncClient"
        ) as MockAsyncClient:
            mock_cache_instance = MockTokenCache.return_value
            mock_cache_instance.get_tokens_with_auto_refresh = AsyncMock(return_value=mock_tokens)

            mock_client_instance = MockAsyncClient.return_value.__aenter__.return_value
            mock_client_instance.post = AsyncMock(side_effect=httpx.TimeoutException("Request timed out"))

            with pytest.raises(TimeoutError) as exc_info:
                await adapter.execute("gmail.send", params, "workspace-123", "user@example.com")

            error_msg = str(exc_info.value)
            assert "timed out" in error_msg.lower() or "timeout" in error_msg.lower()

    @pytest.mark.anyio
    async def test_execute_maps_network_error(self):
        """Test execute maps network errors to bounded reason gmail_network_error."""
        os.environ["PROVIDER_GOOGLE_ENABLED"] = "true"
        os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
        os.environ["GOOGLE_CLIENT_SECRET"] = "test-secret"

        adapter = GoogleAdapter()
        params = {"to": "test@example.com", "subject": "Test", "text": "Body"}

        mock_tokens = {"access_token": "mock-token", "expires_at": datetime.utcnow() + timedelta(hours=1)}

        with patch("src.auth.oauth.tokens.OAuthTokenCache") as MockTokenCache, patch(
            "httpx.AsyncClient"
        ) as MockAsyncClient:
            mock_cache_instance = MockTokenCache.return_value
            mock_cache_instance.get_tokens_with_auto_refresh = AsyncMock(return_value=mock_tokens)

            mock_client_instance = MockAsyncClient.return_value.__aenter__.return_value
            mock_client_instance.post = AsyncMock(side_effect=httpx.NetworkError("Connection failed"))

            with pytest.raises(ConnectionError) as exc_info:
                await adapter.execute("gmail.send", params, "workspace-123", "user@example.com")

            error_msg = str(exc_info.value)
            assert "network" in error_msg.lower() or "connection" in error_msg.lower()

    @pytest.mark.anyio
    async def test_execute_oauth_token_missing(self):
        """Test execute raises error with bounded reason oauth_token_missing when no tokens."""
        os.environ["PROVIDER_GOOGLE_ENABLED"] = "true"
        os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
        os.environ["GOOGLE_CLIENT_SECRET"] = "test-secret"

        adapter = GoogleAdapter()
        params = {"to": "test@example.com", "subject": "Test", "text": "Body"}

        with patch("src.auth.oauth.tokens.OAuthTokenCache") as MockTokenCache:
            mock_cache_instance = MockTokenCache.return_value
            mock_cache_instance.get_tokens_with_auto_refresh = AsyncMock(return_value=None)  # No tokens

            with pytest.raises(ValueError) as exc_info:
                await adapter.execute("gmail.send", params, "workspace-123", "user@example.com")

            error_msg = str(exc_info.value)
            assert "no oauth tokens" in error_msg.lower() or "token" in error_msg.lower()

    @pytest.mark.anyio
    async def test_execute_validation_error(self):
        """Test execute raises validation error for invalid params."""
        os.environ["PROVIDER_GOOGLE_ENABLED"] = "true"

        adapter = GoogleAdapter()
        params = {"to": "invalid-email", "subject": "Test", "text": "Body"}  # Invalid email format

        with pytest.raises(ValueError) as exc_info:
            await adapter.execute("gmail.send", params, "workspace-123", "user@example.com")

        error_msg = str(exc_info.value)
        assert "validation error" in error_msg.lower() or "invalid email" in error_msg.lower()

    @pytest.mark.anyio
    async def test_execute_unknown_action(self):
        """Test execute with unknown action ID."""
        os.environ["PROVIDER_GOOGLE_ENABLED"] = "true"

        adapter = GoogleAdapter()
        params = {"to": "test@example.com", "subject": "Test", "text": "Body"}

        with pytest.raises(ValueError) as exc_info:
            await adapter.execute("unknown.action", params, "workspace-123", "user@example.com")

        assert "unknown action" in str(exc_info.value).lower()

    @pytest.mark.anyio
    async def test_execute_base64url_encoding_no_padding(self):
        """Test that MIME message is Base64URL encoded without padding."""
        os.environ["PROVIDER_GOOGLE_ENABLED"] = "true"
        os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
        os.environ["GOOGLE_CLIENT_SECRET"] = "test-secret"

        adapter = GoogleAdapter()
        params = {
            "to": "test@example.com",
            "subject": "Encoding Test",
            "text": "A" * 100,  # Long text to ensure Base64 would have padding
        }

        mock_tokens = {"access_token": "mock-token", "expires_at": datetime.utcnow() + timedelta(hours=1)}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "msg-123", "threadId": "thread-123"}

        with patch("src.auth.oauth.tokens.OAuthTokenCache") as MockTokenCache, patch(
            "httpx.AsyncClient"
        ) as MockAsyncClient:
            mock_cache_instance = MockTokenCache.return_value
            mock_cache_instance.get_tokens_with_auto_refresh = AsyncMock(return_value=mock_tokens)

            mock_client_instance = MockAsyncClient.return_value.__aenter__.return_value
            mock_client_instance.post = AsyncMock(return_value=mock_response)

            await adapter.execute("gmail.send", params, "workspace-123", "user@example.com")

            # Extract the raw message from the POST call
            call_args = mock_client_instance.post.call_args
            json_body = call_args[1]["json"]
            raw_message = json_body["raw"]

            # Assert no padding characters (=) at the end
            assert not raw_message.endswith("="), "Base64URL should not have padding"
            assert not raw_message.endswith("=="), "Base64URL should not have padding"
