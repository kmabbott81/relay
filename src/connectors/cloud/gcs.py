"""Google Cloud Storage connector."""

import os
from datetime import datetime, timezone
from typing import Any, Optional

from relay_ai.connectors.cloud.base import CloudConnector, ConnectorConfig, StagedItem


class GCSConnector(CloudConnector):
    """
    Google Cloud Storage connector using google-cloud-storage library.

    Requires:
    - GCS_SERVICE_ACCOUNT_JSON (path to service account key)
    - GCS_BUCKET_NAME

    No native delta sync; uses list_blobs with prefixes and page tokens.
    For change detection, use GCS Pub/Sub notifications.
    """

    def __init__(self, config: ConnectorConfig, bucket_name: Optional[str] = None):
        super().__init__(config)
        self.bucket_name = bucket_name or os.getenv("GCS_BUCKET_NAME")
        self.storage_client = None
        self.bucket = None

    def authenticate(self) -> bool:
        """Authenticate with Google Cloud Storage."""
        try:
            from google.cloud import storage

            service_account_json = os.getenv("GCS_SERVICE_ACCOUNT_JSON")

            if service_account_json:
                self.storage_client = storage.Client.from_service_account_json(service_account_json)
            else:
                # Try default credentials (GCE metadata, gcloud auth)
                self.storage_client = storage.Client()

            if self.bucket_name:
                self.bucket = self.storage_client.bucket(self.bucket_name)
                return True

            return False

        except Exception as e:
            print(f"GCS authentication failed: {e}")
            return False

    def list_items(
        self, folder_id: Optional[str] = None, page_token: Optional[str] = None
    ) -> tuple[list[StagedItem], Optional[str]]:
        """List objects in GCS bucket."""
        if not self.storage_client or not self.bucket:
            if not self.authenticate():
                return [], None

        try:
            prefix = folder_id or ""  # GCS uses prefix-based "folders"
            blobs = self.bucket.list_blobs(prefix=prefix, max_results=100, page_token=page_token)

            items = []
            for blob in blobs:
                staged_item = self._blob_to_staged_item(blob)
                items.append(staged_item)

            next_token = blobs.next_page_token if blobs.pages else None
            return items, next_token

        except Exception as e:
            print(f"GCS list_items failed: {e}")
            return [], None

    def get_delta_changes(self, delta_token: Optional[str] = None) -> tuple[list[StagedItem], Optional[str]]:
        """
        Get changes (pseudo-delta using updated timestamps).

        Note: GCS doesn't have native delta sync. This implementation lists all objects
        and compares updated timestamps. For production, use GCS Pub/Sub notifications.
        """
        if not self.storage_client or not self.bucket:
            if not self.authenticate():
                return [], None

        try:
            # Parse delta_token as ISO timestamp if provided
            cutoff_time = None
            if delta_token:
                try:
                    cutoff_time = datetime.fromisoformat(delta_token)
                except ValueError:
                    cutoff_time = None

            # List all objects and filter by updated timestamp
            items = []
            blobs = self.bucket.list_blobs()

            for blob in blobs:
                updated = blob.updated
                if cutoff_time and updated <= cutoff_time:
                    continue  # Skip unchanged objects

                staged_item = self._blob_to_staged_item(blob)
                items.append(staged_item)

            # New delta token = current timestamp
            new_delta_token = datetime.now(timezone.utc).isoformat()
            return items, new_delta_token

        except Exception as e:
            print(f"GCS get_delta_changes failed: {e}")
            return [], delta_token

    def _blob_to_staged_item(self, blob: Any) -> StagedItem:
        """Convert GCS blob to StagedItem."""
        name = blob.name
        size = blob.size or 0
        updated = blob.updated
        content_type = blob.content_type or "application/octet-stream"

        # Extract filename from name
        filename = name.split("/")[-1] if "/" in name else name
        is_folder = name.endswith("/")

        return StagedItem(
            external_id=name,  # Use blob name as ID
            path=name,
            name=filename,
            mime_type=content_type if not is_folder else "folder",
            size_bytes=size,
            last_modified=updated,
            is_folder=is_folder,
            parent_id=None,
            metadata={
                "bucket": self.bucket_name,
                "generation": str(blob.generation),
                "metageneration": str(blob.metageneration),
                "storage_class": blob.storage_class,
            },
        )
