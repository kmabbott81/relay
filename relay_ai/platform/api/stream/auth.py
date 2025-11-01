"""Stream authentication (Supabase JWT + anonymous sessions).

Sprint 61b R0.5 Security Hotfix: Server-side auth for /api/v1/stream endpoint.
"""

import os
import time
from typing import Any, Optional
from uuid import uuid4

from fastapi import Header, HTTPException, Request, status
from jwt import DecodeError, decode, encode
from pydantic import BaseModel

# =============================================================================
# PRINCIPAL MODEL (authenticated user/session context)
# =============================================================================


class StreamPrincipal(BaseModel):
    """Authenticated principal (user or anonymous session)."""

    user_id: str  # Either Supabase user ID or anon_<uuid>
    is_anonymous: bool  # True if anonymous session
    session_id: str  # Session UUID for tracking
    created_at: float  # Token creation timestamp (Unix)
    expires_at: float  # Token expiration timestamp (Unix)

    class Config:
        frozen = True  # Immutable for security


# =============================================================================
# SUPABASE JWT VERIFICATION
# =============================================================================

SUPABASE_PROJECT_ID = os.getenv("SUPABASE_PROJECT_ID", "relay")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL", "")

# Cache for JWKS (public keys)
_jwks_cache = {"keys": [], "expires_at": 0}


async def _load_supabase_jwks() -> dict[str, Any]:
    """Load and cache Supabase JWKS (public keys)."""
    import aiohttp

    now = time.time()
    if _jwks_cache["expires_at"] > now and _jwks_cache["keys"]:
        return {"keys": _jwks_cache["keys"]}

    if not SUPABASE_JWKS_URL:
        # Fallback: use JWT_SECRET directly (symmetric key)
        return None

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(SUPABASE_JWKS_URL, timeout=5) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"JWKS fetch failed: {resp.status}")
                jwks = await resp.json()
                _jwks_cache["keys"] = jwks.get("keys", [])
                _jwks_cache["expires_at"] = now + 3600  # Cache for 1 hour
                return jwks
    except Exception:
        # If fetch fails, use cached keys or fallback
        if _jwks_cache["keys"]:
            return {"keys": _jwks_cache["keys"]}
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service temporarily unavailable",
        )


async def verify_supabase_jwt(token: str) -> StreamPrincipal:
    """Verify Supabase JWT and extract principal.

    Args:
        token: JWT token from Authorization header

    Returns:
        StreamPrincipal with user_id and session context

    Raises:
        HTTPException: 401 if invalid/expired token
    """
    try:
        # Use same secret as token generation (with fallback)
        secret = SUPABASE_JWT_SECRET or os.getenv("SECRET_KEY", "dev-secret-key")

        try:
            claims = decode(
                token,
                secret,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
        except DecodeError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )

        # Extract user_id from token
        user_id = str(claims.get("sub") or claims.get("user_id") or "")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user_id",
            )

        session_id = str(uuid4())
        now = time.time()
        return StreamPrincipal(
            user_id=user_id,
            is_anonymous=bool(claims.get("anon", False)),
            session_id=session_id,
            created_at=now,
            expires_at=now + 86400,  # 24h expiry
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
        )


# =============================================================================
# ANONYMOUS SESSION TOKEN GENERATION (Mint short-lived JWT)
# =============================================================================


def generate_anon_session_token(ttl_seconds: int = 604800) -> tuple[str, float]:
    """Generate signed anonymous session token (short-lived JWT).

    Args:
        ttl_seconds: Time-to-live in seconds (default 7 days)

    Returns:
        Tuple of (token_jwt, expires_at_unix)
    """
    now = time.time()
    expires_at = now + ttl_seconds

    session_id = str(uuid4())
    user_id = f"anon_{session_id}"

    payload = {
        "sub": user_id,
        "user_id": user_id,
        "anon": True,
        "sid": session_id,
        "iat": int(now),
        "exp": int(expires_at),
    }

    # Sign with JWT secret (symmetric)
    secret = SUPABASE_JWT_SECRET or os.getenv("SECRET_KEY", "dev-secret-key")
    token = encode(payload, secret, algorithm="HS256")

    return token, expires_at


# =============================================================================
# DEPENDENCY INJECTION (FastAPI Depends)
# =============================================================================


async def get_stream_principal(
    request: Request, auth: Optional[str] = Header(None, alias="Authorization")
) -> StreamPrincipal:
    """FastAPI dependency to extract and validate principal from Authorization header.

    Usage:
        @app.get("/api/v1/stream")
        async def stream(principal: StreamPrincipal = Depends(get_stream_principal)):
            ...

    Raises:
        HTTPException: 401 if missing/invalid token
    """
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    token = auth.split(" ", 1)[1]
    return await verify_supabase_jwt(token)
