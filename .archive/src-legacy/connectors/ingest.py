"""Connector snapshot ingestion into URG.

Fetches resources from connectors, normalizes via CP-CAL, and indexes in URG.
"""


from ..graph.index import get_index
from .cp_cal import SchemaAdapter
from .gmail import GmailConnector
from .notion import NotionConnector
from .outlook_api import OutlookConnector
from .slack import SlackConnector
from .teams import TeamsConnector


def ingest_connector_snapshot(
    connector_id: str,
    resource_type: str,
    *,
    tenant: str,
    user_id: str = "system",
    limit: int = 100,
) -> dict:
    """Ingest snapshot of resources from connector into URG.

    Args:
        connector_id: Connector identifier (teams, outlook, slack, gmail)
        resource_type: Type of resource to ingest (messages, contacts, events, etc.)
        tenant: Tenant ID for isolation
        user_id: User ID for RBAC (default: system)
        limit: Maximum resources to ingest

    Returns:
        Dict with ingestion stats:
            - count: Number of resources ingested
            - errors: Number of errors
            - source: Connector source
            - resource_type: Resource type

    Raises:
        ValueError: If connector or resource type invalid
    """
    # Normalize connector_id to source name
    source = connector_id.lower().replace("-", "").replace("_", "")

    # Map common aliases
    source_map = {
        "teams": "teams",
        "outlook": "outlook",
        "slack": "slack",
        "gmail": "gmail",
        "notion": "notion",
        "microsoftteams": "teams",
        "microsoftoutlook": "outlook",
    }

    source = source_map.get(source, source)

    # Get connector instance
    connector = _get_connector(source, tenant, user_id)

    if not connector:
        raise ValueError(f"Unknown connector: {connector_id}")

    # Connect to connector
    connect_result = connector.connect()
    if connect_result.status != "success":
        raise ValueError(f"Failed to connect to {source}: {connect_result.message}")

    # List resources
    list_result = connector.list_resources(resource_type, filters={"limit": limit})

    if list_result.status != "success":
        raise ValueError(f"Failed to list {resource_type} from {source}: {list_result.message}")

    resources = list_result.data or []

    # Get URG index
    index = get_index()

    # Normalize and ingest each resource
    ingested_count = 0
    error_count = 0

    for resource in resources:
        try:
            # Normalize via CP-CAL
            normalized = _normalize_resource(source, resource_type, resource)

            # Upsert to URG
            index.upsert(normalized, source=source, tenant=tenant)

            ingested_count += 1

        except Exception as e:
            print(f"Warning: Failed to ingest resource: {e}")
            error_count += 1

    # Disconnect
    connector.disconnect()

    return {
        "count": ingested_count,
        "errors": error_count,
        "source": source,
        "resource_type": resource_type,
        "tenant": tenant,
    }


def _get_connector(source: str, tenant: str, user_id: str):
    """Get connector instance.

    Args:
        source: Source connector (teams, outlook, slack, gmail)
        tenant: Tenant ID
        user_id: User ID

    Returns:
        Connector instance or None
    """
    connector_id = f"{source}-{tenant}"

    if source == "teams":
        return TeamsConnector(connector_id, tenant, user_id)
    elif source == "outlook":
        return OutlookConnector(connector_id, tenant, user_id)
    elif source == "slack":
        return SlackConnector(connector_id, tenant, user_id)
    elif source == "gmail":
        return GmailConnector(connector_id, tenant, user_id)
    elif source == "notion":
        return NotionConnector(connector_id, tenant, user_id)
    else:
        return None


def _normalize_resource(source: str, resource_type: str, resource: dict) -> dict:
    """Normalize resource via CP-CAL.

    Args:
        source: Source connector
        resource_type: Resource type
        resource: Raw resource data

    Returns:
        Normalized resource with URG schema fields
    """
    adapter = SchemaAdapter()

    # Normalize based on resource type
    if resource_type == "messages":
        normalized = adapter.normalize_message(source, resource)

        # Map to URG schema
        return {
            "id": normalized["id"],
            "type": "message",
            "title": normalized.get("subject", ""),
            "snippet": _truncate(normalized.get("body", ""), 200),
            "timestamp": normalized.get("timestamp", ""),
            "participants": [normalized.get("from", "")],
            "thread_id": normalized.get("metadata", {}).get("thread_ts")
            or normalized.get("metadata", {}).get("threadId")
            or "",
            "channel_id": normalized.get("metadata", {}).get("channel") or "",
            "labels": [],
            "metadata": normalized.get("metadata", {}),
        }

    elif resource_type == "pages":
        # Notion pages - normalize as documents
        normalized = adapter.normalize_message(source, resource)

        # Map to URG schema (pages → documents)
        return {
            "id": normalized["id"],
            "type": "document",
            "title": normalized.get("subject", ""),
            "snippet": _truncate(normalized.get("body", ""), 200),
            "timestamp": normalized.get("timestamp", ""),
            "participants": [normalized.get("from", "")],
            "thread_id": "",
            "channel_id": "",
            "labels": ["notion", "page"],
            "metadata": normalized.get("metadata", {}),
        }

    elif resource_type == "databases":
        # Notion databases - normalize as collections
        return {
            "id": resource.get("id", ""),
            "type": "collection",
            "title": resource.get("title", [{}])[0].get("plain_text", "") if resource.get("title") else "",
            "snippet": "Notion database",
            "timestamp": resource.get("last_edited_time", ""),
            "participants": [],
            "thread_id": "",
            "channel_id": "",
            "labels": ["notion", "database"],
            "metadata": {
                "created_time": resource.get("created_time", ""),
                "archived": resource.get("archived", False),
            },
        }

    elif resource_type == "blocks":
        # Notion blocks - normalize as content fragments
        return {
            "id": resource.get("id", ""),
            "type": "content",
            "title": f"Block: {resource.get('type', 'unknown')}",
            "snippet": "",
            "timestamp": resource.get("last_edited_time", ""),
            "participants": [],
            "thread_id": "",
            "channel_id": "",
            "labels": ["notion", "block"],
            "metadata": {
                "block_type": resource.get("type", ""),
                "has_children": resource.get("has_children", False),
            },
        }

    elif resource_type == "contacts":
        normalized = adapter.normalize_contact(source, resource)

        # Map to URG schema
        return {
            "id": normalized["id"],
            "type": "contact",
            "title": normalized.get("name", ""),
            "snippet": f"{normalized.get('email', '')} - {normalized.get('phone', '')}",
            "timestamp": "",
            "participants": [normalized.get("email", "")],
            "thread_id": "",
            "channel_id": "",
            "labels": [],
            "metadata": normalized.get("metadata", {}),
        }

    elif resource_type == "events":
        normalized = adapter.normalize_event(source, resource)

        # Map to URG schema
        return {
            "id": normalized["id"],
            "type": "event",
            "title": normalized.get("title", ""),
            "snippet": f"{normalized.get('start', '')} - {normalized.get('location', '')}",
            "timestamp": normalized.get("start", ""),
            "participants": [],
            "thread_id": "",
            "channel_id": "",
            "labels": [],
            "metadata": normalized.get("metadata", {}),
        }

    elif resource_type == "channels":
        # Generic channel normalization
        return {
            "id": resource.get("id", ""),
            "type": "channel",
            "title": resource.get("displayName") or resource.get("name", ""),
            "snippet": resource.get("description", ""),
            "timestamp": resource.get("createdDateTime", ""),
            "participants": [],
            "thread_id": "",
            "channel_id": resource.get("id", ""),
            "labels": [],
            "metadata": {"source_data": resource},
        }

    elif resource_type == "users":
        # Generic user normalization (for Slack)
        profile = resource.get("profile", {})
        return {
            "id": resource.get("id", ""),
            "type": "contact",
            "title": resource.get("real_name") or resource.get("name", ""),
            "snippet": profile.get("email", ""),
            "timestamp": "",
            "participants": [profile.get("email", "")],
            "thread_id": "",
            "channel_id": "",
            "labels": [],
            "metadata": {"source_data": resource},
        }

    else:
        # Generic fallback
        return {
            "id": resource.get("id", ""),
            "type": resource_type.rstrip("s"),  # Singular form
            "title": resource.get("displayName") or resource.get("name") or resource.get("subject", ""),
            "snippet": resource.get("description") or resource.get("body", "")[:200],
            "timestamp": resource.get("createdDateTime") or resource.get("timestamp") or "",
            "participants": [],
            "thread_id": "",
            "channel_id": "",
            "labels": [],
            "metadata": {"source_data": resource},
        }


def _truncate(text: str, max_length: int) -> str:
    """Truncate text to max length.

    Args:
        text: Text to truncate
        max_length: Maximum length

    Returns:
        Truncated text
    """
    if not text:
        return ""

    if len(text) <= max_length:
        return text

    return text[:max_length] + "..."


def ingest_all_connectors(
    *,
    tenant: str,
    user_id: str = "system",
    limit: int = 50,
) -> dict[str, dict]:
    """Ingest from all available connectors.

    Args:
        tenant: Tenant ID
        user_id: User ID
        limit: Resources per connector

    Returns:
        Dict mapping connector to ingestion results
    """
    results = {}

    # Teams: messages and channels
    for resource_type in ["messages", "channels"]:
        try:
            result = ingest_connector_snapshot(
                "teams",
                resource_type,
                tenant=tenant,
                user_id=user_id,
                limit=limit,
            )
            results[f"teams-{resource_type}"] = result
        except Exception as e:
            results[f"teams-{resource_type}"] = {
                "count": 0,
                "errors": 1,
                "error": str(e),
            }

    # Outlook: messages and contacts
    for resource_type in ["messages", "contacts"]:
        try:
            result = ingest_connector_snapshot(
                "outlook",
                resource_type,
                tenant=tenant,
                user_id=user_id,
                limit=limit,
            )
            results[f"outlook-{resource_type}"] = result
        except Exception as e:
            results[f"outlook-{resource_type}"] = {
                "count": 0,
                "errors": 1,
                "error": str(e),
            }

    # Slack: messages, channels, users
    for resource_type in ["messages", "channels", "users"]:
        try:
            result = ingest_connector_snapshot(
                "slack",
                resource_type,
                tenant=tenant,
                user_id=user_id,
                limit=limit,
            )
            results[f"slack-{resource_type}"] = result
        except Exception as e:
            results[f"slack-{resource_type}"] = {
                "count": 0,
                "errors": 1,
                "error": str(e),
            }

    # Gmail: messages
    try:
        result = ingest_connector_snapshot(
            "gmail",
            "messages",
            tenant=tenant,
            user_id=user_id,
            limit=limit,
        )
        results["gmail-messages"] = result
    except Exception as e:
        results["gmail-messages"] = {"count": 0, "errors": 1, "error": str(e)}

    # Notion: pages and databases
    for resource_type in ["pages", "databases"]:
        try:
            result = ingest_connector_snapshot(
                "notion",
                resource_type,
                tenant=tenant,
                user_id=user_id,
                limit=limit,
            )
            results[f"notion-{resource_type}"] = result
        except Exception as e:
            results[f"notion-{resource_type}"] = {
                "count": 0,
                "errors": 1,
                "error": str(e),
            }

    return results
