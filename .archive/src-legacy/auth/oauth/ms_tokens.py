"""Microsoft OAuth 2.0 token management with PKCE and Azure AD.

Sprint 55 Phase 1: Microsoft Outlook integration OAuth flow.

This module provides Microsoft-specific OAuth token management:
- Azure AD OAuth 2.0 with PKCE (Proof Key for Code Exchange)
- offline_access scope for refresh tokens
- Reuses OAuthTokenCache for storage (database + Redis)
- Reuses OAuthStateManager for CSRF protection
- Telemetry: oauth_events_total{provider="microsoft",event=...}

Example usage:
    # Step 1: Generate authorization URL
    from relay_ai.auth.oauth.ms_tokens import build_consent_url

    url = build_consent_url(
        workspace_id="ws_123",
        actor_id="user_456",
        redirect_uri="https://example.com/oauth/callback"
    )
    # Redirect user to `url`

    # Step 2: Exchange authorization code for tokens
    from relay_ai.auth.oauth.ms_tokens import exchange_code_for_tokens

    await exchange_code_for_tokens(
        workspace_id="ws_123",
        actor_id="user_456",
        code="authorization_code_from_callback",
        state="state_from_callback"
    )

    # Step 3: Get tokens with auto-refresh
    from relay_ai.auth.oauth.ms_tokens import get_tokens

    tokens = await get_tokens(workspace_id="ws_123", actor_id="user_456")
    # Use tokens["access_token"] for Graph API calls
"""

import os
from datetime import datetime, timedelta
from typing import Optional

import httpx


class MSTokenError(Exception):
    """Base exception for Microsoft OAuth token errors."""

    pass


class MSAuthorizationError(MSTokenError):
    """Raised when authorization fails."""

    pass


class MSRefreshError(MSTokenError):
    """Raised when token refresh fails."""

    pass


def build_consent_url(
    workspace_id: str,
    actor_id: str,
    redirect_uri: str,
    scopes: Optional[list[str]] = None,
) -> dict[str, str]:
    """Build Microsoft Azure AD consent URL with PKCE.

    Args:
        workspace_id: Workspace identifier
        actor_id: User/actor identifier
        redirect_uri: OAuth callback URL
        scopes: List of permission scopes (default: Mail.Send + offline_access)

    Returns:
        Dictionary with:
        - consent_url: URL to redirect user to for authorization
        - state: CSRF token (validate in callback)

    Raises:
        ValueError: If MS_CLIENT_ID or MS_TENANT_ID not configured

    Example:
        result = build_consent_url(
            workspace_id="ws_123",
            actor_id="user_456",
            redirect_uri="https://example.com/oauth/callback"
        )
        # Redirect user to result["consent_url"]
        # Store result["state"] for validation
    """
    from relay_ai.auth.oauth.state import OAuthStateManager

    # Get Microsoft OAuth credentials
    client_id = os.getenv("MS_CLIENT_ID")
    tenant_id = os.getenv("MS_TENANT_ID", "common")  # "common" for multi-tenant

    if not client_id:
        raise ValueError("MS_CLIENT_ID not configured")

    # Default scopes: Mail.Send (send emails) + offline_access (refresh token)
    if scopes is None:
        scopes = ["https://graph.microsoft.com/Mail.Send", "offline_access"]

    # Create OAuth state with PKCE
    state_manager = OAuthStateManager()
    state_data = state_manager.create_state(
        workspace_id=workspace_id,
        provider="microsoft",
        redirect_uri=redirect_uri,
        use_pkce=True,  # Azure AD requires PKCE for public clients
    )

    # Build authorization URL
    # Microsoft identity platform v2.0 endpoint
    base_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": " ".join(scopes),
        "state": state_data["state"],
        "code_challenge": state_data["code_challenge"],
        "code_challenge_method": state_data["code_challenge_method"],
        "prompt": "select_account",  # Let user choose account
    }

    # Build query string manually (httpx.URL handles encoding)
    from httpx import QueryParams

    query_string = QueryParams(params)
    consent_url = f"{base_url}?{query_string}"

    return {
        "consent_url": consent_url,
        "state": state_data["state"],
    }


async def exchange_code_for_tokens(
    workspace_id: str,
    actor_id: str,
    code: str,
    state: str,
    redirect_uri: Optional[str] = None,
) -> dict[str, any]:
    """Exchange authorization code for access + refresh tokens.

    Args:
        workspace_id: Workspace identifier
        actor_id: User/actor identifier
        code: Authorization code from OAuth callback
        state: State parameter from OAuth callback (for validation)
        redirect_uri: Redirect URI (must match consent URL)

    Returns:
        Dictionary with:
        - access_token: Access token for Graph API
        - refresh_token: Refresh token for token renewal
        - expires_at: Token expiration datetime
        - scope: Granted scopes (space-separated)

    Raises:
        MSAuthorizationError: If code exchange fails
        ValueError: If state validation fails

    Example:
        tokens = await exchange_code_for_tokens(
            workspace_id="ws_123",
            actor_id="user_456",
            code=request.args.get("code"),
            state=request.args.get("state")
        )
    """
    from relay_ai.auth.oauth.state import OAuthStateManager
    from relay_ai.auth.oauth.tokens import OAuthTokenCache
    from relay_ai.telemetry import oauth_events

    # Validate state (CSRF protection)
    state_manager = OAuthStateManager()
    state_data = state_manager.validate_state(workspace_id=workspace_id, state=state)

    if not state_data:
        oauth_events.labels(provider="microsoft", event="state_invalid").inc()
        raise ValueError("Invalid or expired OAuth state parameter")

    # Use redirect_uri from state if not provided
    redirect_uri = redirect_uri or state_data.get("redirect_uri")

    # Get Microsoft OAuth credentials
    client_id = os.getenv("MS_CLIENT_ID")
    tenant_id = os.getenv("MS_TENANT_ID", "common")

    if not client_id:
        raise ValueError("MS_CLIENT_ID not configured")

    # Exchange code for tokens
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_data = {
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": state_data.get("code_verifier"),  # PKCE code verifier
    }

    # Add client_secret if configured (confidential client)
    client_secret = os.getenv("MS_CLIENT_SECRET")
    if client_secret:
        token_data["client_secret"] = client_secret

    oauth_events.labels(provider="microsoft", event="code_exchange_start").inc()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(token_url, data=token_data)

            if response.status_code != 200:
                oauth_events.labels(provider="microsoft", event="code_exchange_failed").inc()
                error_detail = response.json().get("error_description", response.text[:200])
                raise MSAuthorizationError(f"Token exchange failed: {response.status_code} {error_detail}")

            token_response = response.json()
    except httpx.TimeoutException as e:
        oauth_events.labels(provider="microsoft", event="code_exchange_timeout").inc()
        raise MSAuthorizationError("Token exchange timeout") from e

    # Extract tokens
    access_token = token_response.get("access_token")
    refresh_token = token_response.get("refresh_token")
    expires_in = token_response.get("expires_in", 3600)
    scope = token_response.get("scope", "")

    if not access_token:
        oauth_events.labels(provider="microsoft", event="code_exchange_no_token").inc()
        raise MSAuthorizationError("No access token in response")

    # Store tokens in cache
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

    oauth_events.labels(provider="microsoft", event="code_exchange_ok").inc()

    # Return token dict
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
        "scope": scope,
    }


async def get_tokens(workspace_id: str, actor_id: str) -> Optional[dict[str, any]]:
    """Get Microsoft OAuth tokens with automatic refresh if expiring.

    This is the primary function for getting tokens in application code.
    Handles token refresh automatically if token is expiring within 30 seconds.

    Args:
        workspace_id: Workspace identifier
        actor_id: User/actor identifier

    Returns:
        Dictionary with access_token, refresh_token, expires_at, scope
        or None if no tokens exist

    Raises:
        MSRefreshError: If token expired and refresh failed

    Example:
        tokens = await get_tokens("ws_123", "user_456")
        if tokens:
            # Use tokens["access_token"] for Graph API
            graph_client = GraphClient(access_token=tokens["access_token"])
    """
    from relay_ai.auth.oauth.tokens import OAuthTokenCache

    token_cache = OAuthTokenCache()

    # Use built-in auto-refresh logic from OAuthTokenCache
    # This handles Redis lock and refresh stampede prevention
    try:
        tokens = await token_cache.get_tokens_with_auto_refresh(
            provider="microsoft", workspace_id=workspace_id, actor_id=actor_id
        )
        return tokens
    except Exception as e:
        # If refresh fails, token_cache raises HTTPException
        # Wrap it in MSRefreshError for Microsoft-specific handling
        raise MSRefreshError(f"Token refresh failed: {e}") from e


async def _perform_refresh(workspace_id: str, actor_id: str, refresh_token: str) -> dict[str, any]:
    """Perform Microsoft OAuth token refresh.

    This is called internally by OAuthTokenCache.get_tokens_with_auto_refresh().
    Application code should use get_tokens() instead.

    Args:
        workspace_id: Workspace identifier
        actor_id: User/actor identifier
        refresh_token: Refresh token to use

    Returns:
        New token dict with access_token, refresh_token (maybe), expires_at, scope

    Raises:
        MSRefreshError: If refresh fails
    """
    from relay_ai.auth.oauth.tokens import OAuthTokenCache
    from relay_ai.telemetry import oauth_events

    # Get Microsoft OAuth credentials
    client_id = os.getenv("MS_CLIENT_ID")
    tenant_id = os.getenv("MS_TENANT_ID", "common")

    if not client_id:
        raise ValueError("MS_CLIENT_ID not configured")

    # Call Microsoft token refresh endpoint
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_data = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": "https://graph.microsoft.com/Mail.Send offline_access",
    }

    # Add client_secret if configured (confidential client)
    client_secret = os.getenv("MS_CLIENT_SECRET")
    if client_secret:
        token_data["client_secret"] = client_secret

    oauth_events.labels(provider="microsoft", event="refresh_start").inc()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(token_url, data=token_data)

            if response.status_code != 200:
                oauth_events.labels(provider="microsoft", event="refresh_failed").inc()
                error_detail = response.json().get("error_description", response.text[:200])
                raise MSRefreshError(f"Token refresh failed: {response.status_code} {error_detail}")

            token_response = response.json()
    except httpx.TimeoutException as e:
        oauth_events.labels(provider="microsoft", event="refresh_timeout").inc()
        raise MSRefreshError("Token refresh timeout") from e

    # Extract new tokens
    new_access_token = token_response.get("access_token")
    new_refresh_token = token_response.get("refresh_token", refresh_token)  # Microsoft may not return new one
    expires_in = token_response.get("expires_in", 3600)
    scope = token_response.get("scope")

    if not new_access_token:
        oauth_events.labels(provider="microsoft", event="refresh_no_token").inc()
        raise MSRefreshError("No access token in refresh response")

    # Store updated tokens
    token_cache = OAuthTokenCache()
    await token_cache.store_tokens(
        provider="microsoft",
        workspace_id=workspace_id,
        actor_id=actor_id,
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        expires_in=expires_in,
        scope=scope,
    )

    oauth_events.labels(provider="microsoft", event="refresh_ok").inc()

    # Return new token dict
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "expires_at": expires_at,
        "scope": scope,
    }


async def revoke_tokens(workspace_id: str, actor_id: str) -> None:
    """Revoke Microsoft OAuth tokens (delete from cache and database).

    Args:
        workspace_id: Workspace identifier
        actor_id: User/actor identifier

    Example:
        await revoke_tokens("ws_123", "user_456")
    """
    from relay_ai.auth.oauth.tokens import OAuthTokenCache
    from relay_ai.telemetry import oauth_events

    token_cache = OAuthTokenCache()
    token_cache.delete_tokens(provider="microsoft", workspace_id=workspace_id, actor_id=actor_id)

    oauth_events.labels(provider="microsoft", event="revoke").inc()


def get_configured_scopes() -> list[str]:
    """Get list of Microsoft Graph scopes configured for this application.

    Returns:
        List of scope URLs

    Example:
        scopes = get_configured_scopes()
        # ["https://graph.microsoft.com/Mail.Send", "offline_access"]
    """
    return [
        "https://graph.microsoft.com/Mail.Send",  # Send mail as user
        "offline_access",  # Get refresh token
    ]


def is_configured() -> bool:
    """Check if Microsoft OAuth is properly configured.

    Returns:
        True if MS_CLIENT_ID is set, False otherwise
    """
    return bool(os.getenv("MS_CLIENT_ID"))
