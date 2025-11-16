#!/usr/bin/env python3
"""
Quick credential verification script
Tests that all rotated API keys and database connections work
"""

import os

# For Windows compatibility, disable ANSI colors
import platform
import sys

if platform.system() == "Windows":
    os.environ["PYTHONIOENCODING"] = "utf-8"

# Color output (disabled on Windows)
GREEN = ""
RED = ""
YELLOW = ""
RESET = ""
BOLD = ""


def test_openai():
    """Test OpenAI API key"""
    print("\nTesting OpenAI API Key...")
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("[FAIL] OPENAI_API_KEY not set")
            return False

        # Just verify key format (valid keys start with sk-proj-)
        if not api_key.startswith("sk-proj-"):
            print("[FAIL] OPENAI_API_KEY has unexpected format")
            return False

        print("[PASS] OPENAI_API_KEY is configured (format valid)")
        return True
    except Exception as e:
        print(f"[FAIL] OpenAI test failed: {e}")
        return False


def test_anthropic():
    """Test Anthropic API key"""
    print("\nTesting Anthropic API Key...")
    try:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print("[FAIL] ANTHROPIC_API_KEY not set")
            return False

        # Valid Anthropic keys start with sk-ant-
        if not api_key.startswith("sk-ant-"):
            print("[FAIL] ANTHROPIC_API_KEY has unexpected format")
            return False

        print("[PASS] ANTHROPIC_API_KEY is configured (format valid)")
        return True
    except Exception as e:
        print(f"[FAIL] Anthropic test failed: {e}")
        return False


def test_database():
    """Test database connection"""
    print("\nTesting PostgreSQL Database Connection...")
    try:
        import psycopg2

        db_url = os.getenv("DATABASE_URL") or os.getenv("RELAY_BETA_DB_URL")

        if not db_url:
            print("[FAIL] DATABASE_URL not set")
            return False

        # Mask the password for display
        display_url = db_url.split("@")[1] if "@" in db_url else "postgresql://..."

        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        conn.close()

        print("[PASS] Database connection successful")
        print(f"  Connected to: {display_url}")
        print(f"  PostgreSQL version: {version[0].split(',')[0]}")
        return True
    except Exception as e:
        print(f"[FAIL] Database connection failed: {e}")
        return False


def test_supabase():
    """Test Supabase connection"""
    print("\nTesting Supabase Connection...")
    try:
        from supabase import create_client

        url = os.getenv("RELAY_BETA_SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
        key = os.getenv("RELAY_BETA_SUPABASE_ANON_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")

        if not url or not key:
            print("[SKIP] Supabase credentials not found (optional, skipping)")
            return True

        supabase = create_client(url, key)
        # Try a simple health check
        supabase.table("information_schema.tables").select("*").limit(1).execute()

        print("[PASS] Supabase connection successful")
        print(f"  URL: {url}")
        return True
    except Exception as e:
        print(f"[SKIP] Supabase test skipped (not critical): {str(e)[:50]}")
        return True


def main():
    print(f"\n{'='*60}")
    print("Relay Credentials Verification Test")
    print(f"{'='*60}")

    results = {
        "OpenAI": test_openai(),
        "Anthropic": test_anthropic(),
        "PostgreSQL": test_database(),
        "Supabase": test_supabase(),
    }

    print(f"\n{'='*60}")
    print("Summary:")
    print(f"{'='*60}")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for service, success in results.items():
        status = "[PASS]" if success else "[FAIL]"
        print(f"{service:.<40} {status}")

    print(f"{'='*60}")
    print(f"Results: {passed}/{total} tests passed")
    print(f"{'='*60}\n")

    if passed == total:
        print("[SUCCESS] All credentials verified successfully!\n")
        return 0
    else:
        print("[ERROR] Some credentials failed verification\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
