"""Minimal HTTP client for connector operations.

Uses requests if available, falls back to urllib.request.
"""

import json
from typing import Optional


def request(
    method: str,
    url: str,
    headers: Optional[dict] = None,
    json_data: Optional[dict] = None,
    timeout: int = 30,
) -> dict:
    """Make HTTP request with retry-friendly interface.

    Args:
        method: HTTP method (GET, POST, PATCH, DELETE)
        url: Full URL
        headers: Request headers
        json_data: JSON body (for POST/PATCH)
        timeout: Timeout in seconds

    Returns:
        dict with status_code, headers, body (parsed JSON or text)

    Raises:
        Exception on network/HTTP errors
    """
    headers = headers or {}

    try:
        # Try requests library first
        import requests

        if json_data:
            headers["Content-Type"] = "application/json"

        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=json_data,
            timeout=timeout,
        )

        # Parse body
        try:
            body = response.json()
        except ValueError:
            body = response.text

        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": body,
        }

    except ImportError:
        # Fallback to urllib
        import urllib.request
        from urllib.error import HTTPError, URLError

        # Prepare request
        if json_data:
            headers["Content-Type"] = "application/json"
            data = json.dumps(json_data).encode("utf-8")
        else:
            data = None

        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body_bytes = response.read()
                body_text = body_bytes.decode("utf-8")

                # Try to parse as JSON
                try:
                    body = json.loads(body_text)
                except json.JSONDecodeError:
                    body = body_text

                return {
                    "status_code": response.status,
                    "headers": dict(response.headers),
                    "body": body,
                }

        except HTTPError as e:
            # Parse error body
            try:
                error_body = json.loads(e.read().decode("utf-8"))
            except (ValueError, AttributeError):
                error_body = str(e)

            return {
                "status_code": e.code,
                "headers": dict(e.headers) if hasattr(e, "headers") else {},
                "body": error_body,
            }

        except URLError as e:
            raise Exception(f"Network error: {e}") from e
