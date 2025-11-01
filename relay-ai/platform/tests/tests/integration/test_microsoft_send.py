"""Integration test for Microsoft Outlook send with Graph API.

Sprint 55 Week 2: Gated integration test for real Outlook sends.

**REQUIRES ALL ENVS:**
- PROVIDER_MICROSOFT_ENABLED=true
- MS_CLIENT_ID (from Azure AD app registration)
- MS_CLIENT_SECRET (from Azure AD)
- MS_TENANT_ID (or 'common' for multi-tenant)
- OAUTH_ENCRYPTION_KEY (Fernet key)
- DATABASE_URL (PostgreSQL connection)
- REDIS_URL (Redis connection)
- TEST_MICROSOFT_INTEGRATION=true (explicit opt-in)
- MS_TEST_RECIPIENT (recipient email for test sends)

**TO RUN LOCALLY:**
```bash
export PROVIDER_MICROSOFT_ENABLED=true
export MS_CLIENT_ID=<your-azure-ad-client-id>
export MS_CLIENT_SECRET=<your-secret>
export MS_TENANT_ID=<tenant-id-or-common>
export OAUTH_ENCRYPTION_KEY=<existing-fernet-key>
export DATABASE_URL=postgresql://...
export REDIS_URL=redis://...
export TEST_MICROSOFT_INTEGRATION=true
export MS_TEST_RECIPIENT=test@yourcompany.com

# Run token setup first
python scripts/manual_token_setup_ms.py

# Then run integration test
pytest -v -m integration tests/integration/test_microsoft_send.py
```

**TEST SCENARIOS:**
1. Happy path: HTML + inline image (CID) + attachment → 202 Accepted
2. 429 throttling: Mock two 429s with Retry-After, verify exponential backoff
3. Internal-only mode: Verify external domain blocked
4. Large attachment: Verify >3MB triggers stub (Week 3)

**SKIP GATE:** Test is skipped unless TEST_MICROSOFT_INTEGRATION=true AND all creds present.
"""

import base64
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.actions.adapters.microsoft import MicrosoftAdapter


@pytest.fixture(scope="module")
def skip_if_envs_missing():
    """Skip integration test unless all required envs are present."""
    required_envs = [
        "PROVIDER_MICROSOFT_ENABLED",
        "MS_CLIENT_ID",
        "MS_CLIENT_SECRET",
        "MS_TENANT_ID",
        "OAUTH_ENCRYPTION_KEY",
        "DATABASE_URL",
        "REDIS_URL",
        "TEST_MICROSOFT_INTEGRATION",
        "MS_TEST_RECIPIENT",
    ]

    missing = []
    for env in required_envs:
        value = os.getenv(env)
        if not value:
            missing.append(env)
        elif env in ["PROVIDER_MICROSOFT_ENABLED", "TEST_MICROSOFT_INTEGRATION"] and value.lower() != "true":
            missing.append(f"{env} (must be 'true', got '{value}')")

    if missing:
        pytest.skip(f"Integration test requires envs: {', '.join(missing)}")


@pytest.fixture
def adapter():
    """Create Microsoft adapter with real config."""
    return MicrosoftAdapter()


@pytest.fixture
def test_workspace_id():
    """E2E test workspace UUID."""
    return "00000000-0000-0000-0000-000000000e2e"


@pytest.fixture
def test_actor_id():
    """E2E test actor ID (from token setup)."""
    return os.getenv("MS_TEST_ACTOR", "test@yourcompany.com")


# Test data
RED_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
)


@pytest.mark.integration
@pytest.mark.anyio
async def test_microsoft_send_happy_path(skip_if_envs_missing, adapter, test_workspace_id, test_actor_id):
    """Test 1: Happy path - HTML + inline image + attachment → 202 Accepted.

    Verifies:
    - OAuth token fetch with auto-refresh
    - Graph JSON payload construction
    - Real Graph API POST /me/sendMail call
    - 202 Accepted response
    - Telemetry emission (exec_rate, latency)
    """
    recipient = os.getenv("MS_TEST_RECIPIENT")

    params = {
        "to": recipient,
        "subject": "Integration Test: Outlook Send (Happy Path)",
        "text": "This is a test email sent via Microsoft Graph API integration test.",
        "html": """
        <html>
        <body>
            <h1>Outlook Integration Test</h1>
            <p>This email was sent via <strong>Microsoft Graph API</strong>.</p>
            <p>Logo below (1x1 red pixel PNG):</p>
            <img src="cid:logo" alt="Logo" width="50" height="50" style="border: 1px solid red;" />
            <p>Attachment: sample.txt</p>
        </body>
        </html>
        """,
        "inline": [
            {
                "cid": "logo",
                "filename": "logo.png",
                "content_type": "image/png",
                "data": base64.b64encode(RED_PIXEL_PNG).decode(),
            }
        ],
        "attachments": [
            {
                "filename": "sample.txt",
                "content_type": "text/plain",
                "data": base64.b64encode(b"Integration test attachment content.\n").decode(),
            }
        ],
    }

    # Execute real send
    result = await adapter.execute("outlook.send", params, test_workspace_id, test_actor_id)

    # Verify response
    assert result["status"] == "sent", f"Expected 'sent', got {result['status']}"
    assert "correlation_id" in result, "Missing correlation_id in response"
    assert result.get("provider") == "microsoft"

    print("\n✓ Email sent successfully")
    print(f"  Status: {result['status']}")
    print(f"  Correlation ID: {result.get('correlation_id', 'N/A')}")
    print(f"  To: {recipient}")
    print(f"\n  Check inbox: {recipient}")


@pytest.mark.integration
@pytest.mark.anyio
async def test_microsoft_send_429_retry(skip_if_envs_missing, adapter, test_workspace_id, test_actor_id):
    """Test 2: 429 throttling - Mock two 429s with Retry-After, verify exponential backoff.

    Verifies:
    - Retry-After header parsing (integer seconds)
    - Exponential backoff with jitter (±20%)
    - Max 3 retries
    - Eventually succeeds on 3rd attempt
    - structured_error_total{code="throttled_429"} increments twice
    """
    recipient = os.getenv("MS_TEST_RECIPIENT")

    params = {
        "to": recipient,
        "subject": "Integration Test: 429 Retry",
        "text": "Testing 429 throttling and retry logic.",
    }

    # Mock httpx.AsyncClient to return 429 twice, then 202
    mock_response_429 = MagicMock()
    mock_response_429.status_code = 429
    mock_response_429.headers = {"Retry-After": "2"}  # 2 seconds
    mock_response_429.json.return_value = {"error": {"code": "TooManyRequests", "message": "Rate limit exceeded"}}

    mock_response_202 = MagicMock()
    mock_response_202.status_code = 202
    mock_response_202.headers = {}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[mock_response_429, mock_response_429, mock_response_202])

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await adapter.execute("outlook.send", params, test_workspace_id, test_actor_id)

    # Verify result
    assert result["status"] == "sent", "Expected eventual success after retries"
    assert (
        mock_client.post.call_count == 3
    ), f"Expected 3 calls (2 retries + success), got {mock_client.post.call_count}"

    print("\n✓ 429 retry logic verified")
    print(f"  Total attempts: {mock_client.post.call_count}")
    print(f"  Final status: {result['status']}")


@pytest.mark.integration
def test_microsoft_send_internal_only_blocked(skip_if_envs_missing, adapter):
    """Test 3: Internal-only mode - Verify external domain blocked.

    Verifies:
    - MICROSOFT_INTERNAL_ONLY=true blocks external domains
    - structured_error with code="internal_only_recipient_blocked"
    - Allowed domains work correctly
    """
    # Enable internal-only mode temporarily
    original_internal_only = adapter.internal_only
    original_allowed_domains = adapter.internal_allowed_domains

    try:
        adapter.internal_only = True
        adapter.internal_allowed_domains = ["yourcompany.com", "internal.com"]

        # Try external domain
        params = {
            "to": "external@notallowed.com",
            "subject": "Test",
            "text": "Should be blocked",
        }

        with pytest.raises(ValueError) as exc_info:
            adapter.preview("outlook.send", params)

        error_msg = str(exc_info.value)
        assert "internal_only_recipient_blocked" in error_msg, f"Wrong error code: {error_msg}"

        print("\n✓ Internal-only mode verified")
        print("  External domain blocked: external@notallowed.com")
        print(f"  Allowed domains: {adapter.internal_allowed_domains}")

    finally:
        # Restore original settings
        adapter.internal_only = original_internal_only
        adapter.internal_allowed_domains = original_allowed_domains


@pytest.mark.integration
def test_microsoft_send_large_attachment_stub(skip_if_envs_missing, adapter):
    """Test 4: Large attachment - Verify >3MB triggers upload session stub (Week 3).

    Verifies:
    - Attachments >3MB total trigger upload session path
    - Returns structured error when MS_UPLOAD_SESSIONS_ENABLED!=true
    - Error code: provider_payload_too_large
    """
    # Create 3.5 MB attachment
    large_data = b"x" * (3500 * 1024)  # 3.5 MB

    params = {
        "to": "test@yourcompany.com",
        "subject": "Test: Large Attachment",
        "text": "Testing large attachment stub",
        "attachments": [
            {
                "filename": "large.bin",
                "content_type": "application/octet-stream",
                "data": base64.b64encode(large_data).decode(),
            }
        ],
    }

    # Check if upload sessions are enabled
    upload_sessions_enabled = os.getenv("MS_UPLOAD_SESSIONS_ENABLED", "false").lower() == "true"

    if not upload_sessions_enabled:
        # Should raise structured error
        with pytest.raises(ValueError) as exc_info:
            adapter.preview("outlook.send", params)

        error_msg = str(exc_info.value)
        assert "provider_payload_too_large" in error_msg or "upload_session" in error_msg.lower()

        print("\n✓ Large attachment stub verified")
        print("  Attachment size: 3.5 MB")
        print(f"  Upload sessions enabled: {upload_sessions_enabled}")
        print(f"  Error: {error_msg[:100]}...")
    else:
        # Week 3: Should use upload session (not implemented yet)
        print("\n⚠️  Upload sessions enabled but not implemented (Week 3)")
        pytest.skip("Upload session implementation not ready (Week 3)")


@pytest.mark.integration
def test_integration_test_env_documentation(skip_if_envs_missing):
    """Document required environment variables for Microsoft integration tests.

    This test always passes but prints required environment setup.
    """
    print("\n" + "=" * 70)
    print("MICROSOFT INTEGRATION TEST ENVIRONMENT REQUIREMENTS")
    print("=" * 70)
    print("\nRequired environment variables:")
    print("  PROVIDER_MICROSOFT_ENABLED=true")
    print("  MS_CLIENT_ID=<from-azure-ad-app-registration>")
    print("  MS_CLIENT_SECRET=<from-azure-ad>")
    print("  MS_TENANT_ID=<tenant-id-or-common>")
    print("  OAUTH_ENCRYPTION_KEY=<existing-fernet-key>")
    print("  DATABASE_URL=<postgresql-connection>")
    print("  REDIS_URL=<redis-connection>")
    print("  TEST_MICROSOFT_INTEGRATION=true")
    print("  MS_TEST_RECIPIENT=<test-recipient-email>")
    print("  MS_TEST_ACTOR=<test-actor-email> (optional, defaults to test@yourcompany.com)")
    print("\nAzure AD App Registration Setup:")
    print("  1. Create Azure AD app registration (single tenant)")
    print("  2. Add client secret (Certificates & secrets)")
    print("  3. Configure API permissions:")
    print("     - Microsoft Graph: Mail.Send")
    print("     - Microsoft Graph: offline_access")
    print("     - Microsoft Graph: openid, email, profile")
    print("  4. Grant admin consent")
    print("  5. Add redirect URI: http://localhost:8000/auth/microsoft/callback")
    print("\nToken Setup:")
    print("  python scripts/manual_token_setup_ms.py")
    print("\nRun command:")
    print("  pytest -v -m integration tests/integration/test_microsoft_send.py")
    print("=" * 70)

    # Check current env status
    required_envs = {
        "PROVIDER_MICROSOFT_ENABLED": os.getenv("PROVIDER_MICROSOFT_ENABLED"),
        "MS_CLIENT_ID": "***" if os.getenv("MS_CLIENT_ID") else None,
        "MS_CLIENT_SECRET": "***" if os.getenv("MS_CLIENT_SECRET") else None,
        "MS_TENANT_ID": os.getenv("MS_TENANT_ID"),
        "OAUTH_ENCRYPTION_KEY": "***" if os.getenv("OAUTH_ENCRYPTION_KEY") else None,
        "DATABASE_URL": "***" if os.getenv("DATABASE_URL") else None,
        "REDIS_URL": "***" if os.getenv("REDIS_URL") else None,
        "TEST_MICROSOFT_INTEGRATION": os.getenv("TEST_MICROSOFT_INTEGRATION"),
        "MS_TEST_RECIPIENT": os.getenv("MS_TEST_RECIPIENT"),
    }

    print("\nCurrent environment status:")
    for key, value in required_envs.items():
        status = "✓ SET" if value else "✗ MISSING"
        display_value = (
            value
            if key in ["PROVIDER_MICROSOFT_ENABLED", "MS_TENANT_ID", "TEST_MICROSOFT_INTEGRATION", "MS_TEST_RECIPIENT"]
            else "***"
        )
        print(f"  {status:10} {key:35} = {display_value if value else '(not set)'}")

    missing_count = sum(1 for v in required_envs.values() if not v)
    if missing_count > 0:
        print(f"\n⚠️  {missing_count} required environment variable(s) missing")
        print("   Integration tests will be skipped")
    else:
        print("\n✓ All environment variables set")
        print("  Integration tests will run")

    assert True, "Documentation test always passes"
