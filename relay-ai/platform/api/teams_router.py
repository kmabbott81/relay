"""
Team Management Router (Stub)

Placeholder for team invite/member management endpoints.
TODO: Wire to team_members table with RLS.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class InviteRequest(BaseModel):
    email: str
    role: str = "member"


@router.post("/invite")
async def create_team_invite(invite: InviteRequest):
    """
    Create team invite link.

    TODO: Implement:
    1. Verify inviter is workspace owner
    2. Generate unique invite token
    3. Store in invites table (expires 7 days)
    4. Send email via SendGrid/Resend
    5. Return invite link
    """
    if not invite.email:
        raise HTTPException(status_code=400, detail="Email required")

    return {
        "message": "Invite created (stub)",
        "invite_link": f"https://relay.ai/join/{invite.email}",
        "TODO": "Generate unique token and send email",
        "status": "not_implemented",
    }


@router.post("/join")
async def join_team(token: str):
    """
    Accept team invite.

    TODO: Implement:
    1. Verify token is valid and not expired
    2. Add user to team_members table
    3. Set RLS context for user in workspace
    4. Return success
    """
    if not token:
        raise HTTPException(status_code=400, detail="Token required")

    return {
        "message": "Joined team (stub)",
        "TODO": "Verify token and add to team_members",
        "status": "not_implemented",
    }


@router.get("/members")
async def list_team_members():
    """
    List team members.

    TODO: Implement:
    1. Extract workspace from JWT
    2. Query team_members with RLS
    3. Return paginated list
    """
    return {
        "members": [
            {
                "id": "1",
                "email": "user@example.com",
                "role": "owner",
                "joined_at": "2025-11-01T00:00:00Z",
            }
        ],
        "total": 1,
        "message": "Stub data",
    }


@router.delete("/members/{member_id}")
async def remove_team_member(member_id: str):
    """
    Remove team member.

    TODO: Implement:
    1. Verify requester is workspace owner
    2. Remove from team_members table
    3. Revoke access to shared documents
    """
    return {
        "message": f"Member {member_id} removed (stub)",
        "TODO": "Implement member removal with RLS verification",
        "status": "not_implemented",
    }
