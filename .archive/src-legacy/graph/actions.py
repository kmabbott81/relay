"""Unified Resource Graph (URG) Action Router.

Routes cross-connector actions with RBAC enforcement and audit logging.
"""

import copy
import os
from typing import Callable, Optional

from ..security.audit import AuditAction, AuditLogger, AuditResult
from ..security.teams import get_team_role
from .index import get_index


class ActionError(Exception):
    """Action execution error."""

    pass


class RBACDenied(Exception):
    """RBAC permission denied."""

    pass


# Action registry: {resource_type: {action_name: handler_function}}
ACTION_REGISTRY: dict[str, dict[str, Callable]] = {}


def register_action(resource_type: str, action_name: str):
    """Decorator to register action handler.

    Args:
        resource_type: Type of resource (message, contact, event)
        action_name: Action name (reply, forward, delete, etc.)

    Returns:
        Decorator function
    """

    def decorator(func: Callable):
        if resource_type not in ACTION_REGISTRY:
            ACTION_REGISTRY[resource_type] = {}
        ACTION_REGISTRY[resource_type][action_name] = func
        return func

    return decorator


def execute_action(
    action: str,
    graph_id: str,
    payload: dict,
    *,
    user_id: str,
    tenant: str,
) -> dict:
    """Execute action on resource via appropriate connector.

    Args:
        action: Action to execute (e.g., "message.reply", "contact.email")
        graph_id: URG graph ID of resource
        payload: Action-specific payload
        user_id: User executing action
        tenant: Tenant ID

    Returns:
        Execution result dict with status and data

    Raises:
        ActionError: If action fails
        RBACDenied: If user lacks permission
        ValueError: If resource not found or action invalid
    """
    # Deep copy payload to prevent mutation
    payload = copy.deepcopy(payload)

    # Get audit logger
    audit_logger = AuditLogger(os.getenv("AUDIT_DIR", "audit"))

    # Parse action (format: "resource_type.action_name")
    if "." not in action:
        raise ValueError(f"Invalid action format: {action}. Expected 'type.action'")

    resource_type, action_name = action.split(".", 1)

    # Get resource from index
    index = get_index()
    resource = index.get(graph_id, tenant=tenant)

    if not resource:
        # Log failure
        audit_logger.log(
            tenant_id=tenant,
            user_id=user_id,
            action=AuditAction.RUN_WORKFLOW,
            resource_type=resource_type,
            resource_id=graph_id,
            result=AuditResult.FAILURE,
            reason=f"Resource not found: {graph_id}",
            metadata={"action": action},
        )

        raise ValueError(f"Resource not found: {graph_id}")

    # Verify resource type matches
    if resource.get("type") != resource_type:
        raise ValueError(f"Resource type mismatch: expected {resource_type}, got {resource.get('type')}")

    # Check RBAC - actions require Admin role
    user_role = get_team_role(user_id, tenant)
    if not user_role or user_role != "Admin":
        # Log denied
        audit_logger.log(
            tenant_id=tenant,
            user_id=user_id,
            action=AuditAction.RUN_WORKFLOW,
            resource_type=resource_type,
            resource_id=graph_id,
            result=AuditResult.DENIED,
            reason=f"User role '{user_role}' lacks permission for action: {action}",
            metadata={"action": action, "required_role": "Admin"},
        )

        raise RBACDenied(f"Admin role required for action: {action}")

    # Look up action handler
    if resource_type not in ACTION_REGISTRY:
        raise ValueError(f"No actions registered for resource type: {resource_type}")

    handlers = ACTION_REGISTRY[resource_type]
    if action_name not in handlers:
        available = ", ".join(handlers.keys())
        raise ValueError(f"Unknown action '{action_name}' for type '{resource_type}'. Available: {available}")

    handler = handlers[action_name]

    # Execute action
    try:
        result = handler(resource, payload, user_id=user_id, tenant=tenant)

        # Log success
        audit_logger.log(
            tenant_id=tenant,
            user_id=user_id,
            action=AuditAction.RUN_WORKFLOW,
            resource_type=resource_type,
            resource_id=graph_id,
            result=AuditResult.SUCCESS,
            metadata={"action": action, "payload": payload},
        )

        return {
            "status": "success",
            "action": action,
            "graph_id": graph_id,
            "result": result,
        }

    except Exception as e:
        # Log error
        audit_logger.log(
            tenant_id=tenant,
            user_id=user_id,
            action=AuditAction.RUN_WORKFLOW,
            resource_type=resource_type,
            resource_id=graph_id,
            result=AuditResult.ERROR,
            reason=str(e),
            metadata={"action": action, "payload": payload},
        )

        raise ActionError(f"Action failed: {e}") from e


# Built-in action handlers


@register_action("message", "reply")
def message_reply(resource: dict, payload: dict, *, user_id: str, tenant: str) -> dict:
    """Reply to a message.

    Args:
        resource: Message resource
        payload: Reply payload with 'body' field
        user_id: User executing action
        tenant: Tenant ID

    Returns:
        Reply result
    """
    source = resource.get("source")
    original_id = resource.get("metadata", {}).get("original_id")

    if not original_id:
        raise ActionError("Cannot reply: original_id not found in metadata")

    # Get connector
    connector = _get_connector(source, user_id, tenant)

    # Build reply payload based on source
    if source == "teams":
        # Teams reply in channel
        channel_id = resource.get("channel_id")

        reply_payload = {
            "body": {"contentType": "text", "content": payload.get("body", "")},
        }

        # Use create_resource to post reply
        result = connector.create_resource("messages", reply_payload)

    elif source == "outlook":
        # Outlook reply
        reply_payload = {
            "comment": payload.get("body", ""),
        }

        # Use update for reply (Outlook API pattern)
        result = connector.update_resource("messages", original_id, reply_payload)

    elif source == "slack":
        # Slack reply in thread
        channel_id = resource.get("channel_id")
        thread_ts = resource.get("thread_id") or original_id

        reply_payload = {
            "channel": channel_id,
            "text": payload.get("body", ""),
            "thread_ts": thread_ts,
        }

        result = connector.create_resource("messages", reply_payload)

    elif source == "gmail":
        # Gmail reply
        reply_payload = {
            "threadId": resource.get("thread_id"),
            "body": payload.get("body", ""),
        }

        result = connector.create_resource("messages", reply_payload)

    else:
        raise ActionError(f"Reply not supported for source: {source}")

    return {"status": "replied", "result": result}


@register_action("message", "forward")
def message_forward(resource: dict, payload: dict, *, user_id: str, tenant: str) -> dict:
    """Forward a message.

    Args:
        resource: Message resource
        payload: Forward payload with 'to' field
        user_id: User executing action
        tenant: Tenant ID

    Returns:
        Forward result
    """
    source = resource.get("source")
    original_id = resource.get("metadata", {}).get("original_id")

    if not original_id:
        raise ActionError("Cannot forward: original_id not found in metadata")

    to_recipients = payload.get("to", [])
    if not to_recipients:
        raise ActionError("Forward requires 'to' recipients")

    connector = _get_connector(source, user_id, tenant)

    # Forward based on source
    if source in ["outlook", "gmail"]:
        forward_payload = {
            "to": to_recipients,
            "comment": payload.get("comment", ""),
        }
        result = connector.update_resource("messages", original_id, forward_payload)

    else:
        raise ActionError(f"Forward not supported for source: {source}")

    return {"status": "forwarded", "result": result}


@register_action("message", "delete")
def message_delete(resource: dict, payload: dict, *, user_id: str, tenant: str) -> dict:
    """Delete a message.

    Args:
        resource: Message resource
        payload: Delete payload (unused)
        user_id: User executing action
        tenant: Tenant ID

    Returns:
        Delete result
    """
    source = resource.get("source")
    original_id = resource.get("metadata", {}).get("original_id")

    if not original_id:
        raise ActionError("Cannot delete: original_id not found in metadata")

    connector = _get_connector(source, user_id, tenant)

    # Delete message
    result = connector.delete_resource("messages", original_id)

    return {"status": "deleted", "result": result}


@register_action("contact", "email")
def contact_email(resource: dict, payload: dict, *, user_id: str, tenant: str) -> dict:
    """Send email to contact.

    Args:
        resource: Contact resource
        payload: Email payload with 'subject' and 'body'
        user_id: User executing action
        tenant: Tenant ID

    Returns:
        Send result
    """
    # Extract contact email
    contact_email = None
    participants = resource.get("participants", [])
    if participants:
        contact_email = participants[0] if isinstance(participants, list) else participants

    if not contact_email:
        raise ActionError("Contact has no email address")

    # Use Outlook or Gmail to send
    # Default to outlook for now
    connector = _get_connector("outlook", user_id, tenant)

    email_payload = {
        "message": {
            "subject": payload.get("subject", ""),
            "body": {"contentType": "text", "content": payload.get("body", "")},
            "toRecipients": [{"emailAddress": {"address": contact_email}}],
        }
    }

    result = connector.create_resource("messages", email_payload)

    return {"status": "sent", "result": result}


@register_action("event", "accept")
def event_accept(resource: dict, payload: dict, *, user_id: str, tenant: str) -> dict:
    """Accept calendar event.

    Args:
        resource: Event resource
        payload: Accept payload with optional 'comment'
        user_id: User executing action
        tenant: Tenant ID

    Returns:
        Accept result
    """
    source = resource.get("source")

    if source != "outlook":
        raise ActionError(f"Event accept only supported for Outlook, not {source}")

    original_id = resource.get("metadata", {}).get("original_id")
    if not original_id:
        raise ActionError("Cannot accept: original_id not found in metadata")

    connector = _get_connector(source, user_id, tenant)

    accept_payload = {
        "comment": payload.get("comment", ""),
        "sendResponse": True,
    }

    result = connector.update_resource("events", original_id, accept_payload)

    return {"status": "accepted", "result": result}


@register_action("event", "decline")
def event_decline(resource: dict, payload: dict, *, user_id: str, tenant: str) -> dict:
    """Decline calendar event.

    Args:
        resource: Event resource
        payload: Decline payload with optional 'comment'
        user_id: User executing action
        tenant: Tenant ID

    Returns:
        Decline result
    """
    source = resource.get("source")

    if source != "outlook":
        raise ActionError(f"Event decline only supported for Outlook, not {source}")

    original_id = resource.get("metadata", {}).get("original_id")
    if not original_id:
        raise ActionError("Cannot decline: original_id not found in metadata")

    connector = _get_connector(source, user_id, tenant)

    decline_payload = {
        "comment": payload.get("comment", ""),
        "sendResponse": True,
    }

    result = connector.update_resource("events", original_id, decline_payload)

    return {"status": "declined", "result": result}


def _get_connector(source: str, user_id: str, tenant: str):
    """Get connector instance for source.

    Args:
        source: Source connector name
        user_id: User ID
        tenant: Tenant ID

    Returns:
        Connector instance

    Raises:
        ActionError: If connector not available
    """
    from ..connectors.gmail import GmailConnector
    from ..connectors.outlook_api import OutlookConnector
    from ..connectors.slack import SlackConnector
    from ..connectors.teams import TeamsConnector

    connector_id = f"{source}-{tenant}"

    if source == "teams":
        return TeamsConnector(connector_id, tenant, user_id)
    elif source == "outlook":
        return OutlookConnector(connector_id, tenant, user_id)
    elif source == "slack":
        return SlackConnector(connector_id, tenant, user_id)
    elif source == "gmail":
        return GmailConnector(connector_id, tenant, user_id)
    else:
        raise ActionError(f"Unknown source connector: {source}")


def list_actions(resource_type: Optional[str] = None) -> dict[str, list[str]]:
    """List available actions.

    Args:
        resource_type: Optional filter by resource type

    Returns:
        Dict mapping resource types to action lists
    """
    if resource_type:
        if resource_type not in ACTION_REGISTRY:
            return {resource_type: []}
        return {resource_type: list(ACTION_REGISTRY[resource_type].keys())}

    # Return all
    return {rt: list(actions.keys()) for rt, actions in ACTION_REGISTRY.items()}
