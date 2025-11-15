#!/usr/bin/env python3
"""Test attachment size validation."""
import base64
import os
import sys
from pathlib import Path

from relay_ai.actions.adapters.google import GoogleAdapter

# Load environment
env_file = Path(__file__).parent / ".env.e2e"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key] = value


def test_oversized_attachment():
    """Test that oversized attachment raises validation error."""
    adapter = GoogleAdapter()

    print("Creating 26MB attachment...")
    raw_data = b"x" * 26_000_000  # 26MB
    print(f"Raw data size: {len(raw_data):,} bytes ({len(raw_data) / (1024*1024):.2f}MB)")

    base64_data = base64.b64encode(raw_data).decode()
    print(f"Base64 encoded size: {len(base64_data):,} bytes ({len(base64_data) / (1024*1024):.2f}MB)")

    params = {
        "to": "kbmabb@gmail.com",  # Use allowed test recipient
        "subject": "Test",
        "text": "Body",
        "attachments": [
            {
                "filename": "huge.bin",
                "content_type": "application/octet-stream",
                "data": base64_data,
            }
        ],
    }

    print("\nCalling _preview_gmail_send...")
    try:
        result = adapter._preview_gmail_send(params)
        print("[FAIL] Preview succeeded when it should have raised error!")
        print(f"Result: {result}")
        sys.exit(1)
    except ValueError as e:
        error_str = str(e)
        print(f"[OK] ValueError raised: {error_str[:100]}...")
        if "validation_error_attachment_too_large" in error_str:
            print("[OK] Correct error code: validation_error_attachment_too_large")
            sys.exit(0)
        else:
            print(f"[FAIL] Wrong error code. Full error: {error_str}")
            sys.exit(1)


if __name__ == "__main__":
    test_oversized_attachment()
