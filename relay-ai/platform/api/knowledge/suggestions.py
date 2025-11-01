"""
Error suggestion helper for Knowledge API.

Provides actionable guidance text for common error scenarios.
Keeps strings user-friendly (≤120 chars) without exposing internals.
"""

from typing import Optional


def suggestion_for(
    status_code: int,
    error_code: Optional[str] = None,
    retry_after: Optional[int] = None,
) -> Optional[str]:
    """
    Generate actionable suggestion text for error response.

    Args:
        status_code: HTTP status code (401, 429, 500, etc.)
        error_code: Specific error code (RATE_LIMIT_EXCEEDED, INVALID_JWT, etc.)
        retry_after: Retry-After value in seconds (for 429 responses)

    Returns:
        User-friendly suggestion text or None if no suggestion needed
    """
    if status_code == 429:
        # Rate limit exceeded
        wait_time = retry_after or 60
        if wait_time > 60:
            return f"You've hit your rate limit. Wait {wait_time}s or upgrade your plan for higher limits."
        return f"Too many requests. Try again in {wait_time} seconds or upgrade to Pro."

    if status_code == 401:
        # Unauthorized
        return "Your authentication token is invalid or expired. Please sign in again."

    if status_code == 403:
        # Forbidden
        if error_code == "RLS_VIOLATION":
            return "You don't have permission to access this resource."
        if error_code == "AAD_MISMATCH":
            return "File not found or you don't have permission to access it."
        return "You don't have permission to perform this action."

    if status_code == 400:
        # Bad request
        if error_code == "INVALID_MIME_TYPE":
            return "File type not supported. Try PDF, Word, Excel, or text files."
        if error_code == "FILE_TOO_LARGE":
            return "File exceeds 50MB limit. Try a smaller file or split into parts."
        if error_code == "INVALID_TAGS":
            return "Tags must contain only letters, numbers, dashes, and underscores."
        return "Check your request and try again. Contact support if the issue persists."

    if status_code == 422:
        # Unprocessable entity
        return "Invalid request format. Check the required fields and try again."

    if status_code == 413:
        # Payload too large
        return "Request body too large. Try again with fewer files or smaller data."

    if status_code == 500:
        # Internal server error
        return "Something went wrong on our end. We've been notified. Try again shortly."

    if status_code == 503:
        # Service unavailable
        return "Service temporarily unavailable. Try again in a few moments."

    # Generic fallback for other status codes
    return None
