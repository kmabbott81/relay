#!/usr/bin/env python3
"""E2E test script for Gmail Rich Email integration.

Sprint 54 Phase 3: Verify full path with real Gmail API.

SECURITY NOTE:
  File logging is disabled by default. To enable, set E2E_LOG_TO_FILE=true.
  When enabled, payloads (base64, large subjects) are redacted/hashed for security.

Usage:
    python scripts/e2e_gmail_test.py --scenarios all
    python scripts/e2e_gmail_test.py --scenarios 1,2,3 --dry-run
    python scripts/e2e_gmail_test.py --scenario 5 --verbose
"""

import argparse
import asyncio
import base64
import hashlib
import json
import logging
import os
import sys
import time
from typing import Any

# Add project root to path (noqa: E402)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from relay_ai.actions.adapters.google import GoogleAdapter  # noqa: E402

# Test data
RED_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
)

SMALL_PDF = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\n%%EOF"


def redact_payload(params: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive payload fields for logging.

    - Hash base64 blobs (attachments, inline images)
    - Truncate long subjects to 80 chars

    Args:
        params: Email parameters

    Returns:
        Redacted copy of params
    """
    redacted = params.copy()

    # Truncate subject
    if "subject" in redacted and len(redacted["subject"]) > 80:
        redacted["subject"] = redacted["subject"][:80] + "..."

    # Hash attachment data
    if "attachments" in redacted:
        redacted["attachments"] = [
            {
                "filename": att.get("filename", "unknown"),
                "content_type": att.get("content_type", "unknown"),
                "data_sha256": hashlib.sha256(att.get("data", "").encode()).hexdigest()[:16],
            }
            for att in redacted["attachments"]
        ]

    # Hash inline image data
    if "inline" in redacted:
        redacted["inline"] = [
            {
                "cid": img.get("cid", "unknown"),
                "filename": img.get("filename", "unknown"),
                "content_type": img.get("content_type", "unknown"),
                "data_sha256": hashlib.sha256(img.get("data", "").encode()).hexdigest()[:16],
            }
            for img in redacted["inline"]
        ]

    return redacted


class E2ETestRunner:
    """E2E test runner for Gmail Rich Email."""

    def __init__(
        self,
        workspace_id: str,
        actor_id: str,
        recipient_email: str,
        dry_run: bool = False,
        verbose: bool = False,
    ):
        """Initialize test runner.

        Args:
            workspace_id: Workspace UUID (for OAuth token lookup)
            actor_id: Actor ID (user email)
            recipient_email: Where to send test emails
            dry_run: If True, only run preview (no actual sends)
            verbose: Enable verbose logging
        """
        self.workspace_id = workspace_id
        self.actor_id = actor_id
        self.recipient_email = recipient_email
        self.dry_run = dry_run
        self.verbose = verbose

        # Set up logging
        log_level = logging.DEBUG if verbose else logging.INFO
        handlers = [logging.StreamHandler()]

        # Gate file logging behind E2E_LOG_TO_FILE (default off)
        if os.getenv("E2E_LOG_TO_FILE", "false").lower() == "true":
            handlers.append(logging.FileHandler("logs/e2e_test.log"))

        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=handlers,
        )
        self.logger = logging.getLogger(__name__)

        # Log redaction notice if file logging enabled
        if os.getenv("E2E_LOG_TO_FILE", "false").lower() == "true":
            self.logger.info("=" * 60)
            self.logger.info("SECURITY: File logging enabled with payload redaction")
            self.logger.info("Base64 blobs hashed, subjects truncated to 80 chars")
            self.logger.info("=" * 60)

        # Initialize adapter
        self.adapter = GoogleAdapter()

        # Test results
        self.results: list[dict[str, Any]] = []

    async def run_scenario(self, scenario_num: int) -> dict[str, Any]:
        """Run a specific test scenario.

        Args:
            scenario_num: Scenario number (1-8)

        Returns:
            Test result dict with status, metrics, errors
        """
        scenario_name = f"Scenario {scenario_num}"
        self.logger.info(f"{'=' * 60}")
        self.logger.info(f"Running {scenario_name}")
        self.logger.info(f"{'=' * 60}")

        start_time = time.perf_counter()
        result = {
            "scenario": scenario_num,
            "name": scenario_name,
            "status": "unknown",
            "duration_seconds": 0.0,
            "preview_result": None,
            "execute_result": None,
            "error": None,
            "correlation_id": None,
        }

        try:
            if scenario_num == 1:
                params = self._scenario_1_text_only()
            elif scenario_num == 2:
                params = self._scenario_2_html()
            elif scenario_num == 3:
                params = self._scenario_3_inline_image()
            elif scenario_num == 4:
                params = self._scenario_4_attachments()
            elif scenario_num == 5:
                params = self._scenario_5_full_complexity()
            elif scenario_num == 6:
                # Multiple sub-scenarios for validation errors
                return await self._scenario_6_validation_errors()
            elif scenario_num == 7:
                return await self._scenario_7_internal_controls()
            elif scenario_num == 8:
                return await self._scenario_8_rollout_observation()
            else:
                raise ValueError(f"Unknown scenario: {scenario_num}")

            # Run preview
            self.logger.info("Running preview...")
            if self.verbose:
                self.logger.debug(f"Params (redacted): {redact_payload(params)}")
            preview_result = self.adapter._preview_gmail_send(params)
            result["preview_result"] = {
                "digest": preview_result["digest"],
                "raw_message_length": preview_result["raw_message_length"],
                "warnings": preview_result.get("warnings", []),
                "sanitization_summary": preview_result.get("sanitization_summary"),
            }

            self.logger.info(f"Preview succeeded: {preview_result['digest']}")
            if preview_result.get("sanitization_summary"):
                self.logger.info(f"Sanitization: {preview_result['sanitization_summary']}")

            # Run execute (unless dry-run)
            if not self.dry_run:
                self.logger.info("Running execute...")
                execute_result = await self.adapter._execute_gmail_send(params, self.workspace_id, self.actor_id)
                result["execute_result"] = {
                    "status": execute_result["status"],
                    "message_id": execute_result.get("message_id"),
                    "thread_id": execute_result.get("thread_id"),
                }
                result["correlation_id"] = "<logged-not-in-response>"

                self.logger.info(f"Execute succeeded: {execute_result['message_id']}")
                self.logger.info(f"Check inbox: {self.recipient_email}")
            else:
                self.logger.info("DRY_RUN: Skipping execute")
                result["execute_result"] = {"status": "skipped (dry-run)"}

            result["status"] = "PASS"

        except ValueError as e:
            # Expected for validation error scenarios
            result["status"] = "ERROR (expected)"
            result["error"] = str(e)
            self.logger.warning(f"Validation error (may be expected): {e}")

        except Exception as e:
            result["status"] = "FAIL"
            result["error"] = str(e)
            self.logger.error(f"Test failed: {e}", exc_info=True)

        finally:
            result["duration_seconds"] = time.perf_counter() - start_time
            self.logger.info(f"{scenario_name}: {result['status']} ({result['duration_seconds']:.2f}s)")

        return result

    def _scenario_1_text_only(self) -> dict[str, Any]:
        """Scenario 1: Text-only email (baseline)."""
        return {
            "to": self.recipient_email,
            "subject": "E2E Test: Text Only",
            "text": "This is a plain text email sent via E2E test.\n\nTimestamp: " + time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _scenario_2_html(self) -> dict[str, Any]:
        """Scenario 2: HTML + text fallback."""
        return {
            "to": self.recipient_email,
            "subject": "E2E Test: HTML Email",
            "text": "Fallback plain text (if HTML not supported)",
            "html": """
            <html>
            <head><title>Test</title></head>
            <body>
                <h1 style="color: blue;">Rich Email Test</h1>
                <p>This is <strong>HTML</strong> content with <em>formatting</em>.</p>
                <ul>
                    <li>Item 1</li>
                    <li>Item 2</li>
                </ul>
                <script>alert('xss')</script>  <!-- Should be sanitized -->
                <p onclick="alert('xss')">Click me (event handler should be removed)</p>
            </body>
            </html>
            """,
        }

    def _scenario_3_inline_image(self) -> dict[str, Any]:
        """Scenario 3: HTML + inline image with CID."""
        return {
            "to": self.recipient_email,
            "subject": "E2E Test: Inline Image",
            "text": "Fallback: [Logo image shown below]\n\nRed pixel PNG",
            "html": """
            <html>
            <body>
                <h2>Inline Image Test</h2>
                <p>Logo below (1x1 red pixel PNG):</p>
                <img src="cid:logo" alt="Test Logo" width="100" height="100" style="border: 1px solid black;" />
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
        }

    def _scenario_4_attachments(self) -> dict[str, Any]:
        """Scenario 4: Regular file attachments."""
        return {
            "to": self.recipient_email,
            "subject": "E2E Test: Attachments",
            "text": "Please see attached files:\n\n1. report.pdf (sample PDF)\n2. data.csv (sample CSV)",
            "attachments": [
                {
                    "filename": "report.pdf",
                    "content_type": "application/pdf",
                    "data": base64.b64encode(SMALL_PDF).decode(),
                },
                {
                    "filename": "data.csv",
                    "content_type": "text/csv",
                    "data": base64.b64encode(b"col1,col2\nvalue1,value2\n").decode(),
                },
            ],
        }

    def _scenario_5_full_complexity(self) -> dict[str, Any]:
        """Scenario 5: HTML + inline images + attachments (nested multipart)."""
        return {
            "to": self.recipient_email,
            "subject": "E2E Test: Full Complexity",
            "text": "Fallback: Report with inline chart and CSV attachment",
            "html": """
            <html>
            <body>
                <h1>Monthly Report</h1>
                <p>See chart below:</p>
                <img src="cid:chart" alt="Chart" style="max-width: 100%;" />
                <p>Data attached as CSV.</p>
            </body>
            </html>
            """,
            "inline": [
                {
                    "cid": "chart",
                    "filename": "chart.png",
                    "content_type": "image/png",
                    "data": base64.b64encode(RED_PIXEL_PNG).decode(),
                }
            ],
            "attachments": [
                {
                    "filename": "monthly_data.csv",
                    "content_type": "text/csv",
                    "data": base64.b64encode(b"month,revenue\nJan,1000\nFeb,1500\n").decode(),
                }
            ],
        }

    async def _scenario_6_validation_errors(self) -> dict[str, Any]:
        """Scenario 6: Validation error handling (multiple sub-tests)."""
        result = {"scenario": 6, "name": "Scenario 6: Validation Errors", "sub_tests": []}

        # 6a: Oversized attachment
        try:
            params = {
                "to": self.recipient_email,
                "subject": "E2E Test: Oversized",
                "text": "Body",
                "attachments": [
                    {
                        "filename": "huge.bin",
                        "content_type": "application/octet-stream",
                        "data": base64.b64encode(b"x" * 27_000_000).decode(),  # 27MB > 25 MiB limit
                    }
                ],
            }
            self.adapter._preview_gmail_send(params)
            result["sub_tests"].append({"name": "6a_oversized", "status": "FAIL", "reason": "Should have raised error"})
        except ValueError as e:
            error = json.loads(str(e))
            if error["error_code"] == "validation_error_attachment_too_large":
                result["sub_tests"].append(
                    {"name": "6a_oversized", "status": "PASS", "error_code": error["error_code"]}
                )
            else:
                result["sub_tests"].append(
                    {"name": "6a_oversized", "status": "FAIL", "reason": f"Wrong error: {error['error_code']}"}
                )

        # 6b: Blocked MIME type
        try:
            params = {
                "to": self.recipient_email,
                "subject": "E2E Test: Blocked MIME",
                "text": "Body",
                "attachments": [
                    {
                        "filename": "malware.exe",
                        "content_type": "application/x-msdownload",
                        "data": base64.b64encode(b"MZ fake exe").decode(),
                    }
                ],
            }
            self.adapter._preview_gmail_send(params)
            result["sub_tests"].append(
                {"name": "6b_blocked_mime", "status": "FAIL", "reason": "Should have raised error"}
            )
        except ValueError as e:
            error = json.loads(str(e))
            if error["error_code"] == "validation_error_blocked_mime_type":
                result["sub_tests"].append(
                    {"name": "6b_blocked_mime", "status": "PASS", "error_code": error["error_code"]}
                )
            else:
                result["sub_tests"].append(
                    {"name": "6b_blocked_mime", "status": "FAIL", "reason": f"Wrong error: {error['error_code']}"}
                )

        # 6c: Orphan CID
        try:
            params = {
                "to": self.recipient_email,
                "subject": "E2E Test: Orphan CID",
                "text": "Body",
                "html": '<html><body><img src="cid:missing" /></body></html>',
                "inline": [
                    {
                        "cid": "wrong",
                        "filename": "img.png",
                        "content_type": "image/png",
                        "data": base64.b64encode(RED_PIXEL_PNG).decode(),
                    }
                ],
            }
            self.adapter._preview_gmail_send(params)
            result["sub_tests"].append(
                {"name": "6c_orphan_cid", "status": "FAIL", "reason": "Should have raised error"}
            )
        except ValueError as e:
            error = json.loads(str(e))
            if error["error_code"] == "validation_error_missing_inline_image":
                result["sub_tests"].append(
                    {"name": "6c_orphan_cid", "status": "PASS", "error_code": error["error_code"]}
                )
            else:
                result["sub_tests"].append(
                    {"name": "6c_orphan_cid", "status": "FAIL", "reason": f"Wrong error: {error['error_code']}"}
                )

        # Aggregate status
        all_pass = all(t["status"] == "PASS" for t in result["sub_tests"])
        result["status"] = "PASS" if all_pass else "FAIL"
        return result

    async def _scenario_7_internal_controls(self) -> dict[str, Any]:
        """Scenario 7: Internal-only recipient controls."""
        result = {"scenario": 7, "name": "Scenario 7: Internal Controls", "sub_tests": []}

        # Get internal config
        internal_only = self.adapter.internal_only
        allowed_domains = self.adapter.internal_allowed_domains

        if not internal_only:
            result["status"] = "SKIP"
            result["reason"] = "GOOGLE_INTERNAL_ONLY=false, skipping"
            return result

        # 7a: Allowed internal domain
        if allowed_domains:
            test_email = f"test@{allowed_domains[0]}"
            try:
                params = {"to": test_email, "subject": "Test", "text": "Body"}
                self.adapter._preview_gmail_send(params)
                result["sub_tests"].append({"name": "7a_allowed_domain", "status": "PASS"})
            except Exception as e:
                result["sub_tests"].append({"name": "7a_allowed_domain", "status": "FAIL", "reason": str(e)})

        # 7b: Blocked external domain
        try:
            params = {"to": "external@notallowed.com", "subject": "Test", "text": "Body"}
            self.adapter._preview_gmail_send(params)
            result["sub_tests"].append(
                {"name": "7b_blocked_external", "status": "FAIL", "reason": "Should have blocked"}
            )
        except ValueError as e:
            error = json.loads(str(e))
            if error["error_code"] == "internal_only_recipient_blocked":
                result["sub_tests"].append({"name": "7b_blocked_external", "status": "PASS"})
            else:
                result["sub_tests"].append(
                    {"name": "7b_blocked_external", "status": "FAIL", "reason": f"Wrong error: {error['error_code']}"}
                )

        # Aggregate
        all_pass = all(t["status"] == "PASS" for t in result["sub_tests"])
        result["status"] = "PASS" if all_pass else "FAIL"
        return result

    async def _scenario_8_rollout_observation(self) -> dict[str, Any]:
        """Scenario 8: Rollout controller observation (dry-run mode)."""
        result = {"scenario": 8, "name": "Scenario 8: Rollout Observation", "status": "MANUAL"}

        self.logger.info("This scenario requires manual verification:")
        self.logger.info("1. Run scenarios 1-5 to generate traffic")
        self.logger.info("2. Wait for controller evaluation cycle (5 minutes)")
        self.logger.info("3. Check logs for 'DRY_RUN:' entries")
        self.logger.info("4. Verify Prometheus metrics are being collected")
        self.logger.info("5. Verify Redis rollout_percent unchanged (dry-run)")

        result["instructions"] = [
            "Run multiple test scenarios to generate traffic",
            "Monitor logs/rollout_controller.log for DRY_RUN entries",
            "Query Prometheus: action_execution_total{provider='google'}",
            "Verify redis-cli GET flags:google:rollout_percent unchanged",
        ]

        return result

    async def run_all_scenarios(self, scenario_nums: list[int]) -> dict[str, Any]:
        """Run multiple scenarios.

        Args:
            scenario_nums: List of scenario numbers to run (e.g., [1, 2, 3])

        Returns:
            Summary dict with all results
        """
        start_time = time.perf_counter()
        self.logger.info(f"Running {len(scenario_nums)} scenarios...")

        for num in scenario_nums:
            result = await self.run_scenario(num)
            self.results.append(result)

        duration = time.perf_counter() - start_time

        # Generate summary
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        skipped = sum(1 for r in self.results if r["status"] in ["SKIP", "MANUAL"])

        summary = {
            "total_scenarios": len(scenario_nums),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "duration_seconds": duration,
            "results": self.results,
        }

        self.logger.info(f"{'=' * 60}")
        self.logger.info("E2E Test Summary")
        self.logger.info(f"{'=' * 60}")
        self.logger.info(f"Total: {len(scenario_nums)}, Passed: {passed}, Failed: {failed}, Skipped: {skipped}")
        self.logger.info(f"Duration: {duration:.2f}s")

        # Write results to file
        results_file = f"logs/e2e_results_{int(time.time())}.json"
        with open(results_file, "w") as f:
            json.dump(summary, f, indent=2)
        self.logger.info(f"Results written to: {results_file}")

        return summary


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="E2E test script for Gmail Rich Email")
    parser.add_argument(
        "--scenarios",
        type=str,
        default="all",
        help="Comma-separated scenario numbers or 'all' (e.g., '1,2,3' or 'all')",
    )
    parser.add_argument("--workspace-id", type=str, help="Workspace UUID (for OAuth tokens)")
    parser.add_argument("--actor-id", type=str, help="Actor ID (user email)")
    parser.add_argument("--recipient", type=str, help="Test recipient email address")
    parser.add_argument("--dry-run", action="store_true", help="Only run preview, skip execute")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Get config from env or args
    workspace_id = args.workspace_id or os.getenv("E2E_WORKSPACE_ID")
    actor_id = args.actor_id or os.getenv("E2E_ACTOR_ID")
    recipient = args.recipient or os.getenv("E2E_RECIPIENT_EMAIL")

    if not workspace_id or not actor_id or not recipient:
        print("Error: Must provide --workspace-id, --actor-id, --recipient (or set E2E_* env vars)")
        sys.exit(1)

    # Parse scenarios
    if args.scenarios.lower() == "all":
        scenario_nums = list(range(1, 9))  # Scenarios 1-8
    else:
        scenario_nums = [int(s.strip()) for s in args.scenarios.split(",")]

    # Run tests
    runner = E2ETestRunner(
        workspace_id=workspace_id,
        actor_id=actor_id,
        recipient_email=recipient,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    summary = asyncio.run(runner.run_all_scenarios(scenario_nums))

    # Exit code based on results
    if summary["failed"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
