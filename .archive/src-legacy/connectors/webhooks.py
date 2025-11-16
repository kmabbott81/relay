"""Webhook ingestion for connector events.

Normalizes events from various connector sources.
"""

import base64
import json
from datetime import datetime

from .metrics import record_call


def ingest_event(connector_type: str, payload: dict) -> dict:
    """Ingest and normalize webhook event.

    Args:
        connector_type: Source connector (teams, slack, etc.)
        payload: Raw webhook payload

    Returns:
        Normalized event structure
    """
    # Record ingestion metric
    record_call(f"{connector_type}-webhook", "ingest", "success", 5.0)

    if connector_type == "teams":
        return _normalize_teams_event(payload)
    elif connector_type == "slack":
        return _normalize_slack_event(payload)
    elif connector_type == "gmail":
        return _normalize_gmail_event(payload)
    elif connector_type == "notion":
        return _normalize_notion_event(payload)
    else:
        raise ValueError(f"Unknown connector type: {connector_type}")


def _normalize_teams_event(payload: dict) -> dict:
    """Normalize Microsoft Teams webhook event.

    Args:
        payload: Teams webhook payload

    Returns:
        Normalized event
    """
    # Teams webhook structure varies by subscription type
    # Common fields: changeType, resource, resourceData

    event_type = payload.get("changeType", "unknown")
    resource = payload.get("resource", "")

    # Determine resource type from URL pattern
    if "/teams/" in resource and "/channels/" in resource and "/messages/" in resource:
        resource_type = "message"
    elif "/teams/" in resource and "/channels/" in resource:
        resource_type = "channel"
    elif "/teams/" in resource:
        resource_type = "team"
    else:
        resource_type = "unknown"

    # Extract resource data
    resource_data = payload.get("resourceData", {})

    return {
        "connector_type": "teams",
        "event_type": event_type,
        "resource_type": resource_type,
        "resource_id": resource_data.get("id", ""),
        "timestamp": payload.get("subscriptionExpirationDateTime", datetime.now().isoformat()),
        "data": resource_data,
        "raw_payload": payload,
    }


def _normalize_slack_event(payload: dict) -> dict:
    """Normalize Slack Events API event.

    Args:
        payload: Slack Events API payload

    Returns:
        Normalized event

    Note:
        Slack Events API structure:
        {
            "type": "event_callback",
            "event": {
                "type": "message.channels",
                "channel": "C123456",
                "user": "U123456",
                "text": "Hello",
                "ts": "1234567890.123456"
            }
        }

        Optional signature verification via SLACK_SIGNING_SECRET:
        - Check X-Slack-Signature header
        - Compare HMAC SHA256 of request body
        - Verify timestamp within 5 minutes
        - Not enforced by default (documented only)
    """
    # Extract event data
    event_type = payload.get("type", "unknown")

    # Handle URL verification challenge
    if event_type == "url_verification":
        return {
            "connector_type": "slack",
            "event_type": "url_verification",
            "resource_type": "challenge",
            "resource_id": "",
            "timestamp": datetime.now().isoformat(),
            "data": {"challenge": payload.get("challenge", "")},
            "raw_payload": payload,
        }

    # Handle event callbacks
    if event_type == "event_callback":
        event = payload.get("event", {})
        event_subtype = event.get("type", "unknown")

        # Determine resource type from event type
        if "message" in event_subtype:
            resource_type = "message"
            resource_id = event.get("ts", "")
        elif "channel" in event_subtype:
            resource_type = "channel"
            resource_id = event.get("channel", "")
        elif "user" in event_subtype:
            resource_type = "user"
            resource_id = event.get("user", "")
        else:
            resource_type = "unknown"
            resource_id = ""

        return {
            "connector_type": "slack",
            "event_type": event_subtype,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "timestamp": event.get("event_ts", datetime.now().isoformat()),
            "data": event,
            "raw_payload": payload,
        }

    # Default for unknown event types
    return {
        "connector_type": "slack",
        "event_type": event_type,
        "resource_type": "unknown",
        "resource_id": "",
        "timestamp": datetime.now().isoformat(),
        "data": payload,
        "raw_payload": payload,
    }


def _normalize_gmail_event(payload: dict) -> dict:
    """Normalize Gmail Pub/Sub push notification event.

    Args:
        payload: Gmail Pub/Sub push notification payload

    Returns:
        Normalized event

    Note:
        Gmail push notification structure (Cloud Pub/Sub):
        {
            "message": {
                "data": "<base64-encoded JSON>",
                "messageId": "2070443601311540",
                "publishTime": "2021-02-26T19:13:55.749Z"
            },
            "subscription": "projects/myproject/subscriptions/mysubscription"
        }

        The data field contains base64-encoded JSON with:
        {
            "emailAddress": "user@example.com",
            "historyId": "123456"
        }

        To receive push notifications, you must:
        1. Create a Pub/Sub topic in Google Cloud Console
        2. Grant publish rights to gmail-api-push@system.gserviceaccount.com
        3. Call Gmail API watch() to start receiving notifications
        4. Set up webhook endpoint to receive POST requests
    """
    # Extract message data
    message = payload.get("message", {})
    message_id = message.get("messageId", "")
    publish_time = message.get("publishTime", datetime.now().isoformat())

    # Decode base64 data if present
    decoded_data = {}
    if "data" in message:
        try:
            data_bytes = base64.b64decode(message["data"])
            decoded_data = json.loads(data_bytes.decode("utf-8"))
        except (ValueError, KeyError):
            # If decoding fails, use empty dict
            decoded_data = {}

    # Extract history ID if present
    history_id = decoded_data.get("historyId", "")
    email_address = decoded_data.get("emailAddress", "")

    return {
        "connector_type": "gmail",
        "event_type": "message_received",
        "resource_type": "message",
        "resource_id": message_id,
        "timestamp": publish_time,
        "data": {
            "historyId": history_id,
            "emailAddress": email_address,
            "messageId": message_id,
            "subscription": payload.get("subscription", ""),
        },
        "raw_payload": payload,
    }


def _normalize_notion_event(payload: dict) -> dict:
    """Normalize Notion webhook event.

    Args:
        payload: Notion webhook payload

    Returns:
        Normalized event

    Note:
        Notion webhook structure:
        {
            "type": "page.updated",
            "page": {
                "object": "page",
                "id": "page-123",
                "created_time": "...",
                "last_edited_time": "...",
                "properties": {...}
            },
            "timestamp": "2023-01-02T15:30:00.000Z"
        }

        Or for database events:
        {
            "type": "database.updated",
            "database": {
                "object": "database",
                "id": "database-123",
                ...
            },
            "timestamp": "..."
        }
    """
    # Extract event type
    event_type = payload.get("type", "unknown")

    # Determine resource type and extract resource data
    resource_type = "unknown"
    resource_id = ""
    resource_data = {}

    if "page" in payload:
        resource_type = "page"
        resource_data = payload.get("page", {})
        resource_id = resource_data.get("id", "")
    elif "database" in payload:
        resource_type = "database"
        resource_data = payload.get("database", {})
        resource_id = resource_data.get("id", "")
    elif "block" in payload:
        resource_type = "block"
        resource_data = payload.get("block", {})
        resource_id = resource_data.get("id", "")
    else:
        # Try to extract from event_type (e.g., "page.updated" -> "page")
        if "." in event_type:
            resource_type = event_type.split(".")[0]

        # Try to find resource_id in payload data
        if "data" in payload:
            resource_data = payload.get("data", {})
            resource_id = resource_data.get("id", "")

    # Get timestamp
    timestamp = payload.get("timestamp", datetime.now().isoformat())

    return {
        "connector_type": "notion",
        "event_type": event_type,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "timestamp": timestamp,
        "data": resource_data,
        "raw_payload": payload,
    }
