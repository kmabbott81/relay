#!/usr/bin/env python3
"""Quick test of Gmail adapter implementation."""

import asyncio
import os

# Set environment variables for testing
os.environ["PROVIDER_GOOGLE_ENABLED"] = "false"  # Test with flag off first

from relay_ai.actions.adapters.google import GoogleAdapter


def test_list_actions():
    """Test that gmail.send action is listed."""
    adapter = GoogleAdapter()
    actions = adapter.list_actions()

    print(f"Found {len(actions)} Google actions:")
    for action in actions:
        print(f"  - {action.id}: {action.name}")
        print(f"    Provider: {action.provider}")
        print(f"    Enabled: {action.enabled}")
        print(f"    Description: {action.description}")
        print()

    assert len(actions) == 1, f"Expected 1 action, got {len(actions)}"
    assert actions[0].id == "gmail.send", f"Expected gmail.send, got {actions[0].id}"
    assert actions[0].enabled == False, "Expected enabled=False when PROVIDER_GOOGLE_ENABLED=false"

    print("[OK] list_actions test PASSED")


def test_preview():
    """Test preview method with valid and invalid params."""
    adapter = GoogleAdapter()

    # Test valid params
    params = {
        "to": "test@example.com",
        "subject": "Test Email",
        "text": "This is a test email body.",
        "cc": ["cc@example.com"],
        "bcc": ["bcc@example.com"],
    }

    result = adapter.preview("gmail.send", params)

    print("Preview result:")
    print(f"  Summary: {result['summary'][:100]}...")
    print(f"  Digest: {result['digest']}")
    print(f"  Warnings: {result['warnings']}")
    print(f"  Raw message length: {result['raw_message_length']}")
    print()

    assert "test@example.com" in result["summary"]
    assert "Test Email" in result["summary"]
    assert len(result["digest"]) == 16, f"Expected 16-char digest, got {len(result['digest'])}"
    assert any(
        "PROVIDER_GOOGLE_ENABLED" in w for w in result["warnings"]
    ), f"Expected PROVIDER_GOOGLE_ENABLED warning, got: {result['warnings']}"

    print("[OK] preview test PASSED")


def test_preview_validation_error():
    """Test preview with invalid params."""
    adapter = GoogleAdapter()

    # Test invalid email
    params = {"to": "not-an-email", "subject": "Test", "text": "Body"}

    try:
        result = adapter.preview("gmail.send", params)
        assert False, "Should have raised ValueError for invalid email"
    except ValueError as e:
        print(f"Validation error (expected): {str(e)[:100]}")
        print("[OK] preview validation test PASSED")
        print()


async def test_execute_disabled():
    """Test execute when provider is disabled."""
    adapter = GoogleAdapter()

    params = {"to": "test@example.com", "subject": "Test", "text": "Body"}

    try:
        result = await adapter.execute("gmail.send", params, "workspace-123", "user@example.com")
        assert False, "Should have raised ValueError when provider disabled"
    except ValueError as e:
        assert "disabled" in str(e).lower()
        print(f"Execute disabled error (expected): {e}")
        print("[OK] execute disabled test PASSED")
        print()


def main():
    """Run all tests."""
    print("=" * 60)
    print("Gmail Adapter Implementation Test")
    print("=" * 60)
    print()

    test_list_actions()
    test_preview()
    test_preview_validation_error()

    # Run async test
    asyncio.run(test_execute_disabled())

    print("=" * 60)
    print("All tests PASSED [OK]")
    print("=" * 60)


if __name__ == "__main__":
    main()
