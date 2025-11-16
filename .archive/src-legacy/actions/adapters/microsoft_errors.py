"""Microsoft Graph API error code mapping to structured error taxonomy.

Sprint 55 Week 2: Maps Graph API errors to provider-agnostic structured error codes.

Microsoft Graph API error response format:
{
  "error": {
    "code": "ErrorItemNotFound",
    "message": "The specified object was not found in the store.",
    "innerError": {
      "request-id": "...",
      "date": "..."
    }
  }
}

HTTP status codes:
- 400: Bad Request (invalid parameter)
- 401: Unauthorized (invalid/expired token)
- 403: Forbidden (insufficient permissions)
- 404: Not Found (mailbox not found)
- 409: Conflict (mailbox full, etc.)
- 422: Unprocessable Entity (invalid email format)
- 429: Too Many Requests (throttling)
- 500: Internal Server Error
- 503: Service Unavailable (temporary)
- 504: Gateway Timeout
"""

from typing import Any, Optional


def map_graph_error_to_structured_code(
    status_code: int, error_response: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """Map Microsoft Graph API error to structured error code.

    Args:
        status_code: HTTP status code
        error_response: Graph API error response JSON (optional)

    Returns:
        Structured error dict:
        {
          "code": "error_code_string",
          "message": "Human-readable message",
          "source": "microsoft_graph",
          "retriable": bool,
          "http_status": int,
          "graph_code": "..." (optional, Graph error code),
          "details": {...} (optional, additional context)
        }
    """
    # Extract Graph-specific error code if available
    graph_code = None
    graph_message = None
    if error_response and "error" in error_response:
        error = error_response["error"]
        graph_code = error.get("code")
        graph_message = error.get("message")

    # Map to structured error taxonomy
    if status_code == 400:
        return {
            "code": "provider_payload_invalid",
            "message": graph_message or "Invalid request payload",
            "source": "microsoft_graph",
            "retriable": False,
            "http_status": 400,
            "graph_code": graph_code,
            "details": {"error_response": error_response} if error_response else {},
        }

    elif status_code == 401:
        # Token expired or invalid
        return {
            "code": "oauth_token_invalid",
            "message": "OAuth token expired or invalid",
            "source": "microsoft_graph",
            "retriable": False,  # Requires re-auth
            "http_status": 401,
            "graph_code": graph_code,
            "details": {
                "remediation": "Token refresh should be attempted automatically. If this persists, re-authorize."
            },
        }

    elif status_code == 403:
        # Insufficient permissions or policy block
        if graph_code == "ErrorAccessDenied":
            return {
                "code": "provider_policy_blocked",
                "message": "Access denied - insufficient permissions or policy block",
                "source": "microsoft_graph",
                "retriable": False,
                "http_status": 403,
                "graph_code": graph_code,
                "details": {
                    "remediation": "Check API permissions in Azure AD app registration. Ensure Mail.Send permission is granted."
                },
            }
        return {
            "code": "provider_policy_blocked",
            "message": graph_message or "Forbidden - check permissions",
            "source": "microsoft_graph",
            "retriable": False,
            "http_status": 403,
            "graph_code": graph_code,
        }

    elif status_code == 404:
        # Mailbox or resource not found
        return {
            "code": "provider_not_found",
            "message": graph_message or "Mailbox or resource not found",
            "source": "microsoft_graph",
            "retriable": False,
            "http_status": 404,
            "graph_code": graph_code,
            "details": {"remediation": "Verify user has Exchange Online mailbox. Check recipient addresses."},
        }

    elif status_code == 409:
        # Conflict (mailbox full, etc.)
        return {
            "code": "provider_conflict",
            "message": graph_message or "Conflict - mailbox full or locked",
            "source": "microsoft_graph",
            "retriable": False,
            "http_status": 409,
            "graph_code": graph_code,
        }

    elif status_code == 422:
        # Unprocessable entity (invalid email format, etc.)
        return {
            "code": "provider_payload_invalid",
            "message": graph_message or "Invalid email format or parameters",
            "source": "microsoft_graph",
            "retriable": False,
            "http_status": 422,
            "graph_code": graph_code,
        }

    elif status_code == 429:
        # Rate limiting / throttling
        return {
            "code": "throttled_429",
            "message": "Rate limit exceeded - retry with exponential backoff",
            "source": "microsoft_graph",
            "retriable": True,
            "http_status": 429,
            "graph_code": graph_code,
            "details": {"remediation": "Automatic retry with exponential backoff. Check Retry-After header."},
        }

    elif status_code >= 500 and status_code < 600:
        # Server errors (5xx)
        return {
            "code": "provider_unavailable",
            "message": graph_message or f"Microsoft Graph API unavailable (HTTP {status_code})",
            "source": "microsoft_graph",
            "retriable": True,
            "http_status": status_code,
            "graph_code": graph_code,
            "details": {"remediation": "Temporary service issue. Automatic retry recommended."},
        }

    else:
        # Unknown error
        return {
            "code": "provider_unknown_error",
            "message": graph_message or f"Unknown error (HTTP {status_code})",
            "source": "microsoft_graph",
            "retriable": False,
            "http_status": status_code,
            "graph_code": graph_code,
            "details": {"error_response": error_response} if error_response else {},
        }


def parse_retry_after(retry_after_header: Optional[str]) -> int:
    """Parse Retry-After header value (seconds or HTTP date).

    Args:
        retry_after_header: Value of Retry-After header

    Returns:
        Retry delay in seconds (defaults to 60 if invalid)
    """
    if not retry_after_header:
        return 60  # Default 60 seconds

    # Try parsing as integer (seconds)
    try:
        return max(1, int(retry_after_header))
    except ValueError:
        pass

    # Try parsing as HTTP date (RFC 1123)
    try:
        import datetime
        from email.utils import parsedate_to_datetime

        retry_date = parsedate_to_datetime(retry_after_header)
        now = datetime.datetime.now(datetime.timezone.utc)
        delta = (retry_date - now).total_seconds()
        return max(1, int(delta))
    except Exception:
        pass

    # Fallback: 60 seconds
    return 60


# Common Graph API error codes (for reference)
GRAPH_ERROR_CODES = {
    # Authentication / Authorization
    "InvalidAuthenticationToken": "oauth_token_invalid",
    "ExpiredAuthenticationToken": "oauth_token_invalid",
    "CompactTokenParsingFailure": "oauth_token_invalid",
    "ErrorAccessDenied": "provider_policy_blocked",
    "ErrorInsufficientPermissionsInAccessToken": "provider_policy_blocked",
    # Resource not found
    "ErrorItemNotFound": "provider_not_found",
    "ErrorMailboxNotFound": "provider_not_found",
    "ResourceNotFound": "provider_not_found",
    # Invalid request
    "ErrorInvalidRequest": "provider_payload_invalid",
    "ErrorInvalidRecipients": "provider_payload_invalid",
    "ErrorMessageSizeExceeded": "provider_payload_invalid",
    "RequestBodyRead": "provider_payload_invalid",
    # Throttling
    "ErrorServerBusy": "throttled_429",
    "ErrorTimeoutExpired": "throttled_429",
    "TooManyRequests": "throttled_429",
    # Server errors
    "ErrorInternalServerError": "provider_unavailable",
    "ErrorInternalServerTransientError": "provider_unavailable",
    "ServiceUnavailable": "provider_unavailable",
    # Conflict
    "ErrorMailboxStoreUnavailable": "provider_conflict",
    "ErrorQuotaExceeded": "provider_conflict",
    # Sprint 55 Week 3: Upload session errors
    "ErrorAttachmentSizeLimitExceeded": "provider_payload_too_large",
    "ErrorInvalidUploadSession": "provider_upload_session_invalid",
    "ErrorUploadSessionNotFound": "provider_upload_session_not_found",
}


# Sprint 55 Week 3: Upload session error mapping
def map_upload_session_error(status_code: int, error_response: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Map upload session errors to structured error codes.

    Args:
        status_code: HTTP status code
        error_response: Graph API error response JSON (optional)

    Returns:
        Structured error dict with upload session context
    """
    # Delegate to existing error mapper
    base_error = map_graph_error_to_structured_code(status_code, error_response)

    # Add upload session context
    base_error["source"] = "microsoft_upload_session"
    base_error["details"] = base_error.get("details", {})
    base_error["details"]["upload_session"] = True

    return base_error
