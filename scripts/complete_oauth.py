"""Complete OAuth flow with callback URL.

Usage: python complete_oauth.py "http://localhost:8003/oauth/google/callback?state=...&code=..."
"""
import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from relay_ai.auth.oauth.state import OAuthStateManager
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
    if len(sys.argv) < 2:
        print("ERROR: Missing callback URL")
        print('Usage: python complete_oauth.py "http://localhost:8003/oauth/google/callback?state=...&code=..."')
        sys.exit(1)

    callback_url = sys.argv[1]

    print("=" * 70)
    print("Completing OAuth Flow")
    print("=" * 70)
    print()

    # Parse callback URL
    parsed = urlparse(callback_url)
    params = parse_qs(parsed.query)

    if "error" in params:
        print(f"[ERROR] OAuth error: {params['error'][0]}")
        return

    if "code" not in params or "state" not in params:
        print("[ERROR] Invalid callback URL - missing code or state")
        return

    code = params["code"][0]
    returned_state = params["state"][0]

    print(f"Code: {code[:20]}...")
    print(f"State: {returned_state[:20]}...")
    print()

    # Validate state
    print("Validating state...")
    workspace_id = "00000000-0000-0000-0000-000000000e2e"  # E2E test workspace
    state_mgr = OAuthStateManager()

    validated_state = state_mgr.validate_state(workspace_id=workspace_id, state=returned_state)
    if not validated_state:
        print("[ERROR] State validation failed - state expired or invalid")
        return

    print("  State validated successfully")
    print()

    # Exchange code for tokens
    print("Exchanging code for tokens...")
    import httpx

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": validated_state["redirect_uri"],
        "grant_type": "authorization_code",
        "code_verifier": validated_state.get("code_verifier"),
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(token_url, data=token_data)
        if response.status_code != 200:
            print(f"[ERROR] Token exchange failed: {response.status_code}")
            print(f"  Response: {response.text[:200]}")
            return

        token_response = response.json()

    access_token = token_response.get("access_token")
    refresh_token = token_response.get("refresh_token")
    expires_in = token_response.get("expires_in")
    scope = token_response.get("scope")

    if not access_token:
        print("[ERROR] No access token in response")
        return

    print(f"  Access token: {access_token[:20]}...")
    print(f"  Refresh token: {'Yes' if refresh_token else 'No'}")
    print(f"  Expires in: {expires_in}s")
    print(f"  Scopes: {scope}")
    print()

    # Store tokens
    print("Storing tokens in database...")
    actor_id = "kbmabb@gmail.com"

    token_cache = OAuthTokenCache()
    await token_cache.store_tokens(
        provider="google",
        workspace_id=workspace_id,
        actor_id=actor_id,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        scope=scope,
    )

    print("[OK] Tokens stored successfully!")
    print()
    print("=" * 70)
    print("SUCCESS! OAuth setup complete.")
    print()
    print(f"Workspace ID: {workspace_id}")
    print(f"Actor ID: {actor_id}")
    print(f"Has refresh token: {bool(refresh_token)}")
    print()
    print("You can now run E2E tests with:")
    print("  python scripts/e2e_gmail_test.py --scenarios all --verbose")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
