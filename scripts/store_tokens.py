"""Manually store OAuth tokens in database.

Use this if you already have access/refresh tokens from Google.
"""
import asyncio
import os
from pathlib import Path

from relay_ai.auth.oauth.tokens import OAuthTokenCache

# Load environment
env_file = Path(__file__).parent.parent / ".env.e2e"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key] = value


async def main():
    print("=" * 70)
    print("Manual Token Storage")
    print("=" * 70)
    print()

    # Fixed workspace UUID for E2E testing
    workspace_id = "00000000-0000-0000-0000-000000000e2e"
    actor_id = "kbmabb@gmail.com"

    print("Enter OAuth tokens (paste from previous run or from Google):")
    print()

    access_token = input("Access token: ").strip()
    refresh_token = input("Refresh token (press Enter if none): ").strip() or None
    expires_in = input("Expires in seconds (default 3600): ").strip() or "3600"
    scope = (
        input("Scopes (default gmail.send): ").strip()
        or "https://www.googleapis.com/auth/gmail.send openid email profile"
    )

    print()
    print("Storing tokens...")

    token_cache = OAuthTokenCache()
    await token_cache.store_tokens(
        provider="google",
        workspace_id=workspace_id,
        actor_id=actor_id,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=int(expires_in),
        scope=scope,
    )

    print("[OK] Tokens stored successfully!")
    print()
    print(f"Workspace ID: {workspace_id}")
    print(f"Actor ID: {actor_id}")
    print(f"Has refresh token: {bool(refresh_token)}")
    print()
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
