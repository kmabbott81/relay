"""Manually set up Microsoft OAuth tokens by completing the flow via script.

This bypasses the web UI and does everything programmatically for Microsoft Graph API.
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
required = ["MS_CLIENT_ID", "MS_CLIENT_SECRET", "MS_TENANT_ID", "DATABASE_URL", "REDIS_URL", "OAUTH_ENCRYPTION_KEY"]
missing = [k for k in required if not os.getenv(k)]
if missing:
    print(f"ERROR: Missing environment variables: {', '.join(missing)}")
    print("Make sure .env.e2e is properly configured")
    print()
    print("Required Microsoft variables:")
    print("  MS_CLIENT_ID=<your-azure-ad-client-id>")
    print("  MS_CLIENT_SECRET=<your-azure-ad-client-secret>")
    print("  MS_TENANT_ID=<your-tenant-id-or-common>")
    print("  MS_REDIRECT_URI=http://localhost:8000/auth/microsoft/callback")
    print()
    print("See: docs/specs/MS-OAUTH-SETUP-GUIDE.md")
    sys.exit(1)

print("=" * 70)
print("🔐 Microsoft OAuth Token Setup - Manual Flow")
print("=" * 70)
print()


async def main():
    # Step 1: Create state with PKCE
    print("[Step 1/4] Creating OAuth state with PKCE...")

    # Use a fixed UUID for E2E testing (so it's consistent across runs)
    workspace_id = "00000000-0000-0000-0000-000000000e2e"  # E2E test workspace UUID
    state_mgr = OAuthStateManager()

    print(f"  Backend: {state_mgr.backend}")

    state_data = state_mgr.create_state(
        workspace_id=workspace_id,
        provider="microsoft",
        redirect_uri=os.getenv("MS_REDIRECT_URI", "http://localhost:8000/auth/microsoft/callback"),
        use_pkce=True,  # Azure AD requires PKCE for public clients
    )

    state = state_data["state"]
    code_challenge = state_data["code_challenge"]

    print(f"  State: {state[:20]}...")
    print(f"  Code challenge: {code_challenge[:20]}...")
    print()

    # Step 2: Build authorization URL
    print("[Step 2/4] Building Azure AD authorization URL...")
    client_id = os.getenv("MS_CLIENT_ID")
    tenant_id = os.getenv("MS_TENANT_ID", "common")
    redirect_uri = os.getenv("MS_REDIRECT_URI", "http://localhost:8000/auth/microsoft/callback")

    # Microsoft Graph scopes
    scopes = [
        "https://graph.microsoft.com/Mail.Send",
        "offline_access",  # Required for refresh tokens
        "openid",
        "email",
        "profile",
    ]

    import urllib.parse

    auth_params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    authorize_url = (
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize?{urllib.parse.urlencode(auth_params)}"
    )

    print()
    print("  ✅ Configuration loaded:")
    print(f"     Client ID: {client_id[:12]}****{client_id[-4:]}")
    print(f"     Tenant ID: {tenant_id}")
    print(f"     Redirect URI: {redirect_uri}")
    print()
    print("  📋 Visit this URL in your browser:")
    print(f"  {authorize_url}")
    print()

    # Step 3: Get authorization code from user
    print("[Step 3/4] Waiting for authorization...")
    print()
    print("  After approving (and admin consent if required), you'll be redirected to:")
    print(f"  {redirect_uri}?code=XXX&state=YYY")
    print()
    print("  ⚠️  Copy the ENTIRE redirect URL and paste it here:")
    print()

    callback_url = input("  Redirect URL: ").strip()

    # Parse callback URL
    from urllib.parse import parse_qs, urlparse

    parsed = urlparse(callback_url)
    params = parse_qs(parsed.query)

    if "error" in params:
        error = params["error"][0]
        error_description = params.get("error_description", [""])[0]
        print(f"\n❌ [ERROR] OAuth error: {error}")
        if error_description:
            print(f"  Description: {error_description}")
        print()
        print("Common errors:")
        print("  - AADSTS50011: Redirect URI mismatch (check Azure portal)")
        print("  - AADSTS65001: User consent required (admin must grant consent)")
        print("  - AADSTS700016: Application not found (check client ID)")
        return

    if "code" not in params or "state" not in params:
        print("\n❌ [ERROR] Invalid callback URL - missing code or state")
        print(f"  Received params: {list(params.keys())}")
        return

    code = params["code"][0]
    returned_state = params["state"][0]

    print(f"\n  ✅ Code: {code[:20]}...")
    print(f"  ✅ State: {returned_state[:20]}...")
    print()

    # Step 4: Validate state and exchange code for tokens
    print("[Step 4/4] Validating state and exchanging code for tokens...")

    # CSRF protection: Compare returned state with original using constant-time comparison
    import hmac

    if not hmac.compare_digest(returned_state, state):
        print("❌ [ERROR] CSRF protection failed - state mismatch")
        print(f"  Expected: {state[:20]}...")
        print(f"  Received: {returned_state[:20]}...")
        print("  This could indicate a CSRF attack or OAuth callback tampering.")
        sys.exit(1)

    validated_state = state_mgr.validate_state(workspace_id=workspace_id, state=returned_state)
    if not validated_state:
        print("❌ [ERROR] State validation failed - state expired or invalid")
        print("  Try running the script again to get a fresh state")
        return

    print("  ✅ State validated successfully")

    # Exchange code for tokens using Microsoft token endpoint
    import httpx

    client_id = os.getenv("MS_CLIENT_ID")
    client_secret = os.getenv("MS_CLIENT_SECRET")
    tenant_id = os.getenv("MS_TENANT_ID", "common")

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": validated_state["redirect_uri"],
        "grant_type": "authorization_code",
        "code_verifier": validated_state.get("code_verifier"),  # PKCE verifier
    }

    print("  🔄 Calling Microsoft token endpoint...")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(token_url, data=token_data)
        if response.status_code != 200:
            print(f"❌ [ERROR] Token exchange failed: {response.status_code}")
            print(f"  Response: {response.text[:500]}")
            print()
            print("Common token exchange errors:")
            print("  - invalid_client: Check MS_CLIENT_SECRET")
            print("  - invalid_grant: Authorization code expired or already used")
            print("  - redirect_uri_mismatch: Redirect URI must match exactly")
            return

        token_response = response.json()

    access_token = token_response.get("access_token")
    refresh_token = token_response.get("refresh_token")
    expires_in = token_response.get("expires_in")
    scope = token_response.get("scope")
    token_type = token_response.get("token_type")

    if not access_token:
        print("❌ [ERROR] No access token in response")
        print(f"  Response keys: {list(token_response.keys())}")
        return

    print(f"  ✅ Access token: {access_token[:20]}...")
    print(f"  ✅ Refresh token: {'Yes ✓' if refresh_token else 'No ✗ (missing offline_access scope?)'}")
    print(f"  ✅ Token type: {token_type}")
    print(f"  ✅ Expires in: {expires_in}s ({expires_in // 60} minutes)")
    print(f"  ✅ Scopes granted: {scope}")
    print()

    if not refresh_token:
        print("⚠️  WARNING: No refresh token received!")
        print("   Make sure 'offline_access' scope was requested and granted.")
        print("   Without a refresh token, access will expire after 1 hour.")
        print()

    # Store tokens
    print("💾 Storing tokens in database...")
    actor_id = os.getenv("MS_TEST_ACTOR", "test@yourcompany.com")  # E2E test actor

    token_cache = OAuthTokenCache()
    await token_cache.store_tokens(
        provider="microsoft",
        workspace_id=workspace_id,
        actor_id=actor_id,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        scope=scope,
    )

    print("  ✅ Tokens stored successfully!")
    print(f"     Workspace: {workspace_id}")
    print(f"     Actor: {actor_id}")
    print("     Storage: Database + Redis cache")
    print()

    # Verify tokens can be retrieved
    print("🔍 Verifying token retrieval...")
    retrieved_tokens = await token_cache.get_tokens(
        provider="microsoft",
        workspace_id=workspace_id,
        actor_id=actor_id,
    )

    if retrieved_tokens:
        print("  ✅ Tokens retrieved successfully from cache")
        print(f"     Expires at: {retrieved_tokens.get('expires_at', 'N/A')}")
    else:
        print("  ⚠️  WARNING: Could not retrieve tokens from cache")

    print()
    print("=" * 70)
    print("🎉 SUCCESS! Microsoft OAuth setup complete.")
    print()
    print("Next steps:")
    print("  1. Test email send via integration test:")
    print("     export TEST_MICROSOFT_INTEGRATION=true")
    print("     export MS_TEST_RECIPIENT=test@yourcompany.com")
    print("     pytest tests/integration/test_microsoft_send.py -v")
    print()
    print("  2. Or send email directly via adapter:")
    print('     python -c "')
    print("       from relay_ai.actions.adapters.microsoft import MicrosoftAdapter")
    print("       import asyncio")
    print("       async def test():")
    print("           adapter = MicrosoftAdapter()")
    print("           result = await adapter.execute('outlook.send', {")
    print("               'to': 'test@yourcompany.com',")
    print("               'subject': 'Test from Microsoft OAuth',")
    print("               'text': 'This email was sent via Microsoft Graph API',")
    print("           }, '00000000-0000-0000-0000-000000000e2e', 'test@yourcompany.com')")
    print("           print(result)")
    print("       asyncio.run(test())")
    print('     "')
    print()
    print("  3. Check telemetry in Prometheus:")
    print("     job:outlook_send_exec_rate:5m")
    print("     job:outlook_send_latency_p95:5m")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
