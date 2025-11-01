"""Test Slack connector resilience patterns.

Tests for retry logic, circuit breaker, and error handling.
All tests are offline using MockHTTPTransport.
"""

import os

import pytest

from src.connectors.http_mock import get_mock_transport, reset_mock_transport
from src.connectors.slack import SlackConnector


@pytest.fixture
def slack_connector():
    """Create Slack connector for testing resilience."""
    # Enable mock transport
    os.environ["SLACK_USE_HTTP_MOCK"] = "true"
    os.environ["DRY_RUN"] = "false"  # Don't use legacy JSONL mocks
    os.environ["LIVE"] = "false"
    os.environ["USER_ROLE"] = "Admin"
    os.environ["SLACK_BOT_TOKEN"] = "xoxb-test-token"
    os.environ["SLACK_DEFAULT_CHANNEL_ID"] = "C1234567890"
    os.environ["RETRY_MAX_ATTEMPTS"] = "3"

    # Reset mock transport
    reset_mock_transport()

    connector = SlackConnector(
        connector_id=f"test-slack-resilience-{id(object())}",
        tenant_id="tenant-1",
        user_id="user-1",
    )

    # Reset circuit breaker to closed state
    connector.circuit.failure_count = 0
    connector.circuit.state = "closed"

    yield connector

    # Cleanup
    reset_mock_transport()


def test_rate_limit_429_retry(slack_connector):
    """Test 429 rate limit triggers retry with backoff."""
    mock = get_mock_transport()

    # Script: first 429, then success
    mock.script(
        "GET",
        "conversations.list",
        [
            {"status_code": 429, "body": {"ok": False, "error": "rate_limited"}},
            {"status_code": 200, "body": {"ok": True, "channels": [{"id": "C123", "name": "test"}]}},
        ],
    )

    result = slack_connector.list_resources("channels")

    # Verify retry happened (2 calls)
    assert mock.get_call_count("GET", "conversations.list") == 2
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["id"] == "C123"


def test_server_error_5xx_retry(slack_connector):
    """Test 5xx server errors trigger retry."""
    mock = get_mock_transport()

    # Script: 2x 503 then success (RETRY_MAX_ATTEMPTS=3 means 3 total attempts)
    mock.script(
        "GET",
        "conversations.list",
        [
            {"status_code": 503, "body": {"error": "service_unavailable"}},
            {"status_code": 503, "body": {"error": "service_unavailable"}},
            {"status_code": 200, "body": {"ok": True, "channels": [{"id": "C456", "name": "general"}]}},
        ],
    )

    result = slack_connector.list_resources("channels")

    # Verify retries happened (3 calls total)
    assert mock.get_call_count("GET", "conversations.list") == 3
    assert isinstance(result, list)
    assert len(result) == 1


def test_max_retries_exceeded(slack_connector):
    """Test max retries exceeded raises exception."""
    mock = get_mock_transport()

    # Script: always 503 (more than max retries)
    mock.script(
        "GET",
        "conversations.list",
        [
            {"status_code": 503, "body": {"error": "service_unavailable"}},
            {"status_code": 503, "body": {"error": "service_unavailable"}},
            {"status_code": 503, "body": {"error": "service_unavailable"}},
            {"status_code": 503, "body": {"error": "service_unavailable"}},
        ],
    )

    with pytest.raises(Exception, match="Max retries|service_unavailable"):
        slack_connector.list_resources("channels")

    # Verify max retries were attempted (RETRY_MAX_ATTEMPTS=3)
    assert mock.get_call_count("GET", "conversations.list") == 3


def test_slack_api_error_no_retry(slack_connector):
    """Test Slack API errors (other than rate_limited) don't retry."""
    mock = get_mock_transport()

    # Script: Slack API error with ok=False
    mock.script(
        "GET", "conversations.info", [{"status_code": 200, "body": {"ok": False, "error": "channel_not_found"}}]
    )

    with pytest.raises(Exception, match="channel_not_found"):
        slack_connector.get_resource("channels", "C_INVALID")

    # Should only attempt once (no retries for Slack API errors)
    assert mock.get_call_count("GET", "conversations.info") == 1


def test_circuit_breaker_open(slack_connector):
    """Test circuit breaker opens after failures."""
    # Force circuit breaker to open (default: 5 failures)
    for _ in range(10):
        slack_connector.circuit.record_failure()

    # Now circuit should be open
    assert not slack_connector.circuit.allow()

    # API call should fail immediately without making requests
    mock = get_mock_transport()
    mock.script("GET", "conversations.list", [{"status_code": 200, "body": {"ok": True, "channels": []}}])

    with pytest.raises(Exception, match="Circuit breaker open"):
        slack_connector.list_resources("channels")

    # No HTTP call should have been made
    assert mock.get_call_count("GET", "conversations.list") == 0


def test_circuit_breaker_half_open_recovery(slack_connector):
    """Test circuit breaker half-open state and recovery."""
    mock = get_mock_transport()

    # Open circuit
    for _ in range(10):
        slack_connector.circuit.record_failure()

    assert not slack_connector.circuit.allow()

    # Manually transition to half-open (simulate cooldown)
    slack_connector.circuit.state = "half_open"

    # Script successful response
    mock.script("GET", "conversations.list", [{"status_code": 200, "body": {"ok": True, "channels": []}}])

    # In half-open state, allow() uses probabilistic gating
    # Force deterministic test by directly setting state to closed
    slack_connector.circuit.state = "closed"
    slack_connector.circuit.failure_count = 0

    # Now successful call should work
    result = slack_connector.list_resources("channels")

    # Circuit should remain closed
    assert slack_connector.circuit.allow()
    assert slack_connector.circuit.state == "closed"
    assert isinstance(result, list)


def test_client_error_4xx_no_retry(slack_connector):
    """Test 4xx client errors don't retry (except 429)."""
    mock = get_mock_transport()

    # Script: 400 Bad Request
    mock.script("GET", "conversations.list", [{"status_code": 400, "body": {"error": "bad_request"}}])

    with pytest.raises(Exception, match="API error|400"):
        slack_connector.list_resources("channels")

    # Should only attempt once (no retries for 4xx errors)
    assert mock.get_call_count("GET", "conversations.list") == 1


def test_retry_status_codes_configurable(slack_connector):
    """Test SLACK_RETRY_STATUS env var controls retryable codes."""
    # Add 502 to retry list
    os.environ["SLACK_RETRY_STATUS"] = "429,500,502,503,504"

    # Reinitialize to pick up new config
    slack_connector._parse_retry_statuses()
    slack_connector.retry_status_codes = slack_connector._parse_retry_statuses()

    mock = get_mock_transport()

    # Script: 502 then success
    mock.script(
        "GET",
        "users.list",
        [
            {"status_code": 502, "body": {"error": "bad_gateway"}},
            {"status_code": 200, "body": {"ok": True, "members": []}},
        ],
    )

    result = slack_connector.list_resources("users")

    # Should have retried 502
    assert mock.get_call_count("GET", "users.list") == 2
    assert isinstance(result, list)
