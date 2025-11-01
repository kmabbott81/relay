"""Tests for Unified Resource Graph Index."""

import json
import tempfile
from pathlib import Path

import pytest

from src.graph.index import URGIndex, get_index, load_index


@pytest.fixture
def index():
    """Get URG index (isolated by clean_graph_env autouse fixture)."""
    return get_index()


@pytest.fixture
def temp_store():
    """Create temporary store directory for persistence tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def test_upsert_creates_entry(index):
    """Test upserting a resource creates index entry."""
    resource = {
        "id": "msg-123",
        "type": "message",
        "title": "Test Message",
        "snippet": "This is a test message",
        "timestamp": "2025-01-15T10:00:00Z",
    }

    graph_id = index.upsert(resource, source="teams", tenant="test-tenant")

    assert graph_id == "urn:teams:message:msg-123"
    assert graph_id in index.resources
    assert index.resources[graph_id]["title"] == "Test Message"


def test_upsert_requires_id(index):
    """Test upsert requires 'id' field."""
    resource = {
        "type": "message",
        "title": "No ID",
    }

    with pytest.raises(ValueError, match="must have 'id' field"):
        index.upsert(resource, source="teams", tenant="test-tenant")


def test_upsert_requires_type(index):
    """Test upsert requires 'type' field."""
    resource = {
        "id": "msg-123",
        "title": "No Type",
    }

    with pytest.raises(ValueError, match="must have 'type' field"):
        index.upsert(resource, source="teams", tenant="test-tenant")


def test_upsert_overwrites_existing(index):
    """Test upserting same ID updates resource."""
    resource1 = {
        "id": "msg-123",
        "type": "message",
        "title": "Original Title",
    }

    resource2 = {
        "id": "msg-123",
        "type": "message",
        "title": "Updated Title",
    }

    graph_id1 = index.upsert(resource1, source="teams", tenant="test-tenant")
    graph_id2 = index.upsert(resource2, source="teams", tenant="test-tenant")

    assert graph_id1 == graph_id2
    assert index.resources[graph_id1]["title"] == "Updated Title"


def test_get_resource_by_id(index):
    """Test getting resource by graph ID."""
    resource = {
        "id": "msg-456",
        "type": "message",
        "title": "Find Me",
    }

    graph_id = index.upsert(resource, source="outlook", tenant="tenant-a")

    retrieved = index.get(graph_id, tenant="tenant-a")

    assert retrieved is not None
    assert retrieved["title"] == "Find Me"


def test_get_enforces_tenant_isolation(index):
    """Test get enforces tenant isolation."""
    resource = {
        "id": "msg-789",
        "type": "message",
        "title": "Private Message",
    }

    graph_id = index.upsert(resource, source="slack", tenant="tenant-a")

    # Can access with correct tenant
    result = index.get(graph_id, tenant="tenant-a")
    assert result is not None

    # Cannot access with different tenant
    result = index.get(graph_id, tenant="tenant-b")
    assert result is None


def test_type_indexing(index):
    """Test resources indexed by type."""
    msg_resource = {
        "id": "msg-1",
        "type": "message",
        "title": "Message",
    }

    contact_resource = {
        "id": "contact-1",
        "type": "contact",
        "title": "Contact",
    }

    msg_id = index.upsert(msg_resource, source="teams", tenant="test-tenant")
    contact_id = index.upsert(contact_resource, source="outlook", tenant="test-tenant")

    assert msg_id in index.type_index["message"]
    assert contact_id in index.type_index["contact"]
    assert msg_id not in index.type_index["contact"]


def test_source_indexing(index):
    """Test resources indexed by source."""
    teams_resource = {
        "id": "msg-1",
        "type": "message",
        "title": "Teams Message",
    }

    slack_resource = {
        "id": "msg-2",
        "type": "message",
        "title": "Slack Message",
    }

    teams_id = index.upsert(teams_resource, source="teams", tenant="test-tenant")
    slack_id = index.upsert(slack_resource, source="slack", tenant="test-tenant")

    assert teams_id in index.source_index["teams"]
    assert slack_id in index.source_index["slack"]
    assert teams_id not in index.source_index["slack"]


def test_tenant_indexing(index):
    """Test resources indexed by tenant."""
    resource_a = {
        "id": "msg-1",
        "type": "message",
        "title": "Tenant A",
    }

    resource_b = {
        "id": "msg-2",
        "type": "message",
        "title": "Tenant B",
    }

    id_a = index.upsert(resource_a, source="teams", tenant="tenant-a")
    id_b = index.upsert(resource_b, source="teams", tenant="tenant-b")

    assert id_a in index.tenant_index["tenant-a"]
    assert id_b in index.tenant_index["tenant-b"]
    assert id_a not in index.tenant_index["tenant-b"]


def test_inverted_index_building(index):
    """Test inverted index built from searchable fields."""
    resource = {
        "id": "msg-100",
        "type": "message",
        "title": "Planning Meeting",
        "snippet": "Let's discuss the Q4 roadmap",
        "participants": ["alice@example.com", "bob@example.com"],
    }

    graph_id = index.upsert(resource, source="teams", tenant="test-tenant")

    # Check tokens in inverted index
    assert graph_id in index.inverted_index["planning"]
    assert graph_id in index.inverted_index["meeting"]
    assert graph_id in index.inverted_index["q4"]
    assert graph_id in index.inverted_index["alice"]
    assert graph_id in index.inverted_index["example"]


def test_shard_persistence(temp_store, monkeypatch):
    """Test resources persisted to JSONL shards."""
    # Use a separate path for this test
    monkeypatch.setenv("URG_STORE_PATH", temp_store)
    index = load_index(temp_store)

    resource = {
        "id": "msg-persist",
        "type": "message",
        "title": "Persistent Message",
    }

    graph_id = index.upsert(resource, source="teams", tenant="test-tenant")

    # Check shard file created
    shard_dir = Path(temp_store) / "test-tenant"
    assert shard_dir.exists()

    # Check JSONL content
    shard_files = list(shard_dir.glob("*.jsonl"))
    assert len(shard_files) > 0

    with open(shard_files[0]) as f:
        lines = f.readlines()
        assert len(lines) >= 1

        first_line = json.loads(lines[0])
        assert first_line["id"] == graph_id


def test_shard_loading_on_init(temp_store, monkeypatch):
    """Test shards loaded on initialization."""
    # Use separate path for this test
    monkeypatch.setenv("URG_STORE_PATH", temp_store)

    # Create index and add resources
    index1 = URGIndex(store_path=temp_store)

    resource1 = {
        "id": "msg-1",
        "type": "message",
        "title": "First",
    }

    resource2 = {
        "id": "msg-2",
        "type": "message",
        "title": "Second",
    }

    id1 = index1.upsert(resource1, source="teams", tenant="test-tenant")
    id2 = index1.upsert(resource2, source="teams", tenant="test-tenant")

    # Create new index (should load from shards)
    index2 = URGIndex(store_path=temp_store)

    assert id1 in index2.resources
    assert id2 in index2.resources
    assert index2.resources[id1]["title"] == "First"
    assert index2.resources[id2]["title"] == "Second"


def test_rebuild_index(temp_store, monkeypatch):
    """Test rebuilding index from shards."""
    monkeypatch.setenv("URG_STORE_PATH", temp_store)
    index = URGIndex(store_path=temp_store)

    resource = {
        "id": "msg-rebuild",
        "type": "message",
        "title": "Rebuild Test",
    }

    graph_id = index.upsert(resource, source="teams", tenant="test-tenant")

    # Clear in-memory indexes
    index.resources.clear()
    index.inverted_index.clear()

    assert len(index.resources) == 0

    # Rebuild
    index.rebuild_index()

    # Verify restored
    assert graph_id in index.resources
    assert index.resources[graph_id]["title"] == "Rebuild Test"


def test_list_by_tenant(index):
    """Test listing resources by tenant."""
    for i in range(5):
        resource = {
            "id": f"msg-{i}",
            "type": "message",
            "title": f"Message {i}",
            "timestamp": f"2025-01-{10+i:02d}T10:00:00Z",
        }
        index.upsert(resource, source="teams", tenant="tenant-list")

    results = index.list_by_tenant("tenant-list", limit=3)

    assert len(results) == 3
    # Should be sorted by timestamp descending
    assert results[0]["title"] == "Message 4"


def test_get_stats(index):
    """Test getting index statistics."""
    # Add various resources
    index.upsert(
        {"id": "m1", "type": "message", "title": "M1"},
        source="teams",
        tenant="tenant-a",
    )
    index.upsert(
        {"id": "m2", "type": "message", "title": "M2"},
        source="slack",
        tenant="tenant-a",
    )
    index.upsert(
        {"id": "c1", "type": "contact", "title": "C1"},
        source="outlook",
        tenant="tenant-b",
    )

    # All stats
    stats = index.get_stats()
    assert stats["total"] == 3
    assert stats["by_type"]["message"] == 2
    assert stats["by_type"]["contact"] == 1
    assert stats["by_source"]["teams"] == 1
    assert stats["by_source"]["slack"] == 1
    assert stats["by_source"]["outlook"] == 1

    # Tenant-filtered stats
    stats_a = index.get_stats(tenant="tenant-a")
    assert stats_a["total"] == 2
    assert stats_a["by_type"]["message"] == 2
