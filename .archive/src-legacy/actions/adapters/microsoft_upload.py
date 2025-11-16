"""Microsoft Graph API resumable upload sessions for large attachments.

Sprint 55 Week 3: Handles attachments >3 MB using Graph API's draft + upload session pattern.

Microsoft Graph Upload Flow:
1. Create draft message (POST /me/messages)
2. Create upload session for each large attachment (POST /me/messages/{id}/attachments/createUploadSession)
3. Upload chunks with Content-Range (PUT {uploadUrl})
4. Send draft (POST /me/messages/{id}/send)

Chunk Size Requirements:
- Must be multiple of 320 KiB per Graph API spec
- Default: 4 MiB (optimal for most networks)
- Max file size: 150 MB per attachment

Retry Logic:
- 429 throttling: respect Retry-After header + jitter
- 5xx errors: exponential backoff with jitter
- Max 3 retries per chunk
"""

import asyncio
import os
import random
import time
from typing import Any, Optional

import httpx

# Feature flags
MS_UPLOAD_SESSIONS_ENABLED = os.getenv("MS_UPLOAD_SESSIONS_ENABLED", "false").lower() == "true"
MS_UPLOAD_SESSION_THRESHOLD_BYTES = int(os.getenv("MS_UPLOAD_SESSION_THRESHOLD_BYTES", str(3 * 1024 * 1024)))
MS_UPLOAD_CHUNK_SIZE_BYTES = int(os.getenv("MS_UPLOAD_CHUNK_SIZE_BYTES", str(4 * 1024 * 1024)))

# Validate chunk size is 320 KiB multiple (only if not default)
CHUNK_SIZE_MULTIPLE = 320 * 1024
_custom_chunk_size = os.getenv("MS_UPLOAD_CHUNK_SIZE_BYTES")
if _custom_chunk_size and MS_UPLOAD_CHUNK_SIZE_BYTES % CHUNK_SIZE_MULTIPLE != 0:
    raise ValueError(f"MS_UPLOAD_CHUNK_SIZE_BYTES must be multiple of 320 KiB, got {MS_UPLOAD_CHUNK_SIZE_BYTES}")


class UploadSessionError(Exception):
    """Base exception for upload session errors."""

    pass


class UploadSessionCreateError(UploadSessionError):
    """Failed to create upload session."""

    pass


class UploadChunkError(UploadSessionError):
    """Failed to upload chunk."""

    pass


class UploadFinalizeError(UploadSessionError):
    """Failed to finalize upload."""

    pass


async def create_draft(access_token: str, message_json: dict[str, Any]) -> tuple[str, Optional[str]]:
    """Create a draft message in Outlook.

    Args:
        access_token: OAuth access token
        message_json: Message JSON (same format as sendMail message, without attachments)

    Returns:
        Tuple of (message_id, internet_message_id)

    Raises:
        UploadSessionCreateError: If draft creation fails
        httpx.HTTPStatusError: If Graph API returns error

    Metrics emitted:
        - outlook_draft_created_total{result="success|error"}
        - outlook_draft_create_seconds
    """
    from relay_ai.telemetry.prom import (
        outlook_draft_create_seconds,
        outlook_draft_created_total,
    )

    start_time = time.perf_counter()

    try:
        url = "https://graph.microsoft.com/v1.0/me/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=message_json, headers=headers)

            if response.status_code == 201:
                # Success: draft created
                data = response.json()
                message_id = data.get("id")
                internet_message_id = data.get("internetMessageId")

                if not message_id:
                    raise UploadSessionCreateError("Draft created but missing 'id' field")

                # Emit metrics
                duration = time.perf_counter() - start_time
                if outlook_draft_created_total:
                    outlook_draft_created_total.labels(result="success").inc()
                if outlook_draft_create_seconds:
                    outlook_draft_create_seconds.observe(duration)

                return (message_id, internet_message_id)

            else:
                # Error response
                if outlook_draft_created_total:
                    outlook_draft_created_total.labels(result="error").inc()

                error_body = response.json() if response.content else {}
                raise UploadSessionCreateError(f"Failed to create draft: {response.status_code} - {error_body}")

    except httpx.RequestError as e:
        if outlook_draft_created_total:
            outlook_draft_created_total.labels(result="error").inc()
        raise UploadSessionCreateError(f"Failed to create draft: {e}") from e


async def create_upload_session(access_token: str, message_id: str, attachment_meta: dict[str, Any]) -> str:
    """Create an upload session for a large attachment.

    Args:
        access_token: OAuth access token
        message_id: Draft message ID from create_draft()
        attachment_meta: Attachment metadata with keys:
            - attachmentType: "file"
            - name: filename
            - size: file size in bytes

    Returns:
        Upload URL for PUT chunks

    Raises:
        UploadSessionCreateError: If session creation fails
        httpx.HTTPStatusError: If Graph API returns error

    Metrics emitted:
        - outlook_upload_session_total{result="started|error"}
        - outlook_upload_session_create_seconds
    """
    from relay_ai.telemetry.prom import (
        outlook_upload_session_create_seconds,
        outlook_upload_session_total,
    )

    start_time = time.perf_counter()

    try:
        url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/attachments/createUploadSession"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        payload = {"AttachmentItem": attachment_meta}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)

            if response.status_code == 201:
                # Success: upload session created
                data = response.json()
                upload_url = data.get("uploadUrl")

                if not upload_url:
                    raise UploadSessionCreateError("Upload session created but missing 'uploadUrl' field")

                # Emit metrics
                duration = time.perf_counter() - start_time
                if outlook_upload_session_total:
                    outlook_upload_session_total.labels(result="started").inc()
                if outlook_upload_session_create_seconds:
                    outlook_upload_session_create_seconds.observe(duration)

                return upload_url

            else:
                # Error response
                if outlook_upload_session_total:
                    outlook_upload_session_total.labels(result="error").inc()

                error_body = response.json() if response.content else {}
                raise UploadSessionCreateError(
                    f"Failed to create upload session: {response.status_code} - {error_body}"
                )

    except httpx.RequestError as e:
        if outlook_upload_session_total:
            outlook_upload_session_total.labels(result="error").inc()
        raise UploadSessionCreateError(f"Failed to create upload session: {e}") from e


async def put_chunks(
    upload_url: str, file_bytes: bytes, chunk_size: int = MS_UPLOAD_CHUNK_SIZE_BYTES
) -> dict[str, Any]:
    """Upload file in chunks with retry logic.

    Args:
        upload_url: Upload URL from create_upload_session()
        file_bytes: File data to upload
        chunk_size: Chunk size in bytes (must be 320 KiB multiple, default 4 MiB)

    Returns:
        Final response data with attachment ID

    Raises:
        UploadChunkError: If chunk upload fails after retries
        ValueError: If chunk size not 320 KiB multiple
        httpx.HTTPStatusError: If Graph API returns error

    Metrics emitted:
        - outlook_upload_chunk_seconds
        - outlook_upload_bytes_total{result="completed|failed"}
        - outlook_upload_session_total{result="completed|failed"}
    """
    from relay_ai.actions.adapters.microsoft_errors import parse_retry_after
    from relay_ai.telemetry.prom import (
        outlook_upload_bytes_total,
        outlook_upload_chunk_seconds,
        outlook_upload_session_total,
    )

    # Validate chunk size
    if chunk_size % CHUNK_SIZE_MULTIPLE != 0:
        raise ValueError(f"Chunk size must be multiple of 320 KiB, got {chunk_size}")

    file_size = len(file_bytes)
    num_chunks = (file_size + chunk_size - 1) // chunk_size

    # Retry parameters
    max_retries = 3
    base_delay = 1.0

    # Upload each chunk
    for chunk_idx in range(num_chunks):
        start_byte = chunk_idx * chunk_size
        end_byte = min(start_byte + chunk_size, file_size)
        chunk_data = file_bytes[start_byte:end_byte]

        chunk_start_time = time.perf_counter()

        # Retry loop for this chunk
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                headers = {
                    "Content-Length": str(len(chunk_data)),
                    "Content-Range": f"bytes {start_byte}-{end_byte - 1}/{file_size}",
                }

                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.put(upload_url, content=chunk_data, headers=headers)

                    if response.status_code in (200, 201, 202):
                        # Chunk uploaded successfully
                        data = response.json() if response.content else {}

                        # Emit chunk timing
                        chunk_duration = time.perf_counter() - chunk_start_time
                        if outlook_upload_chunk_seconds:
                            outlook_upload_chunk_seconds.observe(chunk_duration)

                        # Check if this was the last chunk (response contains attachment ID)
                        if "id" in data:
                            # Upload completed
                            if outlook_upload_bytes_total:
                                outlook_upload_bytes_total.labels(result="completed").inc(file_size)
                            if outlook_upload_session_total:
                                outlook_upload_session_total.labels(result="completed").inc()

                            return data

                        # Not the last chunk, continue to next chunk
                        break  # Exit retry loop for this chunk

                    elif response.status_code == 429:
                        # Rate limiting - parse Retry-After header
                        retry_after = parse_retry_after(response.headers.get("Retry-After"))

                        from relay_ai.telemetry.prom import record_structured_error

                        record_structured_error(
                            provider="microsoft",
                            action="outlook.upload_chunk",
                            code="throttled_429",
                            source="upload_session",
                        )

                        if attempt < max_retries:
                            # Add jitter (±20%)
                            jitter = random.uniform(0.8, 1.2)
                            delay = retry_after * jitter
                            await asyncio.sleep(delay)
                            continue  # Retry
                        else:
                            # Max retries exceeded
                            last_error = UploadChunkError(
                                f"Chunk {chunk_idx + 1}/{num_chunks} throttled after {max_retries} retries"
                            )
                            break

                    elif 500 <= response.status_code < 600:
                        # Server error - exponential backoff
                        from relay_ai.telemetry.prom import record_structured_error

                        record_structured_error(
                            provider="microsoft",
                            action="outlook.upload_chunk",
                            code=f"graph_5xx_{response.status_code}",
                            source="upload_session",
                        )

                        if attempt < max_retries:
                            # Exponential backoff with jitter
                            delay = (base_delay * (2**attempt)) * random.uniform(0.8, 1.2)
                            await asyncio.sleep(delay)
                            continue  # Retry
                        else:
                            # Max retries exceeded
                            error_body = response.json() if response.content else {}
                            last_error = UploadChunkError(
                                f"Chunk {chunk_idx + 1}/{num_chunks} failed with 5xx after {max_retries} retries: {response.status_code} - {error_body}"
                            )
                            break

                    else:
                        # Non-retriable error (4xx except 429)
                        error_body = response.json() if response.content else {}
                        last_error = UploadChunkError(
                            f"Chunk {chunk_idx + 1}/{num_chunks} failed: {response.status_code} - {error_body}"
                        )
                        break

            except httpx.TimeoutException as e:
                last_error = e

                if attempt < max_retries:
                    # Exponential backoff
                    delay = (base_delay * (2**attempt)) * random.uniform(0.8, 1.2)
                    await asyncio.sleep(delay)
                    continue  # Retry
                else:
                    last_error = UploadChunkError(
                        f"Chunk {chunk_idx + 1}/{num_chunks} timeout after {max_retries} retries: {e}"
                    )
                    break

            except httpx.RequestError as e:
                last_error = e

                if attempt < max_retries:
                    # Exponential backoff
                    delay = (base_delay * (2**attempt)) * random.uniform(0.8, 1.2)
                    await asyncio.sleep(delay)
                    continue  # Retry
                else:
                    last_error = UploadChunkError(
                        f"Chunk {chunk_idx + 1}/{num_chunks} request error after {max_retries} retries: {e}"
                    )
                    break

        # If we exited retry loop with an error, abort upload
        if last_error:
            if outlook_upload_bytes_total:
                outlook_upload_bytes_total.labels(result="failed").inc(file_size)
            if outlook_upload_session_total:
                outlook_upload_session_total.labels(result="failed").inc()

            raise last_error

    # Should never reach here if chunks uploaded successfully
    raise UploadChunkError("Upload completed but no attachment ID returned")


async def send_draft(access_token: str, message_id: str) -> None:
    """Send a draft message.

    Args:
        access_token: OAuth access token
        message_id: Draft message ID from create_draft()

    Raises:
        UploadFinalizeError: If send fails
        httpx.HTTPStatusError: If Graph API returns error

    Metrics emitted:
        - outlook_draft_sent_total{result="success|error"}
        - outlook_draft_send_seconds
    """
    from relay_ai.telemetry.prom import (
        outlook_draft_send_seconds,
        outlook_draft_sent_total,
    )

    start_time = time.perf_counter()

    try:
        url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/send"
        headers = {
            "Authorization": f"Bearer {access_token}",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers)

            if response.status_code == 202:
                # Success: draft sent
                duration = time.perf_counter() - start_time
                if outlook_draft_sent_total:
                    outlook_draft_sent_total.labels(result="success").inc()
                if outlook_draft_send_seconds:
                    outlook_draft_send_seconds.observe(duration)

                return

            else:
                # Error response
                if outlook_draft_sent_total:
                    outlook_draft_sent_total.labels(result="error").inc()

                error_body = response.json() if response.content else {}
                raise UploadFinalizeError(f"Failed to send draft: {response.status_code} - {error_body}")

    except httpx.RequestError as e:
        if outlook_draft_sent_total:
            outlook_draft_sent_total.labels(result="error").inc()
        raise UploadFinalizeError(f"Failed to send draft: {e}") from e
