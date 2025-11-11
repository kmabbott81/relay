"""Unit tests for onboarding wizard functionality.

Tests cover:
- Environment variable validation (required vs optional)
- .env.example generation with proper format
- .env.local NOT committed (should be in .gitignore)
- Audit event emission to logs/onboarding_audit.log
- Non-interactive mode for CI
- Validation error messages are helpful
- Uses monkeypatch for env vars
- Mocks file writing to verify output
"""

import json
from unittest.mock import patch

from relay_ai.onboarding.wizard import (
    OPTIONAL_VARS,
    REQUIRED_VARS,
    OnboardingAudit,
    check_optional_vars,
    check_required_vars,
    print_validation_report,
    run_wizard,
    validate_env_var,
    write_env_example,
    write_env_local,
)


class TestEnvVarValidation:
    """Test environment variable validation logic."""

    def test_validate_required_var_missing(self):
        """Test validation fails when required var is missing."""
        is_valid, error = validate_env_var("OPENAI_API_KEY", None, "OpenAI API key")
        assert not is_valid
        assert "OPENAI_API_KEY is not set" in error
        assert "OpenAI API key" in error

    def test_validate_required_var_empty(self):
        """Test validation fails when required var is empty."""
        is_valid, error = validate_env_var("OPENAI_API_KEY", "  ", "OpenAI API key")
        assert not is_valid
        assert "OPENAI_API_KEY is not set" in error

    def test_validate_openai_api_key_valid(self):
        """Test OpenAI API key validation with valid key."""
        is_valid, error = validate_env_var("OPENAI_API_KEY", "sk-test123456", "OpenAI API key")
        assert is_valid
        assert error is None

    def test_validate_openai_api_key_invalid_prefix(self):
        """Test OpenAI API key validation with invalid prefix."""
        is_valid, error = validate_env_var("OPENAI_API_KEY", "invalid-key", "OpenAI API key")
        assert not is_valid
        assert "should start with 'sk-'" in error

    def test_validate_temperature_valid(self):
        """Test temperature validation with valid range."""
        is_valid, error = validate_env_var("OPENAI_TEMPERATURE", "0.7", "Temperature")
        assert is_valid
        assert error is None

        is_valid, error = validate_env_var("OPENAI_TEMPERATURE", "0.0", "Temperature")
        assert is_valid
        assert error is None

        is_valid, error = validate_env_var("OPENAI_TEMPERATURE", "2.0", "Temperature")
        assert is_valid
        assert error is None

    def test_validate_temperature_invalid_range(self):
        """Test temperature validation with invalid range."""
        is_valid, error = validate_env_var("OPENAI_TEMPERATURE", "-0.1", "Temperature")
        assert not is_valid
        assert "between 0.0 and 2.0" in error

        is_valid, error = validate_env_var("OPENAI_TEMPERATURE", "2.1", "Temperature")
        assert not is_valid
        assert "between 0.0 and 2.0" in error

    def test_validate_temperature_invalid_type(self):
        """Test temperature validation with invalid type."""
        is_valid, error = validate_env_var("OPENAI_TEMPERATURE", "not-a-number", "Temperature")
        assert not is_valid
        assert "should be a valid float" in error

    def test_validate_timeout_valid(self):
        """Test timeout validation with valid values."""
        is_valid, error = validate_env_var("OPENAI_CONNECT_TIMEOUT_MS", "30000", "Connect timeout")
        assert is_valid
        assert error is None

    def test_validate_timeout_invalid(self):
        """Test timeout validation with invalid values."""
        is_valid, error = validate_env_var("OPENAI_CONNECT_TIMEOUT_MS", "0", "Connect timeout")
        assert not is_valid
        assert "should be a positive integer" in error

        is_valid, error = validate_env_var("OPENAI_CONNECT_TIMEOUT_MS", "-100", "Connect timeout")
        assert not is_valid
        assert "should be a positive integer" in error

        is_valid, error = validate_env_var("OPENAI_CONNECT_TIMEOUT_MS", "not-a-number", "Connect timeout")
        assert not is_valid
        assert "should be a valid integer" in error

    def test_validate_max_retries_valid(self):
        """Test max retries validation with valid values."""
        is_valid, error = validate_env_var("MAX_RETRIES", "3", "Max retries")
        assert is_valid
        assert error is None

        is_valid, error = validate_env_var("MAX_RETRIES", "0", "Max retries")
        assert is_valid
        assert error is None

    def test_validate_max_retries_invalid(self):
        """Test max retries validation with invalid values."""
        is_valid, error = validate_env_var("MAX_RETRIES", "-1", "Max retries")
        assert not is_valid
        assert "should be a non-negative integer" in error

    def test_validate_retry_jitter_valid(self):
        """Test retry jitter validation with valid range."""
        is_valid, error = validate_env_var("RETRY_JITTER_PCT", "0.2", "Jitter percentage")
        assert is_valid
        assert error is None

        is_valid, error = validate_env_var("RETRY_JITTER_PCT", "0.0", "Jitter percentage")
        assert is_valid
        assert error is None

        is_valid, error = validate_env_var("RETRY_JITTER_PCT", "1.0", "Jitter percentage")
        assert is_valid
        assert error is None

    def test_validate_retry_jitter_invalid(self):
        """Test retry jitter validation with invalid range."""
        is_valid, error = validate_env_var("RETRY_JITTER_PCT", "-0.1", "Jitter percentage")
        assert not is_valid
        assert "between 0.0 and 1.0" in error

        is_valid, error = validate_env_var("RETRY_JITTER_PCT", "1.1", "Jitter percentage")
        assert not is_valid
        assert "between 0.0 and 1.0" in error


class TestCheckRequiredVars:
    """Test checking all required variables."""

    def test_check_required_vars_all_valid(self, monkeypatch, tmp_path):
        """Test all required variables are valid."""
        # Set all required vars
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
        monkeypatch.setenv("CURRENT_REGION", "us-east-1")
        monkeypatch.setenv("TENANT_ID", "test-tenant")

        audit_path = tmp_path / "test_audit.log"
        audit = OnboardingAudit(audit_path)

        results = check_required_vars(audit)

        # All should be valid
        for var_name, (is_valid, error) in results.items():
            assert is_valid, f"{var_name} should be valid but got error: {error}"
            assert error is None

        # Check audit log was written
        assert audit_path.exists()
        with open(audit_path, encoding="utf-8") as f:
            events = [json.loads(line) for line in f]
        assert len(events) == len(REQUIRED_VARS)
        for event in events:
            assert event["event_type"] == "validation"
            assert event["is_set"] is True
            assert event["is_valid"] is True

    def test_check_required_vars_some_missing(self, monkeypatch, tmp_path):
        """Test some required variables are missing."""
        # Set only some required vars
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
        # Missing: CURRENT_REGION, TENANT_ID

        audit_path = tmp_path / "test_audit.log"
        audit = OnboardingAudit(audit_path)

        results = check_required_vars(audit)

        # Check OPENAI_API_KEY is valid
        assert results["OPENAI_API_KEY"][0] is True

        # Check CURRENT_REGION is invalid
        assert results["CURRENT_REGION"][0] is False
        assert "CURRENT_REGION is not set" in results["CURRENT_REGION"][1]

        # Check TENANT_ID is invalid
        assert results["TENANT_ID"][0] is False
        assert "TENANT_ID is not set" in results["TENANT_ID"][1]

    def test_check_required_vars_invalid_api_key(self, monkeypatch, tmp_path):
        """Test invalid API key format."""
        monkeypatch.setenv("OPENAI_API_KEY", "invalid-key")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
        monkeypatch.setenv("CURRENT_REGION", "us-east-1")
        monkeypatch.setenv("TENANT_ID", "test-tenant")

        audit_path = tmp_path / "test_audit.log"
        audit = OnboardingAudit(audit_path)

        results = check_required_vars(audit)

        # API key should be invalid
        assert results["OPENAI_API_KEY"][0] is False
        assert "should start with 'sk-'" in results["OPENAI_API_KEY"][1]


class TestCheckOptionalVars:
    """Test checking optional variables."""

    def test_check_optional_vars_all_defaults(self, tmp_path):
        """Test optional variables use defaults when not set."""
        audit_path = tmp_path / "test_audit.log"
        audit = OnboardingAudit(audit_path)

        results = check_optional_vars(audit)

        # All should have default values and be valid
        for var_name, (value, is_valid, error) in results.items():
            expected_default = OPTIONAL_VARS[var_name][0]
            assert value == expected_default
            assert is_valid
            assert error is None

    def test_check_optional_vars_custom_values(self, monkeypatch, tmp_path):
        """Test optional variables with custom values."""
        monkeypatch.setenv("OPENAI_BASE_URL", "https://custom.openai.com/v1")
        monkeypatch.setenv("OPENAI_MAX_TOKENS", "4000")
        monkeypatch.setenv("OPENAI_TEMPERATURE", "0.9")

        audit_path = tmp_path / "test_audit.log"
        audit = OnboardingAudit(audit_path)

        results = check_optional_vars(audit)

        # Check custom values
        assert results["OPENAI_BASE_URL"][0] == "https://custom.openai.com/v1"
        assert results["OPENAI_MAX_TOKENS"][0] == "4000"
        assert results["OPENAI_TEMPERATURE"][0] == "0.9"

        # All should be valid
        for var_name, (value, is_valid, error) in results.items():
            assert is_valid
            assert error is None

    def test_check_optional_vars_invalid_temperature(self, monkeypatch, tmp_path):
        """Test optional variable with invalid value."""
        monkeypatch.setenv("OPENAI_TEMPERATURE", "5.0")  # Out of range

        audit_path = tmp_path / "test_audit.log"
        audit = OnboardingAudit(audit_path)

        results = check_optional_vars(audit)

        # Temperature should be invalid
        assert results["OPENAI_TEMPERATURE"][0] == "5.0"
        assert results["OPENAI_TEMPERATURE"][1] is False
        assert "between 0.0 and 2.0" in results["OPENAI_TEMPERATURE"][2]


class TestEnvExampleGeneration:
    """Test .env.example file generation."""

    def test_write_env_example_format(self, tmp_path):
        """Test .env.example has correct format."""
        output_path = tmp_path / ".env.example"
        audit_path = tmp_path / "audit.log"
        audit = OnboardingAudit(audit_path)

        write_env_example(output_path, audit)

        assert output_path.exists()

        content = output_path.read_text(encoding="utf-8")

        # Check header
        assert "OpenAI Agents Workflows - Environment Configuration" in content
        assert "Generated:" in content

        # Check all required vars are present
        for var_name, description in REQUIRED_VARS.items():
            assert f"# {description}" in content
            assert f"{var_name}=" in content

        # Check all optional vars are present with defaults
        for var_name, (default_value, description) in OPTIONAL_VARS.items():
            assert f"# {description}" in content
            assert f"# Default: {default_value}" in content
            assert f"{var_name}={default_value}" in content

        # Check audit log
        assert audit_path.exists()
        with open(audit_path, encoding="utf-8") as f:
            events = [json.loads(line) for line in f]
        assert len(events) == 1
        assert events[0]["event_type"] == "config_write"
        assert events[0]["type"] == "env_example"

    def test_write_env_example_creates_parent_dirs(self, tmp_path):
        """Test .env.example creation creates parent directories."""
        output_path = tmp_path / "nested" / "dir" / ".env.example"
        audit_path = tmp_path / "audit.log"
        audit = OnboardingAudit(audit_path)

        write_env_example(output_path, audit)

        assert output_path.exists()
        assert output_path.parent.exists()


class TestEnvLocalGeneration:
    """Test .env.local file generation."""

    def test_write_env_local_non_interactive(self, monkeypatch, tmp_path):
        """Test .env.local generation in non-interactive mode."""
        # Set some env vars
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
        monkeypatch.setenv("CURRENT_REGION", "us-east-1")
        monkeypatch.setenv("TENANT_ID", "test-tenant")

        output_path = tmp_path / ".env.local"
        audit_path = tmp_path / "audit.log"
        audit = OnboardingAudit(audit_path)

        result = write_env_local(output_path, audit, interactive=False)

        assert result is True
        assert output_path.exists()

        content = output_path.read_text(encoding="utf-8")

        # Check header with warning
        assert "WARNING: Never commit this file!" in content
        assert "Contains secrets" in content

        # Check current values are written
        assert "OPENAI_API_KEY=sk-test123456" in content
        assert "OPENAI_MODEL=gpt-4o" in content
        assert "CURRENT_REGION=us-east-1" in content
        assert "TENANT_ID=test-tenant" in content

        # Check audit log
        assert audit_path.exists()
        with open(audit_path, encoding="utf-8") as f:
            events = [json.loads(line) for line in f]
        assert len(events) == 1
        assert events[0]["event_type"] == "config_write"
        assert events[0]["type"] == "env_local"

    def test_write_env_local_interactive_yes(self, monkeypatch, tmp_path):
        """Test .env.local generation in interactive mode with 'y' response."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456")

        output_path = tmp_path / ".env.local"
        audit_path = tmp_path / "audit.log"
        audit = OnboardingAudit(audit_path)

        # Mock user input
        with patch("builtins.input", return_value="y"):
            result = write_env_local(output_path, audit, interactive=True)

        assert result is True
        assert output_path.exists()

    def test_write_env_local_interactive_no(self, tmp_path):
        """Test .env.local skipped in interactive mode with 'n' response."""
        output_path = tmp_path / ".env.local"
        audit_path = tmp_path / "audit.log"
        audit = OnboardingAudit(audit_path)

        # Mock user input
        with patch("builtins.input", return_value="n"):
            result = write_env_local(output_path, audit, interactive=True)

        assert result is False
        assert not output_path.exists()

    def test_write_env_local_should_not_be_committed(self, tmp_path):
        """Test .env.local has warning about not committing."""
        output_path = tmp_path / ".env.local"
        audit_path = tmp_path / "audit.log"
        audit = OnboardingAudit(audit_path)

        write_env_local(output_path, audit, interactive=False)

        content = output_path.read_text(encoding="utf-8")

        # Strong warning about not committing
        assert "WARNING" in content
        assert "Never commit this file" in content
        assert "secrets" in content.lower()


class TestAuditLogging:
    """Test audit logging functionality."""

    def test_audit_log_event_format(self, tmp_path):
        """Test audit events have correct format."""
        audit_path = tmp_path / "audit.log"
        audit = OnboardingAudit(audit_path)

        audit.log_event("test_event", {"key1": "value1", "key2": 123})

        assert audit_path.exists()

        with open(audit_path, encoding="utf-8") as f:
            line = f.readline()
            event = json.loads(line)

        assert event["event_type"] == "test_event"
        assert event["key1"] == "value1"
        assert event["key2"] == 123
        assert "timestamp" in event
        assert event["timestamp"].endswith("Z")

    def test_audit_log_multiple_events(self, tmp_path):
        """Test multiple audit events are appended."""
        audit_path = tmp_path / "audit.log"
        audit = OnboardingAudit(audit_path)

        audit.log_event("event1", {"data": "first"})
        audit.log_event("event2", {"data": "second"})
        audit.log_event("event3", {"data": "third"})

        with open(audit_path, encoding="utf-8") as f:
            events = [json.loads(line) for line in f]

        assert len(events) == 3
        assert events[0]["event_type"] == "event1"
        assert events[1]["event_type"] == "event2"
        assert events[2]["event_type"] == "event3"

    def test_audit_creates_parent_dirs(self, tmp_path):
        """Test audit logger creates parent directories."""
        audit_path = tmp_path / "nested" / "logs" / "audit.log"
        audit = OnboardingAudit(audit_path)

        audit.log_event("test", {})

        assert audit_path.exists()
        assert audit_path.parent.exists()


class TestValidationReport:
    """Test validation report printing."""

    def test_print_validation_report_all_valid(self, monkeypatch, tmp_path, capsys):
        """Test validation report when all variables are valid."""
        # Set all required vars
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
        monkeypatch.setenv("CURRENT_REGION", "us-east-1")
        monkeypatch.setenv("TENANT_ID", "test-tenant")

        audit_path = tmp_path / "audit.log"
        audit = OnboardingAudit(audit_path)

        required_results = check_required_vars(audit)
        optional_results = check_optional_vars(audit)

        all_valid = print_validation_report(required_results, optional_results)

        assert all_valid is True

        captured = capsys.readouterr()
        assert "ENVIRONMENT VALIDATION REPORT" in captured.out
        assert "[OK] All required variables are valid!" in captured.out
        assert "[FAIL]" not in captured.out

    def test_print_validation_report_some_missing(self, monkeypatch, tmp_path, capsys):
        """Test validation report when some variables are missing."""
        # Set only some required vars
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456")
        # Missing: OPENAI_MODEL, CURRENT_REGION, TENANT_ID

        audit_path = tmp_path / "audit.log"
        audit = OnboardingAudit(audit_path)

        required_results = check_required_vars(audit)
        optional_results = check_optional_vars(audit)

        all_valid = print_validation_report(required_results, optional_results)

        assert all_valid is False

        captured = capsys.readouterr()
        assert "[FAIL] Some required variables are missing or invalid" in captured.out
        assert "[FAIL]" in captured.out


class TestWizardIntegration:
    """Integration tests for the full wizard."""

    def test_run_wizard_non_interactive_success(self, monkeypatch, tmp_path):
        """Test wizard in non-interactive mode with valid config."""
        # Set all required vars
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
        monkeypatch.setenv("CURRENT_REGION", "us-east-1")
        monkeypatch.setenv("TENANT_ID", "test-tenant")

        # Mock the project root to use tmp_path
        with patch("src.onboarding.wizard.Path") as mock_path:
            mock_path.return_value.parent.parent.parent = tmp_path

            result = run_wizard(interactive=False)

        assert result is True

    def test_run_wizard_non_interactive_missing_vars(self, monkeypatch, tmp_path):
        """Test wizard in non-interactive mode with missing vars."""
        # Only set some required vars
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456")

        # Mock the project root to use tmp_path
        with patch("src.onboarding.wizard.Path") as mock_path:
            mock_path.return_value.parent.parent.parent = tmp_path

            result = run_wizard(interactive=False)

        assert result is False

    def test_run_wizard_emits_audit_events(self, monkeypatch, tmp_path):
        """Test wizard emits audit events."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
        monkeypatch.setenv("CURRENT_REGION", "us-east-1")
        monkeypatch.setenv("TENANT_ID", "test-tenant")

        # Mock the project root to use tmp_path
        with patch("src.onboarding.wizard.Path") as mock_path:
            mock_path.return_value.parent.parent.parent = tmp_path

            run_wizard(interactive=False)

        audit_log = tmp_path / "logs" / "onboarding_audit.log"
        assert audit_log.exists()

        with open(audit_log, encoding="utf-8") as f:
            events = [json.loads(line) for line in f]

        # Should have: wizard_start, validation events, config_write, wizard_complete
        event_types = [e["event_type"] for e in events]
        assert "wizard_start" in event_types
        assert "validation" in event_types
        assert "config_write" in event_types
        assert "wizard_complete" in event_types


class TestHelpfulErrorMessages:
    """Test that error messages are helpful and actionable."""

    def test_missing_api_key_error_is_helpful(self):
        """Test missing API key error provides helpful message."""
        is_valid, error = validate_env_var("OPENAI_API_KEY", None, "OpenAI API key for LLM inference")
        assert not is_valid
        assert "OPENAI_API_KEY is not set" in error
        assert "OpenAI API key for LLM inference" in error

    def test_invalid_api_key_error_is_helpful(self):
        """Test invalid API key error provides helpful message."""
        is_valid, error = validate_env_var("OPENAI_API_KEY", "wrong-prefix-key", "OpenAI API key")
        assert not is_valid
        assert "should start with 'sk-'" in error

    def test_invalid_temperature_error_is_helpful(self):
        """Test invalid temperature error provides helpful message."""
        is_valid, error = validate_env_var("OPENAI_TEMPERATURE", "3.0", "Temperature")
        assert not is_valid
        assert "should be between 0.0 and 2.0" in error

    def test_invalid_timeout_error_is_helpful(self):
        """Test invalid timeout error provides helpful message."""
        is_valid, error = validate_env_var("OPENAI_CONNECT_TIMEOUT_MS", "not-a-number", "Connect timeout")
        assert not is_valid
        assert "should be a valid integer" in error
