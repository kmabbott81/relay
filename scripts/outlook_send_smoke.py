#!/usr/bin/env python3
"""CLI smoke test for Microsoft Outlook send.

Sprint 55 Week 2: Quick command-line test for Outlook send functionality.

Usage:
    python scripts/outlook_send_smoke.py --to test@example.com --subject "Test" --text "Hello"
    python scripts/outlook_send_smoke.py --to test@example.com --html "<h1>Test</h1>" --dry-run
    python scripts/outlook_send_smoke.py --to test@example.com --full-test

Environment variables required:
    - PROVIDER_MICROSOFT_ENABLED=true
    - MS_CLIENT_ID, MS_CLIENT_SECRET, MS_TENANT_ID
    - OAUTH_ENCRYPTION_KEY
    - DATABASE_URL, REDIS_URL
    - MS_TEST_WORKSPACE_ID (workspace UUID for OAuth tokens)
    - MS_TEST_ACTOR (actor ID / user email)
"""

import argparse
import asyncio
import base64
import json
import os
import sys
import time
from typing import Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from relay_ai.actions.adapters.microsoft import MicrosoftAdapter  # noqa: E402


def check_env_vars() -> tuple[bool, list[str]]:
    """Check if required environment variables are set.

    Returns:
        Tuple of (all_present, missing_vars)
    """
    required_vars = [
        "PROVIDER_MICROSOFT_ENABLED",
        "MS_CLIENT_ID",
        "MS_CLIENT_SECRET",
        "MS_TENANT_ID",
        "OAUTH_ENCRYPTION_KEY",
        "DATABASE_URL",
        "REDIS_URL",
        "MS_TEST_WORKSPACE_ID",
        "MS_TEST_ACTOR",
    ]

    missing = []
    for var in required_vars:
        value = os.getenv(var)
        if not value:
            missing.append(var)
        elif var == "PROVIDER_MICROSOFT_ENABLED" and value.lower() != "true":
            missing.append(f"{var} (must be 'true', got '{value}')")

    return (len(missing) == 0, missing)


# Test data
RED_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
)


async def smoke_test_simple(
    adapter: MicrosoftAdapter,
    workspace_id: str,
    actor_id: str,
    to: str,
    subject: str,
    text: str,
    html: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run simple smoke test: text or HTML email.

    Args:
        adapter: Microsoft adapter instance
        workspace_id: Workspace UUID
        actor_id: Actor ID
        to: Recipient email
        subject: Email subject
        text: Plain text body
        html: Optional HTML body
        dry_run: If True, only run preview

    Returns:
        Test result dict
    """
    print(f"\n{'=' * 60}")
    print("Smoke Test: Simple Email")
    print(f"{'=' * 60}")
    print(f"To: {to}")
    print(f"Subject: {subject}")
    print(f"Content: {'HTML + text' if html else 'text only'}")
    print(f"Mode: {'DRY_RUN (preview only)' if dry_run else 'LIVE (will send)'}")
    print()

    start_time = time.perf_counter()
    result: dict[str, Any] = {
        "test": "simple",
        "status": "unknown",
        "duration_seconds": 0.0,
        "preview": None,
        "execute": None,
        "error": None,
    }

    try:
        # Build params
        params = {
            "to": to,
            "subject": subject,
            "text": text,
        }
        if html:
            params["html"] = html

        # Run preview
        print("[1/2] Running preview...")
        preview_result = adapter.preview("outlook.send", params)
        result["preview"] = {
            "status": preview_result.get("status"),
            "correlation_id": preview_result.get("correlation_id", "N/A"),
        }
        print("✓ Preview succeeded")
        print(f"  Correlation ID: {preview_result.get('correlation_id', 'N/A')}")

        # Run execute (unless dry-run)
        if not dry_run:
            print("[2/2] Running execute...")
            execute_result = await adapter.execute("outlook.send", params, workspace_id, actor_id)
            result["execute"] = {
                "status": execute_result.get("status"),
                "correlation_id": execute_result.get("correlation_id", "N/A"),
                "provider": execute_result.get("provider"),
            }
            print(f"✓ Execute succeeded: {execute_result.get('status')}")
            print(f"  Provider: {execute_result.get('provider')}")
            print(f"\n  Check inbox: {to}")
        else:
            print("[2/2] DRY_RUN: Skipping execute")
            result["execute"] = {"status": "skipped (dry-run)"}

        result["status"] = "PASS"

    except Exception as e:
        result["status"] = "FAIL"
        result["error"] = str(e)
        print(f"✗ Test failed: {e}")

    finally:
        result["duration_seconds"] = time.perf_counter() - start_time
        print(f"\nResult: {result['status']} ({result['duration_seconds']:.2f}s)")

    return result


async def smoke_test_full(
    adapter: MicrosoftAdapter,
    workspace_id: str,
    actor_id: str,
    to: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run full complexity smoke test: HTML + inline + attachment.

    Args:
        adapter: Microsoft adapter instance
        workspace_id: Workspace UUID
        actor_id: Actor ID
        to: Recipient email
        dry_run: If True, only run preview

    Returns:
        Test result dict
    """
    print(f"\n{'=' * 60}")
    print("Smoke Test: Full Complexity")
    print(f"{'=' * 60}")
    print(f"To: {to}")
    print("Content: HTML + inline image + attachment")
    print(f"Mode: {'DRY_RUN (preview only)' if dry_run else 'LIVE (will send)'}")
    print()

    start_time = time.perf_counter()
    result: dict[str, Any] = {
        "test": "full",
        "status": "unknown",
        "duration_seconds": 0.0,
        "preview": None,
        "execute": None,
        "error": None,
    }

    try:
        # Build params with inline + attachment
        params = {
            "to": to,
            "subject": f"Outlook Smoke Test: Full Complexity [{time.strftime('%Y-%m-%d %H:%M:%S')}]",
            "text": "Fallback: Report with logo and CSV attachment",
            "html": """
            <html>
            <body>
                <h1>Outlook Integration Smoke Test</h1>
                <p>This email was sent via <strong>Microsoft Graph API</strong>.</p>
                <p>Logo below (1x1 red pixel PNG):</p>
                <img src="cid:logo" alt="Logo" width="50" height="50" style="border: 1px solid red;" />
                <p>Attachment: report.csv</p>
            </body>
            </html>
            """,
            "inline": [
                {
                    "cid": "logo",
                    "filename": "logo.png",
                    "content_type": "image/png",
                    "data": base64.b64encode(RED_PIXEL_PNG).decode(),
                }
            ],
            "attachments": [
                {
                    "filename": "report.csv",
                    "content_type": "text/csv",
                    "data": base64.b64encode(b"month,revenue\nJan,1000\nFeb,1500\n").decode(),
                }
            ],
        }

        # Run preview
        print("[1/2] Running preview...")
        preview_result = adapter.preview("outlook.send", params)
        result["preview"] = {
            "status": preview_result.get("status"),
            "correlation_id": preview_result.get("correlation_id", "N/A"),
        }
        print("✓ Preview succeeded")
        print(f"  Correlation ID: {preview_result.get('correlation_id', 'N/A')}")

        # Run execute (unless dry-run)
        if not dry_run:
            print("[2/2] Running execute...")
            execute_result = await adapter.execute("outlook.send", params, workspace_id, actor_id)
            result["execute"] = {
                "status": execute_result.get("status"),
                "correlation_id": execute_result.get("correlation_id", "N/A"),
                "provider": execute_result.get("provider"),
            }
            print(f"✓ Execute succeeded: {execute_result.get('status')}")
            print(f"  Provider: {execute_result.get('provider')}")
            print(f"\n  Check inbox: {to}")
        else:
            print("[2/2] DRY_RUN: Skipping execute")
            result["execute"] = {"status": "skipped (dry-run)"}

        result["status"] = "PASS"

    except Exception as e:
        result["status"] = "FAIL"
        result["error"] = str(e)
        print(f"✗ Test failed: {e}")

    finally:
        result["duration_seconds"] = time.perf_counter() - start_time
        print(f"\nResult: {result['status']} ({result['duration_seconds']:.2f}s)")

    return result


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="CLI smoke test for Microsoft Outlook send")
    parser.add_argument("--to", type=str, help="Recipient email address")
    parser.add_argument("--subject", type=str, help="Email subject (for simple test)")
    parser.add_argument("--text", type=str, help="Plain text body (for simple test)")
    parser.add_argument("--html", type=str, help="HTML body (optional, for simple test)")
    parser.add_argument(
        "--full-test", action="store_true", help="Run full complexity test (HTML + inline + attachment)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Only run preview, skip execute")
    parser.add_argument("--workspace-id", type=str, help="Workspace UUID (or set MS_TEST_WORKSPACE_ID)")
    parser.add_argument("--actor-id", type=str, help="Actor ID (or set MS_TEST_ACTOR)")

    args = parser.parse_args()

    # Check environment variables
    print("=" * 60)
    print("Outlook Send Smoke Test")
    print("=" * 60)
    print("\nChecking environment variables...")
    env_ok, missing = check_env_vars()

    if not env_ok:
        print("\n✗ Missing required environment variables:")
        for var in missing:
            print(f"  - {var}")
        print("\nPlease set all required variables and try again.")
        print("See: docs/specs/MS-OAUTH-SETUP-GUIDE.md")
        sys.exit(1)

    print("✓ All required environment variables set")

    # Get config from env or args
    workspace_id = args.workspace_id or os.getenv("MS_TEST_WORKSPACE_ID")
    actor_id = args.actor_id or os.getenv("MS_TEST_ACTOR")
    to_email = args.to or os.getenv("MS_TEST_RECIPIENT")

    if not to_email:
        print("\n✗ Error: Must provide --to or set MS_TEST_RECIPIENT")
        sys.exit(1)

    # Initialize adapter
    adapter = MicrosoftAdapter()

    # Run test
    try:
        if args.full_test:
            # Full complexity test
            result = asyncio.run(smoke_test_full(adapter, workspace_id, actor_id, to_email, args.dry_run))
        else:
            # Simple test
            if not args.subject or not args.text:
                print("\n✗ Error: For simple test, must provide --subject and --text")
                print("   Or use --full-test for pre-configured full complexity test")
                sys.exit(1)

            result = asyncio.run(
                smoke_test_simple(
                    adapter,
                    workspace_id,
                    actor_id,
                    to_email,
                    args.subject,
                    args.text,
                    args.html,
                    args.dry_run,
                )
            )

        # Write result to file
        results_file = f"logs/outlook_smoke_{int(time.time())}.json"
        os.makedirs("logs", exist_ok=True)
        with open(results_file, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nResults written to: {results_file}")

        # Exit code based on result
        sys.exit(0 if result["status"] == "PASS" else 1)

    except KeyboardInterrupt:
        print("\n\n✗ Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
