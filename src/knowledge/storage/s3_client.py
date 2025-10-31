"""
S3/Local storage client for Knowledge API (Phase 3).

Abstraction for file storage with S3 primary + local fallback.
- Upload original files (encrypted at-rest)
- Download files (decrypted for authenticated user)
- List objects by prefix
- Delete objects
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Phase 3 TODO: Initialize boto3 S3 client or local filesystem
STORAGE_TYPE = os.getenv("STORAGE_TYPE", "local")  # "s3" or "local"
STORAGE_BUCKET = os.getenv("STORAGE_BUCKET", "./storage/knowledge")


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
    # Phase 3 TODO: Implement S3 upload with encryption
    # s3_key = f"knowledge/{user_hash}/{file_id}"
    # s3_client.put_object(
    #     Bucket=STORAGE_BUCKET,
    #     Key=s3_key,
    #     Body=file_bytes,
    #     ContentType=content_type,
    #     Metadata={"user_hash": user_hash, "file_id": file_id},
    #     ServerSideEncryption="AES256",
    # )

    logger.debug(f"[Phase 3] Upload file {file_id} for user {user_hash[:8]}...")
    return f"s3://{STORAGE_BUCKET}/knowledge/{user_hash}/{file_id}"


async def download_file(
    file_id: str,
    user_hash: str,
) -> Optional[bytes]:
    """
    Download file from storage.

    Returns: Decrypted file bytes or None if not found
    """
    # Phase 3 TODO: Implement S3 download with RLS check
    # s3_key = f"knowledge/{user_hash}/{file_id}"
    # try:
    #     response = s3_client.get_object(Bucket=STORAGE_BUCKET, Key=s3_key)
    #     file_bytes = response["Body"].read()
    #     return file_bytes
    # except s3_client.exceptions.NoSuchKey:
    #     return None

    logger.debug(f"[Phase 3] Download file {file_id} for user {user_hash[:8]}...")
    return None


async def delete_file(
    file_id: str,
    user_hash: str,
) -> bool:
    """
    Delete file from storage.

    Returns: True if deleted, False if not found
    """
    # Phase 3 TODO: Implement S3 delete with RLS check
    # s3_key = f"knowledge/{user_hash}/{file_id}"
    # try:
    #     s3_client.delete_object(Bucket=STORAGE_BUCKET, Key=s3_key)
    #     return True
    # except Exception:
    #     return False

    logger.debug(f"[Phase 3] Delete file {file_id} for user {user_hash[:8]}...")
    return True


async def list_files(
    user_hash: str,
    prefix: str = "",
) -> list[str]:
    """
    List files by prefix (user isolation).

    Returns: List of file IDs
    """
    # Phase 3 TODO: Implement S3 list with RLS filter
    # response = s3_client.list_objects_v2(
    #     Bucket=STORAGE_BUCKET,
    #     Prefix=f"knowledge/{user_hash}/{prefix}",
    # )
    # return [obj["Key"] for obj in response.get("Contents", [])]

    logger.debug(f"[Phase 3] List files for user {user_hash[:8]}...")
    return []
