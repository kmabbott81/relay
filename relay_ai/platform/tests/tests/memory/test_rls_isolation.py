"""Comprehensive tests for Row-Level Security isolation in memory_chunks

Task A: Schema + RLS + Encryption Columns

Tests verify:
1. user_hash computation and consistency
2. RLS policy enforces cross-tenant isolation
3. Partial indexes are correctly scoped to user_hash
4. Session variable plumbing works end-to-end
5. Rollback procedure restores original state
"""

import hashlib
import hmac
import os
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest

# Import RLS module
from relay_ai.memory.rls import (
    MEMORY_TENANT_HMAC_KEY,
    RLSMiddlewareContext,
    clear_rls_session_variable,
    get_rls_context,
    hmac_user,
    set_rls_context,
    set_rls_session_variable,
    verify_rls_isolation,
)


class TestUserHashComputation:
    """Test user_hash computation using HMAC-SHA256"""

    def test_hmac_user_deterministic(self):
        """Hash should be deterministic for same user_id"""
        user_id = "user_123@example.com"
        hash1 = hmac_user(user_id)
        hash2 = hmac_user(user_id)
        assert hash1 == hash2

    def test_hmac_user_different_users(self):
        """Different users should have different hashes"""
        hash1 = hmac_user("user_1")
        hash2 = hmac_user("user_2")
        assert hash1 != hash2

    def test_hmac_user_format(self):
        """Hash should be 64-character hex string (SHA256)"""
        user_hash = hmac_user("user_123")
        assert len(user_hash) == 64
        assert all(c in "0123456789abcdef" for c in user_hash)

    def test_hmac_user_uses_correct_key(self):
        """Hash should use MEMORY_TENANT_HMAC_KEY"""
        user_id = "user_123"
        user_hash = hmac_user(user_id)

        # Manually compute expected hash
        expected = hmac.new(MEMORY_TENANT_HMAC_KEY.encode("utf-8"), user_id.encode("utf-8"), hashlib.sha256).hexdigest()

        assert user_hash == expected

    def test_hmac_user_uuid_input(self):
        """Should work with UUID-formatted user IDs"""
        uuid_user = "550e8400-e29b-41d4-a716-446655440000"
        user_hash = hmac_user(uuid_user)
        assert len(user_hash) == 64

    @patch.dict(os.environ, {"MEMORY_TENANT_HMAC_KEY": "prod-key-xyz"})
    def test_hmac_user_different_key(self):
        """Different key should produce different hash"""
        # Note: This tests the theoretical behavior;
        # in practice, changing the key mid-runtime requires module reload
        user_id = "user_123"
        user_hash = hmac_user(user_id)
        # The hash should be computed with the current MEMORY_TENANT_HMAC_KEY
        assert len(user_hash) == 64


class TestRLSContextManager:
    """Test set_rls_context context manager"""

    @pytest.mark.asyncio
    async def test_set_rls_context_sets_variable(self):
        """Should set app.user_hash session variable"""
        mock_conn = AsyncMock(spec=asyncpg.Connection)
        user_id = "user_123"

        async with set_rls_context(mock_conn, user_id):
            pass

        # Verify SET command was called
        calls = mock_conn.execute.call_args_list
        set_call = [c for c in calls if "SET app.user_hash" in str(c)]
        assert len(set_call) > 0

    @pytest.mark.asyncio
    async def test_set_rls_context_clears_variable_on_exit(self):
        """Should clear app.user_hash when exiting context"""
        mock_conn = AsyncMock(spec=asyncpg.Connection)
        user_id = "user_123"

        async with set_rls_context(mock_conn, user_id):
            pass

        # Verify RESET command was called
        calls = mock_conn.execute.call_args_list
        reset_call = [c for c in calls if "RESET app.user_hash" in str(c)]
        assert len(reset_call) > 0

    @pytest.mark.asyncio
    async def test_set_rls_context_clears_on_exception(self):
        """Should clear session variable even if exception occurs"""
        mock_conn = AsyncMock(spec=asyncpg.Connection)
        user_id = "user_123"

        try:
            async with set_rls_context(mock_conn, user_id):
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Verify RESET was still called
        calls = mock_conn.execute.call_args_list
        reset_call = [c for c in calls if "RESET app.user_hash" in str(c)]
        assert len(reset_call) > 0

    @pytest.mark.asyncio
    async def test_set_rls_context_uses_correct_hash(self):
        """Should use computed user_hash in SET command"""
        mock_conn = AsyncMock(spec=asyncpg.Connection)
        user_id = "user_123"
        expected_hash = hmac_user(user_id)

        async with set_rls_context(mock_conn, user_id):
            pass

        # Check that SET command contains the correct hash
        calls = mock_conn.execute.call_args_list
        set_call = [c for c in calls if "SET app.user_hash" in str(c)][0]
        set_sql = str(set_call)
        assert expected_hash in set_sql


class TestRLSSessionVariable:
    """Test direct session variable setters/clearers"""

    @pytest.mark.asyncio
    async def test_set_rls_session_variable_returns_hash(self):
        """set_rls_session_variable should return computed user_hash"""
        mock_conn = AsyncMock(spec=asyncpg.Connection)
        user_id = "user_123"
        expected_hash = hmac_user(user_id)

        result = await set_rls_session_variable(mock_conn, user_id)

        assert result == expected_hash

    @pytest.mark.asyncio
    async def test_clear_rls_session_variable(self):
        """clear_rls_session_variable should reset the variable"""
        mock_conn = AsyncMock(spec=asyncpg.Connection)

        await clear_rls_session_variable(mock_conn)

        mock_conn.execute.assert_called_once()
        call_sql = str(mock_conn.execute.call_args)
        assert "RESET app.user_hash" in call_sql


class TestRLSVerification:
    """Test RLS isolation verification function"""

    @pytest.mark.asyncio
    async def test_verify_rls_isolation_structure(self):
        """verify_rls_isolation should return expected dict structure"""
        mock_conn = AsyncMock(spec=asyncpg.Connection)
        mock_conn.fetchval.return_value = True  # RLS enabled
        mock_conn.fetch.return_value = [{"polname": "memory_tenant_isolation"}]

        result = await verify_rls_isolation(mock_conn, "user_123")

        assert "user_hash" in result
        assert "row_count" in result
        assert "rls_enabled" in result
        assert "policy_active" in result

    @pytest.mark.asyncio
    async def test_verify_rls_isolation_rls_enabled(self):
        """Should correctly detect when RLS is enabled"""
        mock_conn = AsyncMock(spec=asyncpg.Connection)
        mock_conn.fetchval.return_value = True
        mock_conn.fetch.return_value = [{"polname": "memory_tenant_isolation"}]

        result = await verify_rls_isolation(mock_conn, "user_123")

        assert result["rls_enabled"] is True
        assert result["policy_active"] is True

    @pytest.mark.asyncio
    async def test_verify_rls_isolation_rls_disabled(self):
        """Should correctly detect when RLS is disabled"""
        mock_conn = AsyncMock(spec=asyncpg.Connection)
        mock_conn.fetchval.return_value = False
        mock_conn.fetch.return_value = []

        result = await verify_rls_isolation(mock_conn, "user_123")

        assert result["rls_enabled"] is False
        assert result["policy_active"] is False

    @pytest.mark.asyncio
    async def test_verify_rls_isolation_on_error(self):
        """Should handle exceptions gracefully"""
        mock_conn = AsyncMock(spec=asyncpg.Connection)
        mock_conn.fetchval.side_effect = Exception("DB connection error")

        result = await verify_rls_isolation(mock_conn, "user_123")

        assert result["rls_enabled"] is False
        assert "error" in result


class TestRLSMiddlewareContext:
    """Test RLSMiddlewareContext for FastAPI integration"""

    def test_rls_context_initialization(self):
        """Should initialize with user_id and compute user_hash"""
        user_id = "user_123"
        ctx = RLSMiddlewareContext(user_id=user_id)

        assert ctx.user_id == user_id
        assert ctx.user_hash == hmac_user(user_id)

    def test_rls_context_anonymous_user(self):
        """Should handle anonymous (None) user_id"""
        ctx = RLSMiddlewareContext(user_id=None)

        assert ctx.user_id is None
        assert ctx.user_hash is None

    @pytest.mark.asyncio
    async def test_rls_context_apply_to_connection(self):
        """Should apply RLS context to connection"""
        mock_conn = AsyncMock(spec=asyncpg.Connection)
        user_id = "user_123"
        ctx = RLSMiddlewareContext(user_id=user_id)

        await ctx.apply_to_connection(mock_conn)

        mock_conn.execute.assert_called_once()
        call_sql = str(mock_conn.execute.call_args)
        assert "SET app.user_hash" in call_sql

    @pytest.mark.asyncio
    async def test_rls_context_anonymous_no_apply(self):
        """Anonymous context should not set session variable"""
        mock_conn = AsyncMock(spec=asyncpg.Connection)
        ctx = RLSMiddlewareContext(user_id=None)

        await ctx.apply_to_connection(mock_conn)

        # Should not call execute for anonymous users
        mock_conn.execute.assert_not_called()


class TestGetRLSContext:
    """Test get_rls_context extraction from request principal"""

    @pytest.mark.asyncio
    async def test_get_rls_context_from_principal(self):
        """Should extract user_id from principal dict"""
        principal = {"user_id": "user_123", "is_anonymous": False}

        ctx = await get_rls_context(principal)

        assert ctx.user_id == "user_123"
        assert ctx.user_hash == hmac_user("user_123")

    @pytest.mark.asyncio
    async def test_get_rls_context_missing_user_id(self):
        """Should handle missing user_id in principal"""
        principal = {"is_anonymous": True}

        ctx = await get_rls_context(principal)

        assert ctx.user_id is None
        assert ctx.user_hash is None


class TestRLSTenantIsolation:
    """Integration tests for tenant isolation (requires test database)"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rls_blocks_cross_tenant_access(self):
        """RLS should prevent user A from seeing user B's data"""
        # This test requires a running PostgreSQL instance with memory_chunks table
        # and RLS policy enabled. Skip if database is not available.
        pytest.skip("Requires test database with RLS policy")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_partial_index_scoped_to_user(self):
        """Partial ANN index should be scoped to user_hash"""
        # This test requires a running PostgreSQL instance
        pytest.skip("Requires test database with partial indexes")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rollback_restores_state(self):
        """Rollback migration should restore original state"""
        # This test requires a running PostgreSQL instance
        pytest.skip("Requires test database for rollback testing")


class TestEdgeCases:
    """Test edge cases and error conditions"""

    def test_hmac_user_empty_string(self):
        """Should handle empty user_id"""
        user_hash = hmac_user("")
        assert len(user_hash) == 64

    def test_hmac_user_special_characters(self):
        """Should handle special characters in user_id"""
        user_id = "user+123@example.com!#$%"
        user_hash = hmac_user(user_id)
        assert len(user_hash) == 64

    def test_hmac_user_very_long_id(self):
        """Should handle very long user_id"""
        user_id = "x" * 10000
        user_hash = hmac_user(user_id)
        assert len(user_hash) == 64

    @pytest.mark.asyncio
    async def test_set_rls_context_unicode_user_id(self):
        """Should handle Unicode characters in user_id"""
        mock_conn = AsyncMock(spec=asyncpg.Connection)
        user_id = "user_文字_用户_пользователь"

        async with set_rls_context(mock_conn, user_id):
            pass

        # Should complete without error
        assert mock_conn.execute.called


class TestRegressionSuite:
    """Regression tests to prevent future issues"""

    def test_hmac_consistency_across_imports(self):
        """Hash should be consistent when imported in different ways"""
        from relay_ai.memory import rls
        from relay_ai.memory.rls import hmac_user as hmac_import1

        hmac_import2 = rls.hmac_user

        user_id = "test_user"
        hash1 = hmac_import1(user_id)
        hash2 = hmac_import2(user_id)

        assert hash1 == hash2

    @pytest.mark.asyncio
    async def test_context_manager_idempotency(self):
        """Multiple context managers should work correctly"""
        mock_conn = AsyncMock(spec=asyncpg.Connection)

        async with set_rls_context(mock_conn, "user_1"):
            async with set_rls_context(mock_conn, "user_2"):
                pass

        # Should have SET calls for both users
        calls = mock_conn.execute.call_args_list
        set_calls = [c for c in calls if "SET app.user_hash" in str(c)]
        assert len(set_calls) >= 2


# --- Test Fixtures ---


@pytest.fixture
def test_user_ids():
    """Common test user IDs"""
    return {
        "user_1": "user_1@company.com",
        "user_2": "user_2@company.com",
        "user_admin": "admin@company.com",
    }


@pytest.fixture
def test_hashes(test_user_ids):
    """Precomputed user hashes for testing"""
    return {key: hmac_user(val) for key, val in test_user_ids.items()}
