"""AWS S3 connector."""

import os
from datetime import datetime, timezone
from typing import Any, Optional

from relay_ai.connectors.cloud.base import CloudConnector, ConnectorConfig, StagedItem


class S3Connector(CloudConnector):
    """
    AWS S3 connector using boto3.

    Requires:
    - AWS_ACCESS_KEY_ID
    - AWS_SECRET_ACCESS_KEY
    - AWS_REGION (optional, default: us-east-1)
    - S3_BUCKET_NAME

    No native delta sync; uses list_objects_v2 with prefixes and continuation tokens.
    For change detection, compare last_modified timestamps or use S3 Event Notifications.
    """

    def __init__(self, config: ConnectorConfig, bucket_name: Optional[str] = None):
        super().__init__(config)
        self.bucket_name = bucket_name or os.getenv("S3_BUCKET_NAME")
        self.s3_client = None

    def authenticate(self) -> bool:
        """Authenticate with AWS S3."""
        try:
            import boto3

            aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
            aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
            aws_region = os.getenv("AWS_REGION", "us-east-1")

            if aws_access_key and aws_secret_key:
                self.s3_client = boto3.client(
                    "s3", aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key, region_name=aws_region
                )
                return True

            # Try default credential chain (IAM role, etc.)
            self.s3_client = boto3.client("s3", region_name=aws_region)
            return True

        except Exception as e:
            print(f"S3 authentication failed: {e}")
            return False

    def list_items(
        self, folder_id: Optional[str] = None, page_token: Optional[str] = None
    ) -> tuple[list[StagedItem], Optional[str]]:
        """List objects in S3 bucket."""
        if not self.s3_client or not self.bucket_name:
            if not self.authenticate():
                return [], None

        try:
            prefix = folder_id or ""  # S3 uses prefix-based "folders"
            params = {"Bucket": self.bucket_name, "Prefix": prefix, "MaxKeys": 100}

            if page_token:
                params["ContinuationToken"] = page_token

            response = self.s3_client.list_objects_v2(**params)

            items = []
            for obj in response.get("Contents", []):
                staged_item = self._object_to_staged_item(obj)
                items.append(staged_item)

            next_token = response.get("NextContinuationToken")
            return items, next_token

        except Exception as e:
            print(f"S3 list_items failed: {e}")
            return [], None

    def get_delta_changes(self, delta_token: Optional[str] = None) -> tuple[list[StagedItem], Optional[str]]:
        """
        Get changes (pseudo-delta using last_modified timestamps).

        Note: S3 doesn't have native delta sync. This implementation lists all objects
        and compares last_modified. For production, use S3 Event Notifications with SQS/SNS.
        """
        if not self.s3_client or not self.bucket_name:
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

            # List all objects and filter by last_modified
            items = []
            continuation_token = None

            while True:
                params = {"Bucket": self.bucket_name, "MaxKeys": 100}
                if continuation_token:
                    params["ContinuationToken"] = continuation_token

                response = self.s3_client.list_objects_v2(**params)

                for obj in response.get("Contents", []):
                    last_modified = obj.get("LastModified")
                    if cutoff_time and last_modified <= cutoff_time:
                        continue  # Skip unchanged objects

                    staged_item = self._object_to_staged_item(obj)
                    items.append(staged_item)

                if not response.get("IsTruncated"):
                    break

                continuation_token = response.get("NextContinuationToken")

            # New delta token = current timestamp
            new_delta_token = datetime.now(timezone.utc).isoformat()
            return items, new_delta_token

        except Exception as e:
            print(f"S3 get_delta_changes failed: {e}")
            return [], delta_token

    def _object_to_staged_item(self, obj: dict[str, Any]) -> StagedItem:
        """Convert S3 object to StagedItem."""
        key = obj.get("Key")
        size = obj.get("Size", 0)
        last_modified = obj.get("LastModified")

        # Extract filename from key
        name = key.split("/")[-1] if "/" in key else key
        is_folder = key.endswith("/")

        return StagedItem(
            external_id=key,  # Use key as ID
            path=key,
            name=name,
            mime_type=self._guess_mime_type(name) if not is_folder else "folder",
            size_bytes=size,
            last_modified=last_modified,
            is_folder=is_folder,
            parent_id=None,
            metadata={"bucket": self.bucket_name, "etag": obj.get("ETag"), "storage_class": obj.get("StorageClass")},
        )

    def _guess_mime_type(self, filename: str) -> str:
        """Guess MIME type from filename extension."""
        import mimetypes

        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"
