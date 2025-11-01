"""
OAuth Router (Stub)

Placeholder for Google OAuth endpoints.
TODO: Implement full OAuth flow with Supabase JWT generation.
"""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/google")
async def google_oauth_callback(code: str = None):
    """
    Google OAuth callback handler.

    TODO: Implement:
    1. Exchange code for Google access token
    2. Fetch user info from Google
    3. Create/update user in database
    4. Generate Supabase JWT
    5. Return JWT to client
    """
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    return {
        "message": "OAuth callback (stub)",
        "TODO": "Implement Google OAuth flow",
        "status": "not_implemented",
    }


@router.post("/logout")
async def logout():
    """Logout handler (stub)."""
    return {"message": "Logged out successfully"}


@router.get("/profile")
async def get_profile():
    """
    Get current user profile.

    TODO: Extract user from JWT, fetch from database.
    """
    return {
        "message": "Profile endpoint (stub)",
        "TODO": "Extract user from JWT",
        "status": "not_implemented",
    }
