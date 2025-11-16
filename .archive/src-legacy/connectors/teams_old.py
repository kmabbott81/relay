"""Microsoft Teams connector for posting notifications."""

import json
import os
from typing import Optional
from urllib import request
from urllib.error import URLError


def post_message(
    title: str,
    text: str,
    webhook_url: Optional[str] = None,
    theme_color: str = "0078D4",
) -> bool:
    """
    Post message to Microsoft Teams via webhook.

    Args:
        title: Message title
        text: Message text (supports markdown)
        webhook_url: Teams webhook URL (defaults to TEAMS_WEBHOOK_URL env var)
        theme_color: Message theme color (hex)

    Returns:
        Success status

    Environment Variables:
        TEAMS_WEBHOOK_URL: Incoming webhook URL from Teams

    Example:
        >>> post_message(
        ...     title="Approval Required",
        ...     text="A new template output requires your approval."
        ... )
    """
    webhook_url = webhook_url or os.getenv("TEAMS_WEBHOOK_URL")

    if not webhook_url:
        print("Warning: TEAMS_WEBHOOK_URL not configured. Skipping Teams post.")
        return False

    # Teams message card format
    payload = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": title,
        "themeColor": theme_color,
        "title": title,
        "text": text,
    }

    try:
        req = request.Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        with request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                print("Teams message posted successfully")
                return True
            else:
                print(f"Teams post failed: {response.status}")
                return False

    except URLError as e:
        print(f"Failed to post to Teams: {e}")
        return False


def post_approval_notification(
    template_name: str,
    preview_text: str,
    artifact_id: str,
    approval_url: Optional[str] = None,
    webhook_url: Optional[str] = None,
    webhook_callback_url: Optional[str] = None,
    interactive: bool = True,
) -> bool:
    """
    Post approval notification to Teams with interactive buttons.

    Args:
        template_name: Name of template
        preview_text: Preview of output
        artifact_id: Artifact identifier
        approval_url: Optional URL to approval UI
        webhook_url: Teams webhook URL (defaults to TEAMS_WEBHOOK_URL env var)
        webhook_callback_url: Callback URL for button actions (defaults to WEBHOOK_BASE_URL/webhooks/teams)
        interactive: If True, include Approve/Reject buttons

    Returns:
        Success status
    """
    webhook_url = webhook_url or os.getenv("TEAMS_WEBHOOK_URL")

    if not webhook_url:
        print("Warning: TEAMS_WEBHOOK_URL not configured. Skipping Teams post.")
        return False

    # Get callback URL for interactive actions
    if not webhook_callback_url:
        webhook_base = os.getenv("WEBHOOK_BASE_URL", "http://localhost:8100")
        webhook_callback_url = f"{webhook_base}/webhooks/teams"

    # Build Adaptive Card with action buttons
    card = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": "⚠️ Approval Required",
                            "weight": "Bolder",
                            "size": "Large",
                            "color": "Warning",
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Template:", "value": template_name},
                                {"title": "Artifact ID:", "value": artifact_id},
                            ],
                        },
                        {
                            "type": "TextBlock",
                            "text": "Preview:",
                            "weight": "Bolder",
                        },
                        {
                            "type": "TextBlock",
                            "text": preview_text[:300] + "...",
                            "wrap": True,
                            "fontType": "Monospace",
                        },
                    ],
                },
            }
        ],
    }

    # Add interactive actions
    if interactive:
        card["attachments"][0]["content"]["actions"] = [
            {
                "type": "Action.Http",
                "title": "✅ Approve",
                "method": "POST",
                "url": webhook_callback_url,
                "body": json.dumps({"action": "approve", "artifact_id": artifact_id}),
                "headers": [{"name": "Content-Type", "value": "application/json"}],
            },
            {
                "type": "Action.Http",
                "title": "❌ Reject",
                "method": "POST",
                "url": webhook_callback_url,
                "body": json.dumps({"action": "reject", "artifact_id": artifact_id}),
                "headers": [{"name": "Content-Type", "value": "application/json"}],
            },
        ]

        # Add approval URL as fallback
        if approval_url:
            card["attachments"][0]["content"]["actions"].append(
                {
                    "type": "Action.OpenUrl",
                    "title": "Open in Browser",
                    "url": approval_url,
                }
            )

    try:
        req = request.Request(
            webhook_url,
            data=json.dumps(card).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        with request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                print("Teams approval notification posted successfully")
                return True
            else:
                print(f"Teams post failed: {response.status}")
                return False

    except URLError as e:
        print(f"Failed to post to Teams: {e}")
        return False
