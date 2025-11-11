"""Unit tests for Microsoft Outlook adapter (outlook.send action).

Sprint 55 Phase 1: Week 1 scaffolding tests.

These tests validate:
- Parameter validation (Pydantic models)
- Internal-only recipient checks
- Recipient count limits (Microsoft: 150 max)
- Feature flag guards
- Rollout gate integration
- Preview functionality (no side effects)

Week 2-3 will add:
- OAuth token fetch tests
- Graph API integration tests
- Error mapping tests
- Telemetry emission tests
"""

import os
from unittest.mock import MagicMock

import pytest

from relay_ai.actions.adapters.microsoft import (
    MicrosoftAdapter,
    OutlookSendParams,
)


class TestOutlookSendParams:
    """Test Pydantic validation for outlook.send parameters."""

    def test_valid_params_minimal(self):
        """Test valid minimal parameters (to, subject, text)."""
        params = OutlookSendParams(
            to="user@example.com",
            subject="Test Subject",
            text="Test body",
        )

        assert params.to == "user@example.com"
        assert params.subject == "Test Subject"
        assert params.text == "Test body"
        assert params.html is None
        assert params.cc is None
        assert params.bcc is None

    def test_valid_params_full(self):
        """Test valid parameters with all optional fields."""
        params = OutlookSendParams(
            to="user@example.com",
            subject="Test Subject",
            text="Test body",
            html="<p>Test HTML</p>",
            cc=["cc@example.com"],
            bcc=["bcc@example.com"],
        )

        assert params.to == "user@example.com"
        assert params.html == "<p>Test HTML</p>"
        assert params.cc == ["cc@example.com"]
        assert params.bcc == ["bcc@example.com"]

    def test_invalid_to_email(self):
        """Test validation rejects invalid 'to' email."""
        with pytest.raises(ValueError, match="Invalid email address"):
            OutlookSendParams(
                to="not-an-email",
                subject="Test",
                text="Body",
            )

    def test_invalid_cc_email(self):
        """Test validation rejects invalid CC email."""
        with pytest.raises(ValueError, match="Invalid email address in list"):
            OutlookSendParams(
                to="user@example.com",
                subject="Test",
                text="Body",
                cc=["valid@example.com", "invalid-email"],
            )

    def test_recipient_count_limit_microsoft(self):
        """Test recipient count limit (Microsoft: 150 max)."""
        # Create params with 150 recipients (1 to + 149 cc)
        params = OutlookSendParams(
            to="user@example.com",
            subject="Test",
            text="Body",
            cc=[f"user{i}@example.com" for i in range(149)],
        )

        # Should not raise (exactly 150)
        params.validate_recipient_count()

        # Add one more recipient (151 total)
        params.bcc = ["extra@example.com"]

        # Should raise (exceeds 150)
        with pytest.raises(ValueError, match="exceeds Microsoft limit of 150"):
            params.validate_recipient_count()


class TestMicrosoftAdapter:
    """Test Microsoft adapter scaffolding."""

    @pytest.fixture
    def adapter(self):
        """Create adapter with default config."""
        # Set required env vars
        os.environ["PROVIDER_MICROSOFT_ENABLED"] = "true"
        os.environ["MS_CLIENT_ID"] = "test-client-id"
        os.environ["MICROSOFT_INTERNAL_ONLY"] = "false"

        adapter = MicrosoftAdapter()

        yield adapter

        # Cleanup
        os.environ.pop("PROVIDER_MICROSOFT_ENABLED", None)
        os.environ.pop("MS_CLIENT_ID", None)
        os.environ.pop("MICROSOFT_INTERNAL_ONLY", None)

    def test_adapter_enabled(self, adapter):
        """Test adapter enabled flag."""
        assert adapter.enabled is True
        assert adapter.client_id == "test-client-id"

    def test_adapter_disabled(self):
        """Test adapter disabled when env var is false."""
        os.environ["PROVIDER_MICROSOFT_ENABLED"] = "false"
        adapter = MicrosoftAdapter()

        assert adapter.enabled is False

        os.environ.pop("PROVIDER_MICROSOFT_ENABLED", None)

    def test_list_actions(self, adapter):
        """Test list_actions returns outlook.send definition."""
        actions = adapter.list_actions()

        assert len(actions) == 1
        assert actions[0].id == "outlook.send"
        assert actions[0].name == "Send Outlook Email"
        assert actions[0].provider.value == "microsoft"
        assert actions[0].enabled is True

    def test_preview_valid_params(self, adapter):
        """Test preview with valid parameters."""
        params = {
            "to": "user@example.com",
            "subject": "Test Subject",
            "text": "Test body",
        }

        result = adapter.preview("outlook.send", params)

        assert result["summary"].startswith("Send email to user@example.com")
        assert result["params"] == params
        assert result["digest"]  # Should have computed digest
        assert len(result["warnings"]) == 0  # No warnings when configured

    def test_preview_with_html_and_attachments(self, adapter):
        """Test preview with HTML and attachments."""
        params = {
            "to": "user@example.com",
            "subject": "Test",
            "text": "Body",
            "html": "<p>HTML body</p>",
            "cc": ["cc@example.com"],
            "attachments": [
                {
                    "filename": "test.txt",
                    "content_type": "text/plain",
                    "data": "VGVzdA==",  # "Test" in base64
                }
            ],
        }

        result = adapter.preview("outlook.send", params)

        assert "Format: HTML + plain text" in result["summary"]
        assert "CC: cc@example.com" in result["summary"]
        assert "Attachments: 1" in result["summary"]

    def test_preview_unknown_action(self, adapter):
        """Test preview raises for unknown action."""
        with pytest.raises(ValueError, match="Unknown action: foo.bar"):
            adapter.preview("foo.bar", {})

    def test_internal_only_mode_blocks_external_domain(self):
        """Test internal-only mode blocks external domains."""
        os.environ["PROVIDER_MICROSOFT_ENABLED"] = "true"
        os.environ["MS_CLIENT_ID"] = "test-client-id"
        os.environ["MICROSOFT_INTERNAL_ONLY"] = "true"
        os.environ["MICROSOFT_INTERNAL_ALLOWED_DOMAINS"] = "internal.com"

        adapter = MicrosoftAdapter()

        params = {
            "to": "external@example.com",  # Not in allowed domains
            "subject": "Test",
            "text": "Body",
        }

        # Should raise with structured error
        with pytest.raises(ValueError) as exc_info:
            adapter.preview("outlook.send", params)

        error_msg = str(exc_info.value)
        assert "internal_only_recipient_blocked" in error_msg

        # Cleanup
        os.environ.pop("PROVIDER_MICROSOFT_ENABLED", None)
        os.environ.pop("MS_CLIENT_ID", None)
        os.environ.pop("MICROSOFT_INTERNAL_ONLY", None)
        os.environ.pop("MICROSOFT_INTERNAL_ALLOWED_DOMAINS", None)

    def test_internal_only_mode_allows_internal_domain(self):
        """Test internal-only mode allows internal domains."""
        os.environ["PROVIDER_MICROSOFT_ENABLED"] = "true"
        os.environ["MS_CLIENT_ID"] = "test-client-id"
        os.environ["MICROSOFT_INTERNAL_ONLY"] = "true"
        os.environ["MICROSOFT_INTERNAL_ALLOWED_DOMAINS"] = "internal.com,example.com"

        adapter = MicrosoftAdapter()

        params = {
            "to": "user@internal.com",  # In allowed domains
            "subject": "Test",
            "text": "Body",
        }

        # Should not raise
        result = adapter.preview("outlook.send", params)
        assert result["summary"].startswith("Send email to user@internal.com")

        # Cleanup
        os.environ.pop("PROVIDER_MICROSOFT_ENABLED", None)
        os.environ.pop("MS_CLIENT_ID", None)
        os.environ.pop("MICROSOFT_INTERNAL_ONLY", None)
        os.environ.pop("MICROSOFT_INTERNAL_ALLOWED_DOMAINS", None)

    @pytest.mark.anyio
    async def test_execute_provider_disabled(self, adapter):
        """Test execute raises when provider disabled."""
        adapter.enabled = False

        params = {
            "to": "user@example.com",
            "subject": "Test",
            "text": "Body",
        }

        with pytest.raises(ValueError, match="Microsoft provider is disabled"):
            await adapter.execute("outlook.send", params, "ws_123", "user_456")

    @pytest.mark.anyio
    async def test_execute_rollout_gated(self, adapter):
        """Test execute raises when rollout gate blocks."""
        # Mock rollout gate
        mock_gate = MagicMock()
        mock_gate.allow.return_value = False
        adapter.rollout_gate = mock_gate

        params = {
            "to": "user@example.com",
            "subject": "Test",
            "text": "Body",
        }

        with pytest.raises(ValueError, match="not rolled out to this user"):
            await adapter.execute("outlook.send", params, "ws_123", "user_456")

        # Verify rollout gate was called
        mock_gate.allow.assert_called_once_with("microsoft", {"actor_id": "user_456", "workspace_id": "ws_123"})

    @pytest.mark.anyio
    async def test_execute_stub_response(self, adapter):
        """Test execute returns stub response (Week 1 scaffolding)."""
        params = {
            "to": "user@example.com",
            "subject": "Test Subject",
            "text": "Test body",
        }

        result = await adapter.execute("outlook.send", params, "ws_123", "user_456")

        # Week 1: Returns stub response
        assert result["status"] == "stub"
        assert result["to"] == "user@example.com"
        assert result["subject"] == "Test Subject"
        assert "no Graph API call yet" in result["message"]
        assert "Week 2-3" in result["note"]


class TestMicrosoftConfiguration:
    """Test configuration helper functions."""

    def test_is_configured_true(self):
        """Test is_configured returns True when MS_CLIENT_ID is set."""
        from src.actions.adapters.microsoft import is_configured

        os.environ["MS_CLIENT_ID"] = "test-client-id"
        assert is_configured() is True
        os.environ.pop("MS_CLIENT_ID", None)

    def test_is_configured_false(self):
        """Test is_configured returns False when MS_CLIENT_ID is not set."""
        from src.actions.adapters.microsoft import is_configured

        os.environ.pop("MS_CLIENT_ID", None)
        assert is_configured() is False


class TestMicrosoftBase64Validation:
    """Test base64 validation for attachments and inline images.

    Sprint 54: Compliance Fix #5 - structured errors for invalid base64.
    """

    @pytest.fixture
    def adapter(self):
        """Create adapter with default config."""
        os.environ["PROVIDER_MICROSOFT_ENABLED"] = "true"
        os.environ["MS_CLIENT_ID"] = "test-client-id"
        os.environ["MICROSOFT_INTERNAL_ONLY"] = "false"

        adapter = MicrosoftAdapter()

        yield adapter

        os.environ.pop("PROVIDER_MICROSOFT_ENABLED", None)
        os.environ.pop("MS_CLIENT_ID", None)
        os.environ.pop("MICROSOFT_INTERNAL_ONLY", None)

    def test_preview_invalid_attachment_base64(self, adapter):
        """Test preview raises structured error for invalid attachment base64."""
        params = {
            "to": "user@example.com",
            "subject": "Test",
            "text": "Body",
            "attachments": [
                {
                    "filename": "test.txt",
                    "content_type": "text/plain",
                    "data": "NOT_VALID_BASE64!!!",
                }
            ],
        }

        with pytest.raises(ValueError) as exc_info:
            adapter.preview("outlook.send", params)

        error_msg = str(exc_info.value)
        assert "validation_error_invalid_attachment_data" in error_msg
        assert "decode" in error_msg.lower() or "attachment" in error_msg.lower()
        assert "valid base64" in error_msg.lower()

    def test_preview_invalid_inline_base64(self, adapter):
        """Test preview raises structured error for invalid inline image base64."""
        params = {
            "to": "user@example.com",
            "subject": "Test",
            "text": "Body",
            "html": '<p>Logo: <img src="cid:logo"></p>',
            "inline": [
                {
                    "cid": "logo",
                    "filename": "logo.png",
                    "content_type": "image/png",
                    "data": "INVALID@BASE64#DATA",
                }
            ],
        }

        with pytest.raises(ValueError) as exc_info:
            adapter.preview("outlook.send", params)

        error_msg = str(exc_info.value)
        assert "validation_error_invalid_inline_data" in error_msg
        assert "decode" in error_msg.lower() or "inline" in error_msg.lower()
        assert "valid base64" in error_msg.lower()
