"""Interactive onboarding wizard for OpenAI Agents Workflows.

Validates environment configuration, writes .env.example, and guides setup.
Emits audit events to stdout and logs/onboarding_audit.log.
"""

import argparse
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


# Required environment variables
REQUIRED_VARS = {
    "OPENAI_API_KEY": "OpenAI API key for LLM inference",
    "OPENAI_MODEL": "Model to use (e.g., gpt-4o, gpt-4o-mini)",
    "CURRENT_REGION": "Current deployment region (e.g., us-east-1, us-west-2)",
    "TENANT_ID": "Tenant identifier for multi-tenancy",
}

# Optional environment variables with defaults
OPTIONAL_VARS = {
    "OPENAI_BASE_URL": ("https://api.openai.com/v1", "OpenAI API base URL"),
    "OPENAI_MAX_TOKENS": ("2000", "Maximum tokens per request"),
    "OPENAI_TEMPERATURE": ("0.7", "Temperature for generation (0.0-2.0)"),
    "OPENAI_CONNECT_TIMEOUT_MS": ("30000", "Connection timeout in milliseconds"),
    "OPENAI_READ_TIMEOUT_MS": ("60000", "Read timeout in milliseconds"),
    "MAX_RETRIES": ("3", "Maximum retry attempts for API calls"),
    "RETRY_BASE_MS": ("400", "Base retry delay in milliseconds"),
    "RETRY_JITTER_PCT": ("0.2", "Jitter percentage for retries (0.0-1.0)"),
    "FEATURE_MULTI_REGION": ("false", "Enable multi-region deployment"),
}

# Configure logging
logger = logging.getLogger(__name__)


class OnboardingAudit:
    """Audit logger for onboarding events."""

    def __init__(self, log_path: Path):
        """
        Initialize audit logger.

        Args:
            log_path: Path to audit log file
        """
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_event(self, event_type: str, details: dict):
        """
        Log an audit event to stdout and file.

        Args:
            event_type: Type of event (e.g., 'validation', 'config_write')
            details: Event details dictionary
        """
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": event_type,
            **details,
        }

        # Log to stdout
        print(f"[AUDIT] {json.dumps(event)}")

        # Log to file
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")


def validate_env_var(name: str, value: Optional[str], description: str) -> tuple[bool, Optional[str]]:
    """
    Validate an environment variable.

    Args:
        name: Variable name
        value: Variable value (None if not set)
        description: Variable description

    Returns:
        Tuple of (is_valid, error_message)
    """
    if value is None or value.strip() == "":
        return False, f"{name} is not set. Required: {description}"

    # Specific validations
    if name == "OPENAI_API_KEY":
        if not value.startswith("sk-"):
            return False, f"{name} should start with 'sk-'"

    if name == "OPENAI_TEMPERATURE":
        try:
            temp = float(value)
            if temp < 0.0 or temp > 2.0:
                return False, f"{name} should be between 0.0 and 2.0"
        except ValueError:
            return False, f"{name} should be a valid float"

    if name.endswith("_TIMEOUT_MS"):
        try:
            timeout = int(value)
            if timeout <= 0:
                return False, f"{name} should be a positive integer"
        except ValueError:
            return False, f"{name} should be a valid integer"

    if name == "MAX_RETRIES":
        try:
            retries = int(value)
            if retries < 0:
                return False, f"{name} should be a non-negative integer"
        except ValueError:
            return False, f"{name} should be a valid integer"

    if name == "RETRY_JITTER_PCT":
        try:
            jitter = float(value)
            if jitter < 0.0 or jitter > 1.0:
                return False, f"{name} should be between 0.0 and 1.0"
        except ValueError:
            return False, f"{name} should be a valid float"

    return True, None


def check_required_vars(audit: OnboardingAudit) -> dict[str, tuple[bool, Optional[str]]]:
    """
    Check all required environment variables.

    Args:
        audit: Audit logger

    Returns:
        Dictionary mapping variable names to (is_valid, error_message)
    """
    results = {}

    for var_name, description in REQUIRED_VARS.items():
        value = os.getenv(var_name)
        is_valid, error = validate_env_var(var_name, value, description)
        results[var_name] = (is_valid, error)

        audit.log_event(
            "validation",
            {
                "variable": var_name,
                "is_set": value is not None,
                "is_valid": is_valid,
                "error": error,
            },
        )

    return results


def check_optional_vars(audit: OnboardingAudit) -> dict[str, tuple[str, bool, Optional[str]]]:
    """
    Check all optional environment variables.

    Args:
        audit: Audit logger

    Returns:
        Dictionary mapping variable names to (value, is_valid, error_message)
    """
    results = {}

    for var_name, (default_value, description) in OPTIONAL_VARS.items():
        value = os.getenv(var_name, default_value)
        is_valid, error = validate_env_var(var_name, value, description)
        results[var_name] = (value, is_valid, error)

        audit.log_event(
            "validation",
            {
                "variable": var_name,
                "is_set": os.getenv(var_name) is not None,
                "using_default": os.getenv(var_name) is None,
                "is_valid": is_valid,
                "error": error,
            },
        )

    return results


def write_env_example(output_path: Path, audit: OnboardingAudit):
    """
    Write .env.example file with all variables and descriptions.

    Args:
        output_path: Path to write .env.example
        audit: Audit logger
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# OpenAI Agents Workflows - Environment Configuration\n")
        f.write(f"# Generated: {datetime.utcnow().isoformat()}Z\n\n")

        f.write("# Required Variables\n")
        for var_name, description in REQUIRED_VARS.items():
            f.write(f"# {description}\n")
            f.write(f"{var_name}=\n\n")

        f.write("# Optional Variables (with defaults)\n")
        for var_name, (default_value, description) in OPTIONAL_VARS.items():
            f.write(f"# {description}\n")
            f.write(f"# Default: {default_value}\n")
            f.write(f"{var_name}={default_value}\n\n")

    audit.log_event("config_write", {"file": str(output_path), "type": "env_example"})
    print(f"[OK] Written: {output_path}")


def write_env_local(output_path: Path, audit: OnboardingAudit, interactive: bool = True) -> bool:
    """
    Optionally write .env.local file (never committed).

    Args:
        output_path: Path to write .env.local
        audit: Audit logger
        interactive: Whether to prompt user for confirmation

    Returns:
        True if file was written, False otherwise
    """
    if interactive:
        response = input(f"\nWrite .env.local to {output_path}? (y/n): ").lower().strip()
        if response != "y":
            print("Skipped writing .env.local")
            return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# OpenAI Agents Workflows - Local Environment Configuration\n")
        f.write(f"# Generated: {datetime.utcnow().isoformat()}Z\n")
        f.write("# WARNING: Never commit this file! Contains secrets.\n\n")

        f.write("# Required Variables\n")
        for var_name, description in REQUIRED_VARS.items():
            current_value = os.getenv(var_name, "")
            f.write(f"# {description}\n")
            f.write(f"{var_name}={current_value}\n\n")

        f.write("# Optional Variables\n")
        for var_name, (default_value, description) in OPTIONAL_VARS.items():
            current_value = os.getenv(var_name, default_value)
            f.write(f"# {description}\n")
            f.write(f"{var_name}={current_value}\n\n")

    audit.log_event("config_write", {"file": str(output_path), "type": "env_local"})
    print(f"[OK] Written: {output_path}")
    print("[WARNING] Make sure .env.local is in your .gitignore!")
    return True


def print_validation_report(
    required_results: dict[str, tuple[bool, Optional[str]]],
    optional_results: dict[str, tuple[str, bool, Optional[str]]],
):
    """
    Print validation report to console.

    Args:
        required_results: Results from check_required_vars
        optional_results: Results from check_optional_vars
    """
    print("\n" + "=" * 70)
    print("ENVIRONMENT VALIDATION REPORT")
    print("=" * 70)

    # Required variables
    print("\nRequired Variables:")
    all_valid = True
    for var_name, (is_valid, error) in required_results.items():
        status = "[OK]" if is_valid else "[FAIL]"
        print(f"  {status} {var_name}")
        if error:
            print(f"     Error: {error}")
            all_valid = False

    # Optional variables
    print("\nOptional Variables:")
    for var_name, (value, is_valid, error) in optional_results.items():
        status = "[OK]" if is_valid else "[WARN]"
        is_default = os.getenv(var_name) is None
        default_marker = " (using default)" if is_default else ""
        print(f"  {status} {var_name}{default_marker}")
        if error:
            print(f"     Warning: {error}")

    print("\n" + "=" * 70)

    if all_valid:
        print("[OK] All required variables are valid!")
    else:
        print("[FAIL] Some required variables are missing or invalid.")

    return all_valid


def print_next_steps(all_valid: bool):
    """
    Print next steps guidance.

    Args:
        all_valid: Whether all required variables are valid
    """
    print("\n" + "=" * 70)
    print("NEXT STEPS")
    print("=" * 70)

    if not all_valid:
        print("\n1. Set missing/invalid environment variables:")
        print("   - Edit .env.local or set in your shell")
        print("   - See docs/.env.example for reference")
        print("\n2. Re-run wizard: python -m src.onboarding.wizard")
    else:
        print("\n[OK] Environment is configured! You can now:")
        print("\n1. Run example workflows:")
        print("   - Weekly report: python -m src.workflows.examples.weekly_report_pack --dry-run")
        print("   - Meeting brief: python -m src.workflows.examples.meeting_transcript_brief --dry-run")
        print("   - Inbox sweep: python -m src.workflows.examples.inbox_drive_sweep --dry-run")
        print("\n2. View dashboards:")
        print("   - streamlit run dashboards/app.py")
        print("\n3. Check documentation:")
        print("   - See docs/.env.example for all configuration options")

    print("\n" + "=" * 70)


def run_wizard(interactive: bool = True) -> bool:
    """
    Run the onboarding wizard.

    Args:
        interactive: Whether to run in interactive mode (prompts user)

    Returns:
        True if all required variables are valid, False otherwise
    """
    print("=" * 70)
    print("OpenAI Agents Workflows - Onboarding Wizard")
    print("=" * 70)

    # Initialize audit logger
    project_root = Path(__file__).parent.parent.parent
    audit_path = project_root / "logs" / "onboarding_audit.log"
    audit = OnboardingAudit(audit_path)

    audit.log_event("wizard_start", {"interactive": interactive})

    # Check required variables
    print("\n🔍 Checking required environment variables...")
    required_results = check_required_vars(audit)

    # Check optional variables
    print("🔍 Checking optional environment variables...")
    optional_results = check_optional_vars(audit)

    # Print validation report
    all_valid = print_validation_report(required_results, optional_results)

    # Write .env.example
    print("\n📝 Writing configuration files...")
    env_example_path = project_root / "docs" / ".env.example"
    write_env_example(env_example_path, audit)

    # Optionally write .env.local
    if interactive:
        env_local_path = project_root / ".env.local"
        write_env_local(env_local_path, audit, interactive=True)

    # Print next steps
    print_next_steps(all_valid)

    audit.log_event("wizard_complete", {"all_valid": all_valid})

    return all_valid


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="OpenAI Agents Workflows - Onboarding Wizard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without user prompts (for CI/automation)",
    )

    args = parser.parse_args()

    try:
        success = run_wizard(interactive=not args.non_interactive)
        exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Wizard failed: {e}", exc_info=True)
        print(f"\n[ERROR] {e}")
        exit(1)


if __name__ == "__main__":
    main()
