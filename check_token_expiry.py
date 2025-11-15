#!/usr/bin/env python3
"""Check OAuth token expiry details"""
import os
import sys
from datetime import datetime
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

    print("Checking OAuth token expiry for:")
    print(f"  Workspace: {workspace_id}")
    print(f"  Actor: {actor_id}")
    print()

    token_cache = OAuthTokenCache()
    try:
        tokens = token_cache.get_tokens("google", workspace_id, actor_id)
        if tokens:
            expires_at = tokens["expires_at"]
            now = datetime.now()

            time_remaining = (expires_at - now).total_seconds()

            print("[OK] Token found")
            print(f"  Access token: {tokens['access_token'][:20]}...")
            print(f"  Expires at: {expires_at}")
            print(f"  Current time: {now}")
            print(f"  Time remaining: {time_remaining:.1f} seconds ({time_remaining/60:.1f} minutes)")
            print()

            if time_remaining > 0:
                print("[OK] Token is VALID")
                if time_remaining < 60:
                    print("[WARN] Token expires in less than 1 minute!")
            else:
                print("[ERROR] Token is EXPIRED")
                print(f"  Expired {abs(time_remaining):.1f} seconds ago")
        else:
            print("[ERROR] No token found")
            sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Error checking token: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
