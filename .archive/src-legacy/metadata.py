"""Metadata storage for staged items and ingested content."""

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


# Database path (function to allow dynamic env var evaluation)
def get_db_path():
    """Get database path from environment or default."""
    return Path(os.getenv("METADATA_DB_PATH", "data/metadata.db"))


@dataclass
class StagedItemRecord:
    """Represents a staged item ready for ingestion."""

    id: Optional[int] = None  # Auto-increment primary key
    tenant_id: str = "default"
    connector: str = ""  # gdrive, onedrive, s3, etc.
    external_id: str = ""  # Provider-specific ID
    path: str = ""  # Human-readable path
    name: str = ""  # File/folder name
    mime_type: str = ""  # MIME type
    size_bytes: int = 0  # File size
    last_modified: Optional[str] = None  # ISO timestamp
    delta_token: Optional[str] = None  # For incremental sync
    status: str = "staged"  # staged, ingesting, ingested, failed, skipped
    error_message: Optional[str] = None  # If status=failed
    metadata_json: Optional[str] = None  # Provider-specific metadata as JSON
    created_at: Optional[str] = None  # ISO timestamp
    updated_at: Optional[str] = None  # ISO timestamp


def init_metadata_db():
    """Initialize metadata database with staged_items and user_prefs tables."""
    db_path = get_db_path()
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create staged_items table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS staged_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            connector TEXT NOT NULL,
            external_id TEXT NOT NULL,
            path TEXT NOT NULL,
            name TEXT NOT NULL,
            mime_type TEXT,
            size_bytes INTEGER DEFAULT 0,
            last_modified TEXT,
            delta_token TEXT,
            status TEXT DEFAULT 'staged',
            error_message TEXT,
            metadata_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tenant_id, connector, external_id)
        )
    """
    )

    # Create indexes for staged_items
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_staged_tenant_connector ON staged_items(tenant_id, connector)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_staged_status ON staged_items(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_staged_external_id ON staged_items(external_id)")

    # Create user_prefs table (Sprint 22)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_prefs (
            user_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, tenant_id, key)
        )
    """
    )

    # Create indexes for user_prefs
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_prefs_user_tenant ON user_prefs(user_id, tenant_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_prefs_updated ON user_prefs(updated_at DESC)")

    conn.commit()
    conn.close()


def insert_staged_item(item: StagedItemRecord) -> int:
    """Insert or update a staged item. Returns row ID."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    now = datetime.utcnow().isoformat()

    try:
        cursor.execute(
            """
            INSERT INTO staged_items (
                tenant_id, connector, external_id, path, name, mime_type,
                size_bytes, last_modified, delta_token, status, metadata_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id, connector, external_id) DO UPDATE SET
                path=excluded.path,
                name=excluded.name,
                mime_type=excluded.mime_type,
                size_bytes=excluded.size_bytes,
                last_modified=excluded.last_modified,
                delta_token=excluded.delta_token,
                status=excluded.status,
                metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at
        """,
            (
                item.tenant_id,
                item.connector,
                item.external_id,
                item.path,
                item.name,
                item.mime_type,
                item.size_bytes,
                item.last_modified,
                item.delta_token,
                item.status,
                item.metadata_json,
                now,
                now,
            ),
        )

        row_id = cursor.lastrowid
        conn.commit()
        return row_id

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_staged_items(
    tenant_id: str, connector: Optional[str] = None, status: Optional[str] = None, limit: int = 100
) -> list[StagedItemRecord]:
    """Query staged items by tenant, connector, and status."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = "SELECT * FROM staged_items WHERE tenant_id = ?"
    params = [tenant_id]

    if connector:
        query += " AND connector = ?"
        params.append(connector)

    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    items = []
    for row in rows:
        item = StagedItemRecord(
            id=row["id"],
            tenant_id=row["tenant_id"],
            connector=row["connector"],
            external_id=row["external_id"],
            path=row["path"],
            name=row["name"],
            mime_type=row["mime_type"],
            size_bytes=row["size_bytes"],
            last_modified=row["last_modified"],
            delta_token=row["delta_token"],
            status=row["status"],
            error_message=row["error_message"],
            metadata_json=row["metadata_json"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        items.append(item)

    return items


def update_staged_item_status(item_id: int, status: str, error_message: Optional[str] = None):
    """Update the status of a staged item."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    now = datetime.utcnow().isoformat()

    cursor.execute(
        """
        UPDATE staged_items
        SET status = ?, error_message = ?, updated_at = ?
        WHERE id = ?
    """,
        (status, error_message, now, item_id),
    )

    conn.commit()
    conn.close()


def get_delta_token(tenant_id: str, connector: str) -> Optional[str]:
    """Get the latest delta token for a tenant/connector pair."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT delta_token FROM staged_items
        WHERE tenant_id = ? AND connector = ?
        AND delta_token IS NOT NULL
        ORDER BY updated_at DESC
        LIMIT 1
    """,
        (tenant_id, connector),
    )

    row = cursor.fetchone()
    conn.close()

    return row[0] if row else None


def save_delta_token(tenant_id: str, connector: str, delta_token: str):
    """Save delta token for a tenant/connector pair."""
    # Insert a marker record with just the delta token
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    now = datetime.utcnow().isoformat()

    cursor.execute(
        """
        INSERT INTO staged_items (
            tenant_id, connector, external_id, path, name, delta_token, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tenant_id, connector, external_id) DO UPDATE SET
            delta_token=excluded.delta_token,
            updated_at=excluded.updated_at
    """,
        (tenant_id, connector, f"_delta_marker_{connector}", "", "_delta_marker", delta_token, "marker", now, now),
    )

    conn.commit()
    conn.close()


def get_user_prefs(user_id: str, tenant_id: str) -> dict[str, str]:
    """Get all preferences for a user in a tenant."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT key, value FROM user_prefs
        WHERE user_id = ? AND tenant_id = ?
    """,
        (user_id, tenant_id),
    )

    rows = cursor.fetchall()
    conn.close()

    return {row["key"]: row["value"] for row in rows}


def set_user_pref(user_id: str, tenant_id: str, key: str, value: str) -> None:
    """Set a preference for a user in a tenant."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    now = datetime.utcnow().isoformat()

    cursor.execute(
        """
        INSERT INTO user_prefs (user_id, tenant_id, key, value, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, tenant_id, key) DO UPDATE SET
            value=excluded.value,
            updated_at=excluded.updated_at
    """,
        (user_id, tenant_id, key, value, now),
    )

    conn.commit()
    conn.close()


def delete_user_pref(user_id: str, tenant_id: str, key: str) -> None:
    """Delete a preference for a user in a tenant."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM user_prefs
        WHERE user_id = ? AND tenant_id = ? AND key = ?
    """,
        (user_id, tenant_id, key),
    )

    conn.commit()
    conn.close()


def clear_user_prefs(user_id: str, tenant_id: str) -> None:
    """Clear all preferences for a user in a tenant."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM user_prefs
        WHERE user_id = ? AND tenant_id = ?
    """,
        (user_id, tenant_id),
    )

    conn.commit()
    conn.close()


# Initialize database on import
init_metadata_db()
