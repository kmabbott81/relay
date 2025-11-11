"""Manually set up OAuth tokens by completing the flow via script.

This bypasses the web UI and does everything programmatically.
"""
import asyncio
import os
import sys
from pathlib import Path

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

# Verify required environment variables
required = ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "DATABASE_URL", "REDIS_URL", "OAUTH_ENCRYPTION_KEY"]
missing = [k for k in required if not os.getenv(k)]
if missing:
    print(f"ERROR: Missing environment variables: {', '.join(missing)}")
    print("Make sure .env.e2e is properly configured")
    sys.exit(1)

print("=" * 70)
print("Manual OAuth Token Setup")
print("=" * 70)
print()


async def main():
    # Step 1: Create state
    print("[Step 1/4] Creating OAuth state...")

    # Use a fixed UUID for E2E testing (so it's consistent across runs)
    workspace_id = "00000000-0000-0000-0000-000000000e2e"  # E2E test workspace UUID
    state_mgr = OAuthStateManager()

    print(f"  Backend: {state_mgr.backend}")

    state_data = state_mgr.create_state(
        workspace_id=workspace_id,
        provider="google",
        redirect_uri="http://localhost:8003/oauth/google/callback",
        use_pkce=True,
    )

    state = state_data["state"]
    code_challenge = state_data["code_challenge"]

    print(f"  State: {state[:20]}...")
    print(f"  Code challenge: {code_challenge[:20]}...")
    print()

    # Step 2: Build authorization URL
    print("[Step 2/4] Building authorization URL...")
    client_id = os.getenv("GOOGLE_CLIENT_ID")

    import urllib.parse

    auth_params = {
        "client_id": client_id,
        "redirect_uri": "http://localhost:8003/oauth/google/callback",
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/gmail.send openid email profile",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
    }

    authorize_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(auth_params)}"

    print("  Visit this URL:")
    print(f"  {authorize_url}")
    print()

    # Step 3: Get authorization code from user
    print("[Step 3/4] Waiting for authorization...")
    print()
    print("  After approving, you'll be redirected to a URL like:")
    print("  http://localhost:8003/oauth/google/callback?state=XXX&code=YYY")
    print()
    print("  Copy the ENTIRE redirect URL and paste it here:")
    print()

    callback_url = input("  Redirect URL: ").strip()

    # Parse callback URL
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(callback_url)
    params = parse_qs(parsed.query)

    if "error" in params:
        print(f"\n[ERROR] OAuth error: {params['error'][0]}")
        return

    if "code" not in params or "state" not in params:
        print("\n[ERROR] Invalid callback URL - missing code or state")
        return

    code = params["code"][0]
    returned_state = params["state"][0]

    print(f"\n  Code: {code[:20]}...")
    print(f"  State: {returned_state[:20]}...")
    print()

    # Step 4: Validate state
    print("[Step 4/4] Validating state and exchanging code for tokens...")

    validated_state = state_mgr.validate_state(workspace_id=workspace_id, state=returned_state)
    if not validated_state:
        print("[ERROR] State validation failed - state expired or invalid")
        return

    print("  State validated successfully")

    # Exchange code for tokens
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
    actor_id = "kbmabb@gmail.com"  # E2E test actor

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
    print("You can now run E2E tests with:")
    print("  python scripts/e2e_gmail_test.py --scenarios all --verbose")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
