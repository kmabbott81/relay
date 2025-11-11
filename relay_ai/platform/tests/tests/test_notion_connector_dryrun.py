"""Test Notion connector in DRY_RUN mode.

All tests run offline using mock responses.
"""

import os

import pytest

from relay_ai.connectors.notion import NotionConnector


@pytest.fixture
def notion_connector():
    """Create Notion connector in DRY_RUN mode."""
    os.environ["DRY_RUN"] = "true"
    os.environ["LIVE"] = "false"
    os.environ["USER_ROLE"] = "Admin"
    os.environ["CONNECTOR_RBAC_ROLE"] = "Operator"

    # Set up team role for RBAC
    from src.security.teams import upsert_team_member

    upsert_team_member("tenant-1", "user-1", "Admin", "Test Tenant")

    connector = NotionConnector(
        connector_id="test-notion",
        tenant_id="tenant-1",
        user_id="user-1",
    )

    yield connector

    # Cleanup
    if connector.mock_path.exists():
        connector.mock_path.unlink()


def test_connect_dry_run(notion_connector):
    """Test connection in DRY_RUN mode."""
    assert notion_connector.dry_run is True
    result = notion_connector.connect()
    assert result.status == "success"
    assert notion_connector.connected is True


def test_list_pages(notion_connector):
    """Test listing pages."""
    result = notion_connector.list_resources("pages")

    assert result.status == "success"
    assert isinstance(result.data, list)
    assert len(result.data) >= 0

    # Verify metrics were recorded
    assert notion_connector.mock_path.exists()


def test_list_pages_with_query(notion_connector):
    """Test listing pages with search query."""
    result = notion_connector.list_resources("pages", filters={"query": "test"})

    assert result.status == "success"
    assert isinstance(result.data, list)


def test_list_databases(notion_connector):
    """Test listing databases."""
    result = notion_connector.list_resources("databases")

    assert result.status == "success"
    assert isinstance(result.data, list)


def test_list_blocks(notion_connector):
    """Test listing blocks in page."""
    result = notion_connector.list_resources("blocks", filters={"page_id": "page-123"})

    assert result.status == "success"
    assert isinstance(result.data, list)


def test_list_blocks_no_page_id(notion_connector):
    """Test listing blocks without page_id fails."""
    result = notion_connector.list_resources("blocks")

    assert result.status == "error"
    assert "page_id or block_id required" in result.message


def test_get_page(notion_connector):
    """Test getting specific page."""
    result = notion_connector.get_resource("pages", "page-123")

    assert result.status == "success"
    assert isinstance(result.data, dict)
    assert result.data.get("object") == "page"


def test_get_database(notion_connector):
    """Test getting specific database."""
    result = notion_connector.get_resource("databases", "db-123")

    assert result.status == "success"
    assert isinstance(result.data, dict)


def test_get_block(notion_connector):
    """Test getting specific block."""
    result = notion_connector.get_resource("blocks", "block-123")

    assert result.status == "success"
    assert isinstance(result.data, dict)


def test_create_page(notion_connector):
    """Test creating page."""
    payload = {
        "parent": {"type": "page_id", "page_id": "parent-page-123"},
        "properties": {
            "title": {
                "title": [
                    {
                        "type": "text",
                        "text": {"content": "New Test Page"},
                    }
                ]
            }
        },
    }

    result = notion_connector.create_resource("pages", payload)

    assert result.status == "success"
    assert isinstance(result.data, dict)


def test_create_blocks(notion_connector):
    """Test creating blocks (appending to page)."""
    payload = {
        "parent_id": "page-123",
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": "New paragraph"},
                        }
                    ]
                },
            }
        ],
    }

    result = notion_connector.create_resource("blocks", payload)

    assert result.status == "success"


def test_create_blocks_no_parent(notion_connector):
    """Test creating blocks without parent_id fails."""
    payload = {
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": []},
            }
        ],
    }

    result = notion_connector.create_resource("blocks", payload)

    assert result.status == "error"
    assert "parent_id required" in result.message


def test_update_page(notion_connector):
    """Test updating page properties."""
    payload = {
        "properties": {
            "title": {
                "title": [
                    {
                        "type": "text",
                        "text": {"content": "Updated Title"},
                    }
                ]
            }
        }
    }

    result = notion_connector.update_resource("pages", "page-123", payload)

    assert result.status == "success"
    assert isinstance(result.data, dict)


def test_update_database(notion_connector):
    """Test updating database properties."""
    payload = {"title": [{"type": "text", "text": {"content": "Updated Database"}}]}

    result = notion_connector.update_resource("databases", "db-123", payload)

    assert result.status == "success"


def test_update_block(notion_connector):
    """Test updating block content."""
    payload = {
        "paragraph": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": "Updated paragraph"},
                }
            ]
        }
    }

    result = notion_connector.update_resource("blocks", "block-123", payload)

    assert result.status == "success"


def test_delete_page(notion_connector):
    """Test deleting (archiving) page."""
    result = notion_connector.delete_resource("pages", "page-123")

    assert result.status == "success"
    assert "archived" in result.message.lower()


def test_delete_database(notion_connector):
    """Test deleting (archiving) database."""
    result = notion_connector.delete_resource("databases", "db-123")

    assert result.status == "success"
    assert "archived" in result.message.lower()


def test_delete_block(notion_connector):
    """Test deleting block."""
    result = notion_connector.delete_resource("blocks", "block-123")

    assert result.status == "success"
    assert "deleted" in result.message.lower()


def test_rbac_read_denied(notion_connector):
    """Test RBAC enforcement for reads."""
    # Set role below Operator by updating team membership
    from src.security.teams import upsert_team_member

    upsert_team_member("tenant-1", "user-1", "Viewer", "Test Tenant")

    # Set required role to Operator
    notion_connector.required_role = "Operator"

    result = notion_connector.list_resources("pages")

    assert result.status == "denied"
    assert "permissions" in result.message.lower()


def test_rbac_write_denied(notion_connector):
    """Test RBAC enforcement for writes."""
    # Set role below Admin by updating team membership
    from src.security.teams import upsert_team_member

    upsert_team_member("tenant-1", "user-1", "Operator", "Test Tenant")

    payload = {"properties": {}}
    result = notion_connector.create_resource("pages", payload)

    assert result.status == "denied"
    assert "admin" in result.message.lower()


def test_unknown_resource_type(notion_connector):
    """Test unknown resource type returns error."""
    result = notion_connector.list_resources("unknown_type")

    assert result.status == "error"
    assert "Unknown resource type" in result.message


def test_disconnect(notion_connector):
    """Test disconnect."""
    notion_connector.connect()
    result = notion_connector.disconnect()

    assert result.status == "success"
    assert notion_connector.connected is False


def test_metrics_recorded(notion_connector):
    """Test that metrics are recorded for operations."""
    # Perform operation
    notion_connector.list_resources("pages")

    # Check mock file created (which happens during metric recording)
    assert notion_connector.mock_path.exists()

    # Verify mock file has data
    with open(notion_connector.mock_path, encoding="utf-8") as f:
        content = f.read()
        assert len(content) > 0
