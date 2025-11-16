"""Webhook handlers for interactive approvals from Slack and Teams."""

import hashlib
import hmac
import json
import os
import time
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

app = FastAPI(title="DJP Webhooks", version="1.0.0")


class ApprovalPayload(BaseModel):
    """Approval action payload."""

    artifact_id: str
    action: str  # "approve" or "reject"
    reason: Optional[str] = None
    user: Optional[str] = None
    channel: Optional[str] = None


class ApprovalResponse(BaseModel):
    """Response from approval action."""

    success: bool
    artifact_id: str
    new_status: str
    message: str
    error: Optional[str] = None


def verify_slack_signature_headers(headers: dict, body: bytes, secret: str) -> bool:
    """
    Verify Slack request signature using HMAC SHA256.

    Per Slack docs: https://api.slack.com/authentication/verifying-requests-from-slack

    Args:
        headers: Request headers dict
        body: Raw request body bytes
        secret: Slack signing secret

    Returns:
        True if signature is valid, False otherwise
    """
    if not secret:
        print("Warning: SLACK_SIGNING_SECRET not provided. Verification disabled.")
        return True  # Verification disabled

    timestamp = headers.get("X-Slack-Request-Timestamp", "")
    signature = headers.get("X-Slack-Signature", "")

    if not timestamp or not signature:
        print("Warning: Missing timestamp or signature headers")
        return False

    # Prevent replay attacks (5 minute window)
    try:
        timestamp_int = int(timestamp)
    except ValueError:
        print("Warning: Invalid timestamp format")
        return False

    if abs(time.time() - timestamp_int) > 60 * 5:
        print("Warning: Request timestamp too old (replay attack prevention)")
        return False

    # Compute expected signature: HMAC-SHA256 of "v0:timestamp:body"
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    expected_signature = "v0=" + hmac.new(secret.encode(), sig_basestring.encode(), hashlib.sha256).hexdigest()

    # Constant-time comparison
    return hmac.compare_digest(expected_signature, signature)


def verify_slack_signature(request: Request, body: bytes) -> bool:
    """
    Verify Slack request signature (FastAPI wrapper).

    Args:
        request: FastAPI request object
        body: Raw request body

    Returns:
        True if signature is valid, False otherwise
    """
    slack_signing_secret = os.getenv("SLACK_SIGNING_SECRET", "")

    if not slack_signing_secret:
        print("Warning: SLACK_SIGNING_SECRET not set. Running in dev mode (signature verification disabled).")
        return True  # Dev mode

    # Convert request headers to dict
    headers_dict = dict(request.headers)

    return verify_slack_signature_headers(headers_dict, body, slack_signing_secret)


def verify_teams_token(request: Request) -> bool:
    """
    Verify Teams webhook token.

    Args:
        request: FastAPI request object

    Returns:
        True if token is valid, False otherwise
    """
    teams_token = os.getenv("TEAMS_WEBHOOK_TOKEN")

    if not teams_token:
        print("Warning: TEAMS_WEBHOOK_TOKEN not set. Running in dev mode (token verification disabled).")
        return True  # Dev mode

    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        return False

    token = auth_header[7:]  # Remove "Bearer " prefix
    return hmac.compare_digest(token, teams_token)


def update_artifact_status(artifact_id: str, action: str, reason: Optional[str] = None) -> tuple[bool, str, str]:
    """
    Update artifact status based on approval action.

    Args:
        artifact_id: Artifact identifier
        action: "approve" or "reject"
        reason: Optional rejection reason

    Returns:
        Tuple of (success, new_status, message)
    """
    from pathlib import Path

    # Find artifact file
    artifact_path = None
    for search_dir in ["runs", "runs/api/triage", "runs/ui"]:
        search_path = Path(search_dir)
        if not search_path.exists():
            continue

        for artifact_file in search_path.rglob(f"*{artifact_id}*.json"):
            artifact_path = artifact_file
            break

        if artifact_path:
            break

    if not artifact_path or not artifact_path.exists():
        return False, "", f"Artifact {artifact_id} not found"

    # Load artifact
    try:
        artifact_data = json.loads(artifact_path.read_text(encoding="utf-8"))
    except Exception as e:
        return False, "", f"Failed to load artifact: {str(e)}"

    # Update status using publish.py functions
    try:
        from .publish import approve_pending_result, reject_pending_result

        current_status = artifact_data.get("result", {}).get("status", "unknown")
        provider = artifact_data.get("result", {}).get("provider", "")
        text = artifact_data.get("result", {}).get("text", "")

        if action == "approve":
            new_status, new_provider, new_text, new_reason = approve_pending_result(
                pending_status=current_status, pending_provider=provider, pending_text=text, allowed=[]
            )
        elif action == "reject":
            new_status, new_provider, new_text, new_reason = reject_pending_result(
                pending_status=current_status,
                pending_provider=provider,
                pending_text=text,
                rejection_reason=reason or "Rejected via interactive approval",
            )
        else:
            return False, "", f"Invalid action: {action}"

        # Update artifact with new status
        if "result" not in artifact_data:
            artifact_data["result"] = {}

        artifact_data["result"]["status"] = new_status
        artifact_data["result"]["provider"] = new_provider
        artifact_data["result"]["text"] = new_text
        artifact_data["result"]["reason"] = new_reason

        # Add approval metadata
        if "approval_history" not in artifact_data:
            artifact_data["approval_history"] = []

        artifact_data["approval_history"].append(
            {"action": action, "timestamp": time.time(), "reason": reason, "new_status": new_status}
        )

        # Save updated artifact
        artifact_path.write_text(json.dumps(artifact_data, indent=2), encoding="utf-8")

        return True, new_status, f"Artifact {artifact_id} updated to {new_status}"

    except Exception as e:
        return False, "", f"Failed to update artifact: {str(e)}"


@app.get("/")
def root():
    """Webhook root endpoint."""
    return {
        "name": "DJP Webhooks",
        "version": "1.0.0",
        "endpoints": {
            "approval": "/webhooks/approval",
            "slack": "/webhooks/slack",
            "teams": "/webhooks/teams",
        },
    }


@app.post("/webhooks/approval", response_model=ApprovalResponse)
async def handle_approval(payload: ApprovalPayload):
    """
    Handle approval action from Slack or Teams.

    Args:
        payload: Approval action details

    Returns:
        Response with new status
    """
    if payload.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail=f"Invalid action: {payload.action}")

    success, new_status, message = update_artifact_status(payload.artifact_id, payload.action, payload.reason)

    if not success:
        return ApprovalResponse(
            success=False, artifact_id=payload.artifact_id, new_status="", message="", error=message
        )

    return ApprovalResponse(success=True, artifact_id=payload.artifact_id, new_status=new_status, message=message)


@app.post("/webhooks/slack")
async def handle_slack_interactive(request: Request):
    """
    Handle Slack interactive message callback.

    Slack sends form-encoded payload with button actions.
    """
    # Read raw body for signature verification
    body = await request.body()

    if not verify_slack_signature(request, body):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    # Parse form data
    form_data = await request.form()
    payload_str = form_data.get("payload", "")

    if not payload_str:
        raise HTTPException(status_code=400, detail="Missing payload")

    payload = json.loads(payload_str)

    # Extract action details
    actions = payload.get("actions", [])
    if not actions:
        raise HTTPException(status_code=400, detail="No actions in payload")

    action = actions[0]
    action_id = action.get("action_id", "")
    artifact_id = action.get("value", "")

    # Determine approve or reject
    if "approve" in action_id.lower():
        action_type = "approve"
    elif "reject" in action_id.lower():
        action_type = "reject"
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action_id}")

    # Update artifact
    success, new_status, message = update_artifact_status(artifact_id, action_type)

    if not success:
        return {"text": f"❌ {message}"}

    # Post follow-up message to Slack
    user = payload.get("user", {}).get("name", "unknown")
    response_text = f"✅ {user} {action_type}d artifact `{artifact_id}`. New status: *{new_status}*"

    return {"text": response_text, "replace_original": False}


@app.post("/webhooks/teams")
async def handle_teams_actionable(request: Request):
    """
    Handle Teams actionable message callback.

    Teams sends JSON payload with action details.
    """
    if not verify_teams_token(request):
        raise HTTPException(status_code=401, detail="Invalid Teams token")

    payload = await request.json()

    # Extract action details
    action_type = payload.get("action", "").lower()
    artifact_id = payload.get("artifact_id", "")
    reason = payload.get("reason", None)

    if not artifact_id:
        raise HTTPException(status_code=400, detail="Missing artifact_id")

    if action_type not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail=f"Invalid action: {action_type}")

    # Update artifact
    success, new_status, message = update_artifact_status(artifact_id, action_type, reason)

    if not success:
        return {"type": "message", "text": f"❌ {message}"}

    # Return confirmation message
    user = payload.get("user", {}).get("displayName", "User")
    return {
        "type": "message",
        "text": f"✅ {user} {action_type}d artifact {artifact_id}. New status: {new_status}",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8100)
