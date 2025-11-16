"""Storage abstraction for local, S3, and GCS backends."""

import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# Cloud SDKs are optional dependencies
try:
    import boto3
    from botocore.exceptions import ClientError

    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False

try:
    from google.api_core.exceptions import GoogleAPIError
    from google.cloud import storage as gcs_storage

    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False


class StorageBackend:
    """Abstract base for storage backends."""

    def write(self, path: str, content: str) -> str:
        """Write content to path. Returns full path/URI."""
        raise NotImplementedError

    def read(self, path: str) -> str:
        """Read content from path."""
        raise NotImplementedError

    def list(self, prefix: str = "") -> list[str]:
        """List files with optional prefix filter."""
        raise NotImplementedError

    def exists(self, path: str) -> bool:
        """Check if path exists."""
        raise NotImplementedError

    def delete(self, path: str) -> bool:
        """Delete file at path. Returns success status."""
        raise NotImplementedError


class LocalStorage(StorageBackend):
    """Local filesystem storage."""

    def __init__(self, base_dir: str = "runs"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def write(self, path: str, content: str) -> str:
        """Write content to local file."""
        full_path = self.base_dir / path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        return str(full_path)

    def read(self, path: str) -> str:
        """Read content from local file."""
        full_path = self.base_dir / path

        with open(full_path, encoding="utf-8") as f:
            return f.read()

    def list(self, prefix: str = "") -> list[str]:
        """List files in directory."""
        if prefix:
            search_path = self.base_dir / prefix
        else:
            search_path = self.base_dir

        if not search_path.exists():
            return []

        files = []
        for item in search_path.rglob("*"):
            if item.is_file():
                rel_path = item.relative_to(self.base_dir)
                files.append(str(rel_path))

        return sorted(files)

    def exists(self, path: str) -> bool:
        """Check if file exists."""
        full_path = self.base_dir / path
        return full_path.exists()

    def delete(self, path: str) -> bool:
        """Delete local file."""
        try:
            full_path = self.base_dir / path
            full_path.unlink()
            return True
        except FileNotFoundError:
            return False


class S3Storage(StorageBackend):
    """Amazon S3 storage backend."""

    def __init__(self, bucket: str, prefix: str = "runs"):
        if not S3_AVAILABLE:
            raise ImportError("boto3 not installed. Install with: pip install boto3")

        self.bucket = bucket
        self.prefix = prefix
        self.s3 = boto3.client("s3")

    def _get_key(self, path: str) -> str:
        """Get full S3 key with prefix."""
        if self.prefix:
            return f"{self.prefix}/{path}"
        return path

    def write(self, path: str, content: str) -> str:
        """Write content to S3."""
        key = self._get_key(path)

        try:
            self.s3.put_object(
                Bucket=self.bucket, Key=key, Body=content.encode("utf-8"), ContentType="application/json"
            )
            return f"s3://{self.bucket}/{key}"
        except ClientError as e:
            raise RuntimeError(f"Failed to write to S3: {e}")

    def read(self, path: str) -> str:
        """Read content from S3."""
        key = self._get_key(path)

        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read().decode("utf-8")
        except ClientError as e:
            raise FileNotFoundError(f"Object not found in S3: {e}")

    def list(self, prefix: str = "") -> list[str]:
        """List objects in S3 bucket."""
        full_prefix = self._get_key(prefix)

        try:
            paginator = self.s3.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=self.bucket, Prefix=full_prefix)

            files = []
            for page in pages:
                if "Contents" in page:
                    for obj in page["Contents"]:
                        # Strip prefix to get relative path
                        rel_path = obj["Key"]
                        if self.prefix and rel_path.startswith(self.prefix + "/"):
                            rel_path = rel_path[len(self.prefix) + 1 :]
                        files.append(rel_path)

            return sorted(files)
        except ClientError as e:
            raise RuntimeError(f"Failed to list S3 objects: {e}")

    def exists(self, path: str) -> bool:
        """Check if object exists in S3."""
        key = self._get_key(path)

        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    def delete(self, path: str) -> bool:
        """Delete object from S3."""
        key = self._get_key(path)

        try:
            self.s3.delete_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False


class GCSStorage(StorageBackend):
    """Google Cloud Storage backend."""

    def __init__(self, bucket: str, prefix: str = "runs"):
        if not GCS_AVAILABLE:
            raise ImportError("google-cloud-storage not installed. Install with: pip install google-cloud-storage")

        self.bucket_name = bucket
        self.prefix = prefix
        self.client = gcs_storage.Client()
        self.bucket = self.client.bucket(bucket)

    def _get_blob_name(self, path: str) -> str:
        """Get full blob name with prefix."""
        if self.prefix:
            return f"{self.prefix}/{path}"
        return path

    def write(self, path: str, content: str) -> str:
        """Write content to GCS."""
        blob_name = self._get_blob_name(path)
        blob = self.bucket.blob(blob_name)

        try:
            blob.upload_from_string(content, content_type="application/json")
            return f"gs://{self.bucket_name}/{blob_name}"
        except GoogleAPIError as e:
            raise RuntimeError(f"Failed to write to GCS: {e}")

    def read(self, path: str) -> str:
        """Read content from GCS."""
        blob_name = self._get_blob_name(path)
        blob = self.bucket.blob(blob_name)

        try:
            return blob.download_as_text()
        except GoogleAPIError as e:
            raise FileNotFoundError(f"Blob not found in GCS: {e}")

    def list(self, prefix: str = "") -> list[str]:
        """List blobs in GCS bucket."""
        full_prefix = self._get_blob_name(prefix)

        try:
            blobs = self.client.list_blobs(self.bucket_name, prefix=full_prefix)

            files = []
            for blob in blobs:
                # Strip prefix to get relative path
                rel_path = blob.name
                if self.prefix and rel_path.startswith(self.prefix + "/"):
                    rel_path = rel_path[len(self.prefix) + 1 :]
                files.append(rel_path)

            return sorted(files)
        except GoogleAPIError as e:
            raise RuntimeError(f"Failed to list GCS blobs: {e}")

    def exists(self, path: str) -> bool:
        """Check if blob exists in GCS."""
        blob_name = self._get_blob_name(path)
        blob = self.bucket.blob(blob_name)
        return blob.exists()

    def delete(self, path: str) -> bool:
        """Delete blob from GCS."""
        blob_name = self._get_blob_name(path)
        blob = self.bucket.blob(blob_name)

        try:
            blob.delete()
            return True
        except GoogleAPIError:
            return False


def get_storage_backend(runs_dir: Optional[str] = None) -> StorageBackend:
    """
    Create storage backend based on RUNS_DIR configuration.

    Supports:
    - Local: "runs" or "/path/to/runs"
    - S3: "s3://bucket-name/prefix"
    - GCS: "gs://bucket-name/prefix"

    Args:
        runs_dir: Storage location. If None, uses RUNS_DIR env var or defaults to "runs"

    Returns:
        Configured storage backend

    Examples:
        >>> storage = get_storage_backend()  # Uses env var or default
        >>> storage = get_storage_backend("runs")  # Local
        >>> storage = get_storage_backend("s3://my-bucket/djp-runs")  # S3
        >>> storage = get_storage_backend("gs://my-bucket/djp-runs")  # GCS
    """
    if runs_dir is None:
        runs_dir = os.getenv("RUNS_DIR", "runs")

    parsed = urlparse(runs_dir)

    # S3 backend
    if parsed.scheme == "s3":
        bucket = parsed.netloc
        prefix = parsed.path.lstrip("/")
        return S3Storage(bucket=bucket, prefix=prefix)

    # GCS backend
    elif parsed.scheme == "gs":
        bucket = parsed.netloc
        prefix = parsed.path.lstrip("/")
        return GCSStorage(bucket=bucket, prefix=prefix)

    # Local backend (default)
    else:
        return LocalStorage(base_dir=runs_dir)


# Convenience functions for backward compatibility
def save_artifact_content(content: str, filename: str, runs_dir: Optional[str] = None) -> str:
    """
    Save artifact content to configured storage backend.

    Args:
        content: JSON content to save
        filename: Filename (e.g., "2025.10.01-1200.json")
        runs_dir: Storage location override

    Returns:
        Full path/URI where artifact was saved
    """
    storage = get_storage_backend(runs_dir)
    return storage.write(filename, content)


def load_artifact_content(filename: str, runs_dir: Optional[str] = None) -> str:
    """
    Load artifact content from configured storage backend.

    Args:
        filename: Filename to load
        runs_dir: Storage location override

    Returns:
        Artifact content as string
    """
    storage = get_storage_backend(runs_dir)
    return storage.read(filename)


def list_artifact_files(prefix: str = "", runs_dir: Optional[str] = None) -> list[str]:
    """
    List artifact files in configured storage backend.

    Args:
        prefix: Optional prefix filter
        runs_dir: Storage location override

    Returns:
        Sorted list of artifact filenames
    """
    storage = get_storage_backend(runs_dir)
    return storage.list(prefix)
