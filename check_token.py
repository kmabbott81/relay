#!/usr/bin/env python3
"""Check OAuth token status"""
import os
import sys
from pathlib import Path

from relay_ai.auth.oauth.tokens import OAuthTokenCache

# Load .env.e2e
env_file = Path(__file__).parent / ".env.e2e"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key] = value


def main():
    workspace_id = "00000000-0000-0000-0000-000000000e2e"
    actor_id = "kbmabb@gmail.com"

    print("Checking OAuth token for:")
    print(f"  Workspace: {workspace_id}")
    print(f"  Actor: {actor_id}")
    print()

    token_cache = OAuthTokenCache()
    try:
        tokens = token_cache.get_tokens("google", workspace_id, actor_id)
        if tokens:
            print("[OK] OAuth token is VALID")
            print(f"  Access token: {tokens['access_token'][:20]}...")
            print(f"  Has refresh token: {bool(tokens.get('refresh_token'))}")
            print()
            print("Ready to run E2E tests!")
        else:
            print("[ERROR] OAuth token is MISSING or EXPIRED")
            print()
            print("To re-authorize:")
            print("  python scripts/oauth/manual_token_setup.py")
            sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Error checking token: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
