"""Integration tests for Microsoft large attachment upload sessions.

Sprint 55 Week 3: Real Graph API calls (gated by TEST_MICROSOFT_INTEGRATION=true).

Prerequisites:
- PROVIDER_MICROSOFT_ENABLED=true
- MS_UPLOAD_SESSIONS_ENABLED=true
- MS_CLIENT_ID, MS_CLIENT_SECRET configured
- Valid Microsoft OAuth tokens in database for test workspace/actor
- TEST_MICROSOFT_INTEGRATION=true (else skip)
"""

import base64
import os

import pytest


@pytest.mark.skipif(
    os.getenv("TEST_MICROSOFT_INTEGRATION") != "true",
    reason="TEST_MICROSOFT_INTEGRATION not enabled",
)
class TestMicrosoftLargeAttachmentIntegration:
    """Integration tests for Microsoft upload session flow (real Graph API)."""

    @pytest.mark.anyio
    async def test_send_email_with_5mb_attachment(self):
        """Test sending email with 5MB attachment via upload session.

        This test requires:
        - Valid Microsoft OAuth tokens for test workspace/actor
        - MS_UPLOAD_SESSIONS_ENABLED=true
        - Network access to graph.microsoft.com
        """
        from src.actions.adapters.microsoft import MicrosoftAdapter

        adapter = MicrosoftAdapter()

        # Create 5MB attachment
        attachment_data = b"x" * (5 * 1024 * 1024)
        attachment_b64 = base64.b64encode(attachment_data).decode("ascii")

        # Test workspace and actor (must have valid tokens in database)
        workspace_id = os.getenv("TEST_MICROSOFT_WORKSPACE_ID", "test-workspace")
        actor_id = os.getenv("TEST_MICROSOFT_ACTOR_ID", "test-actor@example.com")
        recipient = os.getenv("TEST_MICROSOFT_RECIPIENT", "test-recipient@example.com")

        params = {
            "to": recipient,
            "subject": "Integration Test: Large Attachment (5MB)",
            "text": "This is an integration test for large attachment upload sessions.",
            "html": "<p>This is an <strong>integration test</strong> for large attachment upload sessions.</p>",
            "attachments": [
                {
                    "filename": "large_file_5mb.bin",
                    "content_type": "application/octet-stream",
                    "data": attachment_b64,
                }
            ],
        }

        # Execute
        result = await adapter.execute("outlook.send", params, workspace_id, actor_id)

        # Assertions
        assert result["status"] == "sent"
        assert result["upload_session_used"] is True
        assert result["to"] == recipient
        assert result["subject"] == "Integration Test: Large Attachment (5MB)"
        assert "draft_id" in result
        assert result["provider"] == "microsoft"

        print(f"✅ Email sent via upload session: draft_id={result['draft_id']}")

    @pytest.mark.anyio
    async def test_send_email_with_multiple_large_attachments(self):
        """Test sending email with multiple large attachments via upload session."""
        from src.actions.adapters.microsoft import MicrosoftAdapter

        adapter = MicrosoftAdapter()

        # Create 2 x 3MB attachments
        attachment1_data = b"a" * (3 * 1024 * 1024)
        attachment2_data = b"b" * (3 * 1024 * 1024)

        attachment1_b64 = base64.b64encode(attachment1_data).decode("ascii")
        attachment2_b64 = base64.b64encode(attachment2_data).decode("ascii")

        workspace_id = os.getenv("TEST_MICROSOFT_WORKSPACE_ID", "test-workspace")
        actor_id = os.getenv("TEST_MICROSOFT_ACTOR_ID", "test-actor@example.com")
        recipient = os.getenv("TEST_MICROSOFT_RECIPIENT", "test-recipient@example.com")

        params = {
            "to": recipient,
            "subject": "Integration Test: Multiple Large Attachments (2x3MB)",
            "text": "This email has 2 large attachments (3MB each).",
            "attachments": [
                {
                    "filename": "file1_3mb.bin",
                    "content_type": "application/octet-stream",
                    "data": attachment1_b64,
                },
                {
                    "filename": "file2_3mb.bin",
                    "content_type": "application/octet-stream",
                    "data": attachment2_b64,
                },
            ],
        }

        # Execute
        result = await adapter.execute("outlook.send", params, workspace_id, actor_id)

        # Assertions
        assert result["status"] == "sent"
        assert result["upload_session_used"] is True
        assert "draft_id" in result

        print(f"✅ Email sent with multiple attachments: draft_id={result['draft_id']}")

    @pytest.mark.anyio
    async def test_send_email_with_inline_image_and_large_attachment(self):
        """Test sending email with inline image and large attachment."""
        from src.actions.adapters.microsoft import MicrosoftAdapter

        adapter = MicrosoftAdapter()

        # Create inline image (100KB)
        inline_data = b"\x89PNG\r\n\x1a\n" + b"x" * (100 * 1024)
        inline_b64 = base64.b64encode(inline_data).decode("ascii")

        # Create large attachment (4MB)
        attachment_data = b"y" * (4 * 1024 * 1024)
        attachment_b64 = base64.b64encode(attachment_data).decode("ascii")

        workspace_id = os.getenv("TEST_MICROSOFT_WORKSPACE_ID", "test-workspace")
        actor_id = os.getenv("TEST_MICROSOFT_ACTOR_ID", "test-actor@example.com")
        recipient = os.getenv("TEST_MICROSOFT_RECIPIENT", "test-recipient@example.com")

        params = {
            "to": recipient,
            "subject": "Integration Test: Inline Image + Large Attachment",
            "text": "Plain text fallback",
            "html": '<p>Email with inline image: <img src="cid:image123" /></p>',
            "inline": [
                {
                    "cid": "image123",
                    "filename": "inline.png",
                    "content_type": "image/png",
                    "data": inline_b64,
                }
            ],
            "attachments": [
                {
                    "filename": "large_file_4mb.bin",
                    "content_type": "application/octet-stream",
                    "data": attachment_b64,
                }
            ],
        }

        # Execute
        result = await adapter.execute("outlook.send", params, workspace_id, actor_id)

        # Assertions
        assert result["status"] == "sent"
        assert result["upload_session_used"] is True

        print(f"✅ Email sent with inline + attachment: draft_id={result['draft_id']}")
