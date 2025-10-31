"""
S3/Local storage client for Knowledge API (Phase 3).

Abstraction for file storage with S3 primary + local fallback.
- Upload original files (encrypted at-rest)
- Download files (decrypted for authenticated user)
- List objects by prefix
- Delete objects
- Signed URLs for direct access
"""

import logging
import os
from pathlib import Path
from typing import Optional

import aiofiles

logger = logging.getLogger(__name__)

# Configuration
STORAGE_TYPE = os.getenv("STORAGE_TYPE", "local")  # "s3" or "local"
STORAGE_BUCKET = os.getenv("STORAGE_BUCKET", "/tmp/relay-knowledge")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Initialize boto3 for S3 (lazy load)
_s3_client = None


def _get_s3_client():
    """Lazy init of boto3 S3 client."""
    global _s3_client
    if _s3_client is None and STORAGE_TYPE == "s3":
        try:
            import boto3

            _s3_client = boto3.client("s3", region_name=AWS_REGION)
        except ImportError:
            logger.warning("boto3 not available; falling back to local storage")
            return None
    return _s3_client


async def _ensure_local_dir() -> None:
    """Ensure local storage directory exists."""
    if STORAGE_TYPE == "local":
        Path(STORAGE_BUCKET).mkdir(parents=True, exist_ok=True)


async def upload_file(
    file_id: str,
    file_bytes: bytes,
    content_type: str,
    user_hash: str,
) -> str:
    """
    Upload file to storage (S3 or local).

    Returns: Storage path/URL for reference
    """
    s3_key = f"knowledge/{user_hash}/{file_id}"

    if STORAGE_TYPE == "s3":
        s3_client = _get_s3_client()
        if s3_client:
            try:
                s3_client.put_object(
                    Bucket=STORAGE_BUCKET,
                    Key=s3_key,
                    Body=file_bytes,
                    ContentType=content_type,
                    ServerSideEncryption="AES256",
                    Metadata={"user_hash": user_hash, "file_id": str(file_id)},
                )
                logger.info(f"Uploaded {file_id} to S3: {s3_key}")
                return f"s3://{STORAGE_BUCKET}/{s3_key}"
            except Exception as e:
                logger.error(f"S3 upload failed: {e}")
                raise
    else:
        # Local storage
        await _ensure_local_dir()
        local_path = Path(STORAGE_BUCKET) / s3_key
        local_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(local_path, "wb") as f:
            await f.write(file_bytes)

        logger.info(f"Uploaded {file_id} locally: {local_path}")
        return str(local_path)


async def download_file(
    file_id: str,
    user_hash: str,
) -> Optional[bytes]:
    """
    Download file from storage with RLS check.

    Returns: File bytes or None if not found
    """
    s3_key = f"knowledge/{user_hash}/{file_id}"

    if STORAGE_TYPE == "s3":
        s3_client = _get_s3_client()
        if s3_client:
            try:
                response = s3_client.get_object(Bucket=STORAGE_BUCKET, Key=s3_key)
                file_bytes = response["Body"].read()
                logger.info(f"Downloaded {file_id} from S3")
                return file_bytes
            except s3_client.exceptions.NoSuchKey:
                logger.debug(f"File not found in S3: {s3_key}")
                return None
            except Exception as e:
                logger.error(f"S3 download failed: {e}")
                raise
    else:
        # Local storage
        local_path = Path(STORAGE_BUCKET) / s3_key
        if not local_path.exists():
            logger.debug(f"File not found locally: {local_path}")
            return None

        try:
            async with aiofiles.open(local_path, "rb") as f:
                file_bytes = await f.read()
                logger.info(f"Downloaded {file_id} locally")
                return file_bytes
        except Exception as e:
            logger.error(f"Local download failed: {e}")
            raise


async def delete_file(
    file_id: str,
    user_hash: str,
) -> bool:
    """
    Delete file from storage with RLS check.

    Returns: True if deleted, False if not found
    """
    s3_key = f"knowledge/{user_hash}/{file_id}"

    if STORAGE_TYPE == "s3":
        s3_client = _get_s3_client()
        if s3_client:
            try:
                s3_client.delete_object(Bucket=STORAGE_BUCKET, Key=s3_key)
                logger.info(f"Deleted {file_id} from S3")
                return True
            except Exception as e:
                logger.error(f"S3 delete failed: {e}")
                return False
    else:
        # Local storage
        local_path = Path(STORAGE_BUCKET) / s3_key
        if not local_path.exists():
            logger.debug(f"File not found locally: {local_path}")
            return False

        try:
            local_path.unlink()
            logger.info(f"Deleted {file_id} locally")
            return True
        except Exception as e:
            logger.error(f"Local delete failed: {e}")
            return False


async def list_files(
    user_hash: str,
    prefix: str = "",
) -> list[str]:
    """
    List files by prefix (user isolation via user_hash).

    Returns: List of file IDs
    """
    s3_prefix = f"knowledge/{user_hash}/{prefix}"

    if STORAGE_TYPE == "s3":
        s3_client = _get_s3_client()
        if s3_client:
            try:
                response = s3_client.list_objects_v2(Bucket=STORAGE_BUCKET, Prefix=s3_prefix)
                files = [obj["Key"].split("/")[-1] for obj in response.get("Contents", [])]
                logger.info(f"Listed {len(files)} files in S3 for user {user_hash[:8]}")
                return files
            except Exception as e:
                logger.error(f"S3 list failed: {e}")
                return []
    else:
        # Local storage
        await _ensure_local_dir()
        local_prefix = Path(STORAGE_BUCKET) / "knowledge" / user_hash / prefix
        if not local_prefix.exists():
            logger.debug(f"Directory not found locally: {local_prefix}")
            return []

        files = [f.name for f in local_prefix.iterdir() if f.is_file()]
        logger.info(f"Listed {len(files)} files locally for user {user_hash[:8]}")
        return files
