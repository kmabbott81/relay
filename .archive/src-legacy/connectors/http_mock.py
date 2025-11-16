"""Mock HTTP transport for deterministic testing.

Provides scripted HTTP responses for testing connector resilience patterns
without making real API calls.
"""

import os
from collections.abc import Iterator
from typing import Optional
from urllib.parse import urlparse


class MockHTTPTransport:
    """Mock HTTP transport with scripted responses.

    Supports scripting responses by (method, endpoint) key with configurable
    status codes, bodies, headers, and optional latency tracking.

    Example:
        mock = MockHTTPTransport()
        mock.script("GET", "conversations.list", [
            {"status_code": 429, "body": {"ok": False, "error": "rate_limited"}},
            {"status_code": 200, "body": {"ok": True, "channels": []}}
        ])
        response = mock.request("GET", "https://slack.com/api/conversations.list")
    """

    def __init__(self):
        """Initialize mock transport."""
        self._scripts: dict[tuple[str, str], Iterator] = {}
        self._call_history: list[dict] = []
        self._default_response = {"status_code": 200, "body": {"ok": True}, "headers": {}}

    def script(self, method: str, endpoint: str, responses: list[dict]):
        """Script responses for a specific (method, endpoint) pair.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (e.g., "conversations.list")
            responses: List of response dicts with status_code, body, headers, latency_ms
        """
        key = (method.upper(), endpoint)
        # Store both iterator and last response for repeating
        self._scripts[key] = {"iterator": iter(responses), "last": None, "exhausted": False}

    def request(
        self,
        method: str,
        url: str,
        headers: Optional[dict] = None,
        json_data: Optional[dict] = None,
        timeout: int = 30,
    ) -> dict:
        """Make mocked HTTP request.

        Args:
            method: HTTP method
            url: Full URL
            headers: Request headers
            json_data: JSON body
            timeout: Timeout (ignored in mock)

        Returns:
            dict with status_code, headers, body
        """
        # Extract endpoint from URL
        parsed = urlparse(url)
        path_parts = parsed.path.strip("/").split("/")
        # For Slack: /api/conversations.list -> conversations.list
        endpoint = path_parts[-1] if path_parts else ""

        # Record call
        call_record = {
            "method": method.upper(),
            "url": url,
            "endpoint": endpoint,
            "headers": headers or {},
            "json_data": json_data,
        }
        self._call_history.append(call_record)

        # Find matching script
        key = (method.upper(), endpoint)

        if key in self._scripts:
            script_data = self._scripts[key]

            # Try to get next response from iterator
            if not script_data["exhausted"]:
                try:
                    response = next(script_data["iterator"])
                    script_data["last"] = response

                    # Build response dict
                    result = {
                        "status_code": response.get("status_code", 200),
                        "body": response.get("body", {}),
                        "headers": response.get("headers", {}),
                    }

                    # Optional: record latency for metrics (don't sleep)
                    if "latency_ms" in response:
                        result["_mock_latency_ms"] = response["latency_ms"]

                    return result

                except StopIteration:
                    # Iterator exhausted, mark and fall through to repeat last
                    script_data["exhausted"] = True

            # Repeat last response if iterator exhausted
            if script_data["last"] is not None:
                response = script_data["last"]
                result = {
                    "status_code": response.get("status_code", 200),
                    "body": response.get("body", {}),
                    "headers": response.get("headers", {}),
                }

                if "latency_ms" in response:
                    result["_mock_latency_ms"] = response["latency_ms"]

                return result

        # No script found, return default success
        return self._default_response.copy()

    def get_call_count(self, method: Optional[str] = None, endpoint: Optional[str] = None) -> int:
        """Get number of calls made.

        Args:
            method: Filter by method (optional)
            endpoint: Filter by endpoint (optional)

        Returns:
            Number of matching calls
        """
        if method is None and endpoint is None:
            return len(self._call_history)

        count = 0
        for call in self._call_history:
            if method and call["method"] != method.upper():
                continue
            if endpoint and call["endpoint"] != endpoint:
                continue
            count += 1

        return count

    def get_call_history(self) -> list[dict]:
        """Get full call history.

        Returns:
            List of call records
        """
        return self._call_history.copy()

    def reset(self):
        """Reset all scripts and call history."""
        self._scripts.clear()
        self._call_history.clear()


# Singleton instance for use in tests
_mock_transport_instance: Optional[MockHTTPTransport] = None


def get_mock_transport() -> MockHTTPTransport:
    """Get singleton mock transport instance.

    Returns:
        MockHTTPTransport instance
    """
    global _mock_transport_instance
    if _mock_transport_instance is None:
        _mock_transport_instance = MockHTTPTransport()
    return _mock_transport_instance


def reset_mock_transport():
    """Reset singleton mock transport."""
    global _mock_transport_instance
    if _mock_transport_instance:
        _mock_transport_instance.reset()


def is_mock_enabled() -> bool:
    """Check if mock HTTP transport is enabled.

    Returns:
        True if SLACK_USE_HTTP_MOCK=true
    """
    return os.getenv("SLACK_USE_HTTP_MOCK", "false").lower() == "true"
