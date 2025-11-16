"""Base classes for cloud folder connectors."""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class StagedItem:
    """Represents a file or folder staged for ingestion."""

    external_id: str  # Provider-specific ID
    path: str  # Human-readable path
    name: str  # File/folder name
    mime_type: str  # MIME type (application/pdf, etc.)
    size_bytes: int  # File size
    last_modified: datetime  # Last modification time
    is_folder: bool = False  # True if folder, False if file
    parent_id: Optional[str] = None  # Parent folder ID
    metadata: Optional[dict[str, Any]] = None  # Provider-specific metadata


@dataclass
class ConnectorConfig:
    """Configuration for cloud connector."""

    tenant_id: str
    connector_name: str  # gdrive, onedrive, etc.
    include_patterns: list[str] = None  # Glob patterns to include
    exclude_patterns: list[str] = None  # Glob patterns to exclude
    mime_types: list[str] = None  # MIME types to include
    max_size_bytes: Optional[int] = None  # Max file size
    min_modified_date: Optional[datetime] = None  # Only files modified after this date
    max_modified_date: Optional[datetime] = None  # Only files modified before this date

    def __post_init__(self):
        if self.include_patterns is None:
            self.include_patterns = ["*"]
        if self.exclude_patterns is None:
            self.exclude_patterns = []
        if self.mime_types is None:
            self.mime_types = []


class CloudConnector(ABC):
    """Abstract base class for cloud folder connectors."""

    def __init__(self, config: ConnectorConfig):
        self.config = config
        self.delta_token: Optional[str] = None

    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with the cloud provider. Returns True if successful."""
        pass

    @abstractmethod
    def list_items(
        self, folder_id: Optional[str] = None, page_token: Optional[str] = None
    ) -> tuple[list[StagedItem], Optional[str]]:
        """
        List items in a folder.

        Args:
            folder_id: Provider-specific folder ID (None = root)
            page_token: Pagination token for next page

        Returns:
            Tuple of (items, next_page_token)
        """
        pass

    @abstractmethod
    def get_delta_changes(self, delta_token: Optional[str] = None) -> tuple[list[StagedItem], Optional[str]]:
        """
        Get incremental changes since last delta sync.

        Args:
            delta_token: Token from previous delta sync (None = full sync)

        Returns:
            Tuple of (changed_items, new_delta_token)
        """
        pass

    def should_include(self, item: StagedItem) -> bool:
        """Check if item matches include/exclude patterns and filters."""
        # Skip folders
        if item.is_folder:
            return False

        # Check size limits
        if self.config.max_size_bytes and item.size_bytes > self.config.max_size_bytes:
            return False

        # Check date range
        if self.config.min_modified_date and item.last_modified < self.config.min_modified_date:
            return False
        if self.config.max_modified_date and item.last_modified > self.config.max_modified_date:
            return False

        # Check MIME types
        if self.config.mime_types and item.mime_type not in self.config.mime_types:
            return False

        # Check exclude patterns first
        for pattern in self.config.exclude_patterns:
            if self._matches_glob(item.path, pattern):
                return False

        # Check include patterns
        for pattern in self.config.include_patterns:
            if self._matches_glob(item.path, pattern):
                return True

        # Default: include if no patterns matched
        return len(self.config.include_patterns) == 1 and self.config.include_patterns[0] == "*"

    def _matches_glob(self, path: str, pattern: str) -> bool:
        """Check if path matches glob pattern."""
        # Convert glob pattern to regex
        regex_pattern = pattern.replace(".", r"\.").replace("*", ".*").replace("?", ".")
        regex_pattern = f"^{regex_pattern}$"
        return bool(re.match(regex_pattern, path, re.IGNORECASE))

    def filter_items(self, items: list[StagedItem]) -> list[StagedItem]:
        """Filter items based on config rules."""
        return [item for item in items if self.should_include(item)]
