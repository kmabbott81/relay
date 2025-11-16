"""Unified Resource Graph (URG) Index.

Provides storage and in-memory indexing for normalized resources from all connectors.
Supports fast search/filter with JSONL shard-based persistence.
"""

import json
import os
import re
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional


class URGIndex:
    """Unified Resource Graph in-memory index with JSONL persistence.

    Features:
    - Append-only JSONL shards (one per tenant per day)
    - In-memory inverted index for fast search
    - Thread-safe writes
    - Automatic shard loading on init
    """

    def __init__(self, store_path: Optional[str] = None):
        """Initialize URG index.

        Args:
            store_path: Path to store JSONL shards (default: logs/graph)
        """
        self.store_path = Path(store_path or os.getenv("URG_STORE_PATH", "logs/graph"))
        self.store_path.mkdir(parents=True, exist_ok=True)

        # In-memory storage: {graph_id: resource}
        self.resources: dict[str, dict] = {}

        # Inverted index: {token: set(graph_ids)}
        self.inverted_index: dict[str, set[str]] = defaultdict(set)

        # Type index: {type: set(graph_ids)}
        self.type_index: dict[str, set[str]] = defaultdict(set)

        # Source index: {source: set(graph_ids)}
        self.source_index: dict[str, set[str]] = defaultdict(set)

        # Tenant index: {tenant: set(graph_ids)}
        self.tenant_index: dict[str, set[str]] = defaultdict(set)

        # Thread lock for writes
        self.write_lock = threading.Lock()

        # Load existing shards
        self._load_shards()

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text for indexing.

        Args:
            text: Text to tokenize

        Returns:
            List of lowercase tokens
        """
        if not text:
            return []

        # Lowercase and split on non-word characters
        tokens = re.split(r"\W+", text.lower())
        return [t for t in tokens if t]

    def _index_resource(self, graph_id: str, resource: dict):
        """Add resource to in-memory indexes.

        Args:
            graph_id: Unique graph ID
            resource: Resource data
        """
        # Store resource
        self.resources[graph_id] = resource

        # Index by type
        resource_type = resource.get("type", "")
        if resource_type:
            self.type_index[resource_type].add(graph_id)

        # Index by source
        source = resource.get("source", "")
        if source:
            self.source_index[source].add(graph_id)

        # Index by tenant
        tenant = resource.get("tenant", "")
        if tenant:
            self.tenant_index[tenant].add(graph_id)

        # Build inverted index from searchable fields
        searchable_text = []

        # Add title
        if resource.get("title"):
            searchable_text.append(resource["title"])

        # Add snippet
        if resource.get("snippet"):
            searchable_text.append(resource["snippet"])

        # Add participants
        if resource.get("participants"):
            participants = resource["participants"]
            if isinstance(participants, list):
                searchable_text.extend(participants)
            elif isinstance(participants, str):
                searchable_text.append(participants)

        # Add labels
        if resource.get("labels"):
            labels = resource["labels"]
            if isinstance(labels, list):
                searchable_text.extend(labels)
            elif isinstance(labels, str):
                searchable_text.append(labels)

        # Tokenize and index
        for text in searchable_text:
            tokens = self._tokenize(str(text))
            for token in tokens:
                self.inverted_index[token].add(graph_id)

    def _unindex_resource(self, graph_id: str):
        """Remove resource from in-memory indexes.

        Args:
            graph_id: Unique graph ID
        """
        if graph_id not in self.resources:
            return

        resource = self.resources[graph_id]

        # Remove from type index
        resource_type = resource.get("type", "")
        if resource_type and graph_id in self.type_index[resource_type]:
            self.type_index[resource_type].discard(graph_id)

        # Remove from source index
        source = resource.get("source", "")
        if source and graph_id in self.source_index[source]:
            self.source_index[source].discard(graph_id)

        # Remove from tenant index
        tenant = resource.get("tenant", "")
        if tenant and graph_id in self.tenant_index[tenant]:
            self.tenant_index[tenant].discard(graph_id)

        # Remove from inverted index
        for token_set in self.inverted_index.values():
            token_set.discard(graph_id)

        # Remove resource
        del self.resources[graph_id]

    def _load_shards(self):
        """Load all JSONL shards from disk into memory."""
        if not self.store_path.exists():
            return

        loaded_count = 0

        # Walk through tenant directories
        for tenant_dir in self.store_path.iterdir():
            if not tenant_dir.is_dir():
                continue

            # Load each JSONL shard
            for shard_file in tenant_dir.glob("*.jsonl"):
                try:
                    with open(shard_file, encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue

                            try:
                                resource = json.loads(line)
                                graph_id = resource.get("id")
                                if graph_id:
                                    self._index_resource(graph_id, resource)
                                    loaded_count += 1
                            except json.JSONDecodeError:
                                # Skip malformed lines
                                continue
                except Exception as e:
                    print(f"Warning: Failed to load shard {shard_file}: {e}")

        if loaded_count > 0:
            print(f"URG Index: Loaded {loaded_count} resources from {self.store_path}")

    def _get_shard_path(self, tenant: str) -> Path:
        """Get JSONL shard path for tenant and current date.

        Args:
            tenant: Tenant ID

        Returns:
            Path to shard file
        """
        tenant_dir = self.store_path / tenant
        tenant_dir.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now().strftime("%Y-%m-%d")
        return tenant_dir / f"{date_str}.jsonl"

    def upsert(self, resource: dict, *, source: str, tenant: str) -> str:
        """Store or update resource in URG.

        Args:
            resource: Normalized resource data
            source: Source connector (teams, outlook, slack, gmail)
            tenant: Tenant ID for isolation

        Returns:
            Graph ID of stored resource

        Raises:
            ValueError: If required fields missing
        """
        # Validate required fields
        if not resource.get("id"):
            raise ValueError("Resource must have 'id' field")

        if not resource.get("type"):
            raise ValueError("Resource must have 'type' field")

        # Generate graph ID
        original_id = resource["id"]
        resource_type = resource["type"]
        graph_id = f"urn:{source}:{resource_type}:{original_id}"

        # Ensure required fields are present
        full_resource = {
            "id": graph_id,
            "type": resource_type,
            "title": resource.get("title", ""),
            "snippet": resource.get("snippet", ""),
            "timestamp": resource.get("timestamp", datetime.now().isoformat()),
            "source": source,
            "tenant": tenant,
            "labels": resource.get("labels", []),
            "participants": resource.get("participants", []),
            "thread_id": resource.get("thread_id", ""),
            "channel_id": resource.get("channel_id", ""),
            "metadata": resource.get("metadata", {}),
        }

        # Add original_id to metadata
        if "original_id" not in full_resource["metadata"]:
            full_resource["metadata"]["original_id"] = original_id

        # Thread-safe write
        with self.write_lock:
            # Remove old version from indexes if exists
            if graph_id in self.resources:
                self._unindex_resource(graph_id)

            # Index new version
            self._index_resource(graph_id, full_resource)

            # Append to JSONL shard
            shard_path = self._get_shard_path(tenant)
            with open(shard_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(full_resource, separators=(",", ":")) + "\n")

        return graph_id

    def get(self, graph_id: str, *, tenant: str) -> Optional[dict]:
        """Get resource by graph ID.

        Args:
            graph_id: Unique graph ID
            tenant: Tenant ID for isolation

        Returns:
            Resource data or None if not found
        """
        resource = self.resources.get(graph_id)

        # Enforce tenant isolation
        if resource and resource.get("tenant") == tenant:
            return resource

        return None

    def list_by_tenant(self, tenant: str, limit: int = 100) -> list[dict]:
        """List resources for tenant.

        Args:
            tenant: Tenant ID
            limit: Maximum number of results

        Returns:
            List of resources
        """
        graph_ids = self.tenant_index.get(tenant, set())
        resources = [self.resources[gid] for gid in graph_ids if gid in self.resources]

        # Sort by timestamp descending
        resources.sort(key=lambda r: r.get("timestamp", ""), reverse=True)

        return resources[:limit]

    def rebuild_index(self, tenant: Optional[str] = None):
        """Rebuild in-memory index from JSONL shards.

        Args:
            tenant: Optional tenant to rebuild (default: all tenants)
        """
        # Clear indexes
        self.resources.clear()
        self.inverted_index.clear()
        self.type_index.clear()
        self.source_index.clear()
        self.tenant_index.clear()

        # Reload shards
        self._load_shards()

    def get_stats(self, tenant: Optional[str] = None) -> dict:
        """Get index statistics.

        Args:
            tenant: Optional tenant to filter stats

        Returns:
            Statistics dict with counts by type and source
        """
        if tenant:
            graph_ids = self.tenant_index.get(tenant, set())
            resources = [self.resources[gid] for gid in graph_ids if gid in self.resources]
        else:
            resources = list(self.resources.values())

        stats = {
            "total": len(resources),
            "by_type": defaultdict(int),
            "by_source": defaultdict(int),
            "by_tenant": defaultdict(int),
        }

        for resource in resources:
            resource_type = resource.get("type", "unknown")
            source = resource.get("source", "unknown")
            tenant_id = resource.get("tenant", "unknown")

            stats["by_type"][resource_type] += 1
            stats["by_source"][source] += 1
            stats["by_tenant"][tenant_id] += 1

        # Convert defaultdicts to regular dicts
        stats["by_type"] = dict(stats["by_type"])
        stats["by_source"] = dict(stats["by_source"])
        stats["by_tenant"] = dict(stats["by_tenant"])

        return stats


# Global singleton instance
_index: Optional[URGIndex] = None
_index_lock = threading.Lock()


def reset_index():
    """Reset global index (for testing).

    Clears the global index singleton, forcing a new instance
    to be created on next get_index() call.
    """
    global _index
    with _index_lock:
        _index = None


def get_index() -> URGIndex:
    """Get or create global URG index instance.

    Returns:
        URGIndex instance
    """
    global _index
    with _index_lock:
        if _index is None:
            store_path = os.getenv("URG_STORE_PATH", "logs/graph")
            _index = URGIndex(store_path)
        return _index


def load_index(path: str) -> URGIndex:
    """Load index from specific path (for testing).

    Args:
        path: Path to store directory

    Returns:
        URGIndex instance loaded from path
    """
    reset_index()
    global _index
    with _index_lock:
        _index = URGIndex(path)
        return _index
