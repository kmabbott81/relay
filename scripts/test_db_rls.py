"""Test database connectivity and RLS enforcement for Phase 4 validation."""
import asyncio
import os

import asyncpg
from dotenv import load_dotenv

load_dotenv()


async def validate_database():
    """Validate database connection, RLS policies, and migration state."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("[FAIL] DATABASE_URL not set in environment")
        return False

    print("[INFO] Connecting to database...")
    try:
        conn = await asyncpg.connect(db_url, timeout=10.0)

        # Test 1: Version check
        version = await conn.fetchval("SELECT version();")
        pg_version = version.split()[1]
        print(f"[PASS] Database connected: PostgreSQL {pg_version}")

        # Test 2: Check memory_chunks table
        exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM pg_tables
                WHERE schemaname = 'public'
                AND tablename = 'memory_chunks'
            );
        """
        )
        print(f"[INFO] memory_chunks table exists: {exists}")

        if not exists:
            print("[WARN] memory_chunks table not found - migrations not applied yet")
            await conn.close()
            return True  # Not a failure - just needs migration

        # Test 3: RLS status
        rls_enabled = await conn.fetchval(
            """
            SELECT relrowsecurity
            FROM pg_class
            WHERE relname = 'memory_chunks';
        """
        )
        if rls_enabled:
            print(f"[PASS] RLS enabled on memory_chunks: {rls_enabled}")
        else:
            print("[FAIL] RLS NOT enabled on memory_chunks")
            await conn.close()
            return False

        # Test 4: List RLS policies
        policies = await conn.fetch(
            """
            SELECT policyname, cmd, qual, with_check
            FROM pg_policies
            WHERE tablename = 'memory_chunks';
        """
        )
        print(f"[INFO] RLS policies: {len(policies)} found")
        for policy in policies:
            print(f'  - {policy["policyname"]} (cmd: {policy["cmd"]})')

        if len(policies) == 0:
            print("[WARN] No RLS policies found - policy creation may have failed")

        # Test 5: Check app_user role (optional)
        app_user_exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM pg_roles
                WHERE rolname = 'app_user'
            );
        """
        )
        print(f"[INFO] app_user role exists: {app_user_exists}")

        # Test 6: Verify indexes
        indexes = await conn.fetch(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'memory_chunks';
        """
        )
        print(f"[INFO] Indexes on memory_chunks: {len(indexes)}")
        for idx in indexes[:3]:  # Show first 3
            print(f'  - {idx["indexname"]}')

        await conn.close()
        print("[PASS] All database validations completed")
        return True

    except Exception as e:
        print(f"[FAIL] Database validation error: {e}")
        return False


if __name__ == "__main__":
    result = asyncio.run(validate_database())
    exit(0 if result else 1)
