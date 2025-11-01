"""Shared fixtures for AI Orchestrator tests.

Sprint 55 Week 3: Test fixtures for AI planning, queue, and execution.
"""

import os
from unittest.mock import Mock

import pytest


@pytest.fixture
def mock_redis():
    """Mock Redis client for queue tests (avoids external dependency)."""
    redis = Mock()
    redis.set = Mock(return_value=True)  # For idempotency checks
    redis.hset = Mock(return_value=1)
    redis.hgetall = Mock(return_value={})
    redis.rpush = Mock(return_value=1)
    redis.blpop = Mock(return_value=None)
    redis.llen = Mock(return_value=0)
    redis.expire = Mock(return_value=True)
    redis.keys = Mock(return_value=[])
    return redis


@pytest.fixture
def sample_plan_minimal():
    """Minimal valid plan for testing."""
    return {
        "intent": "Send email to ops team",
        "confidence": 0.95,
        "actions": [
            {
                "provider": "google",
                "action": "gmail.send",
                "params": {"to": "ops@example.com", "subject": "Test", "body": "Hello"},
                "client_request_id": "test-req-001",
            }
        ],
        "notes": None,
    }


@pytest.fixture
def sample_plan_multi_action():
    """Plan with multiple actions."""
    return {
        "intent": "Send email and create task",
        "confidence": 0.85,
        "actions": [
            {
                "provider": "google",
                "action": "gmail.send",
                "params": {"to": "ops@example.com", "subject": "Weekly report", "body": "Attached"},
                "client_request_id": "test-req-002",
            },
            {
                "provider": "independent",
                "action": "task.create",
                "params": {"title": "Review report", "due": "2025-01-20"},
                "client_request_id": "test-req-003",
            },
        ],
        "notes": "Multi-step workflow",
    }


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response for planner tests."""

    class MockMessage:
        def __init__(self, content):
            self.content = content

    class MockChoice:
        def __init__(self, message):
            self.message = message

    class MockUsage:
        def __init__(self):
            self.prompt_tokens = 150
            self.completion_tokens = 200
            self.total_tokens = 350

    class MockResponse:
        def __init__(self, content):
            self.choices = [MockChoice(MockMessage(content))]
            self.usage = MockUsage()

    return MockResponse


@pytest.fixture(autouse=True)
def reset_env():
    """Reset environment variables for tests."""
    # Save originals
    orig_env = os.environ.copy()

    # Set test defaults
    os.environ["ACTION_ALLOWLIST"] = "gmail.send,outlook.send,task.create"
    os.environ["AI_MODEL"] = "gpt-4o-mini"
    os.environ["AI_MAX_OUTPUT_TOKENS"] = "800"

    yield

    # Restore
    os.environ.clear()
    os.environ.update(orig_env)
