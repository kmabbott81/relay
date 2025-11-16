"""Environment variable validation module for OpenAI Agents Workflows.

This module validates all environment variables required for the system to run correctly.
It checks for required variables, validates enum values, numeric ranges, and path accessibility.

Usage:
    As a CLI tool:
        python -m src.config.validate
        python -m src.config.validate --strict

    As a module:
        from relay_ai.config import validate_config
        success, errors, warnings = validate_config()
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


class ValidationError:
    """Represents a validation error."""

    def __init__(self, variable: str, message: str, is_warning: bool = False):
        self.variable = variable
        self.message = message
        self.is_warning = is_warning

    def __str__(self) -> str:
        prefix = "WARNING" if self.is_warning else "ERROR"
        return f"[{prefix}] {self.variable}: {self.message}"


class ConfigValidator:
    """Validates environment configuration."""

    # Valid enum values
    VALID_ENVS = ["development", "staging", "production"]
    VALID_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    VALID_RATE_LIMIT_STORAGE = ["memory", "redis"]
    VALID_DATABASE_TYPES = ["postgresql", "mongodb", "sqlite"]
    VALID_URG_DB_TYPES = ["neo4j", "sqlite", "memory"]
    VALID_METRICS_PROVIDERS = ["prometheus", "datadog", "cloudwatch"]
    VALID_TRACING_PROVIDERS = ["jaeger", "zipkin", "datadog"]
    VALID_JAEGER_SAMPLER_TYPES = ["const", "probabilistic", "ratelimiting", "remote"]

    # Required variables (minimum set)
    REQUIRED_VARS = ["ENV", "TENANT_ID", "REDIS_URL"]

    # Production-required secrets
    PRODUCTION_SECRETS = [
        "JWT_SECRET_KEY",
        "ENCRYPTION_KEY",
        "OPENAI_API_KEY",
    ]

    # Default values that should be changed in production
    UNSAFE_DEFAULTS = {
        "JWT_SECRET_KEY": "your-super-secret-jwt-key-change-this-in-production",
        "DASHBOARD_PASSWORD": "change-this-password",
    }

    def __init__(self, strict: bool = False):
        self.strict = strict
        self.errors: list[ValidationError] = []
        self.warnings: list[ValidationError] = []

    def add_error(self, variable: str, message: str) -> None:
        """Add a validation error."""
        self.errors.append(ValidationError(variable, message, is_warning=False))

    def add_warning(self, variable: str, message: str) -> None:
        """Add a validation warning."""
        warning = ValidationError(variable, message, is_warning=True)
        if self.strict:
            self.errors.append(warning)
        else:
            self.warnings.append(warning)

    def get_env(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get environment variable value."""
        return os.getenv(key, default)

    def validate_required_vars(self) -> None:
        """Validate that required environment variables are present."""
        for var in self.REQUIRED_VARS:
            value = self.get_env(var)
            if not value:
                self.add_error(var, f"Required variable '{var}' is not set")

    def validate_env(self) -> None:
        """Validate ENV variable."""
        env = self.get_env("ENV")
        if env and env not in self.VALID_ENVS:
            self.add_error(
                "ENV",
                f"Invalid value '{env}'. Must be one of: {', '.join(self.VALID_ENVS)}",
            )

    def validate_log_level(self) -> None:
        """Validate LOG_LEVEL variable."""
        log_level = self.get_env("LOG_LEVEL")
        if log_level and log_level not in self.VALID_LOG_LEVELS:
            self.add_warning(
                "LOG_LEVEL",
                f"Invalid value '{log_level}'. Expected one of: {', '.join(self.VALID_LOG_LEVELS)}",
            )

    def validate_numeric(
        self,
        var_name: str,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        required: bool = False,
        is_int: bool = False,
    ) -> None:
        """Validate numeric environment variable."""
        value = self.get_env(var_name)

        if not value:
            if required:
                self.add_error(var_name, "Required numeric variable is not set")
            return

        try:
            num_value = int(value) if is_int else float(value)

            if min_value is not None and num_value < min_value:
                self.add_error(var_name, f"Value {num_value} is below minimum {min_value}")

            if max_value is not None and num_value > max_value:
                self.add_error(var_name, f"Value {num_value} exceeds maximum {max_value}")

        except ValueError:
            self.add_error(var_name, f"Invalid numeric value '{value}' (expected {'integer' if is_int else 'number'})")

    def validate_boolean(self, var_name: str) -> None:
        """Validate boolean environment variable."""
        value = self.get_env(var_name)
        if value and value.lower() not in ["true", "false", "1", "0", "yes", "no"]:
            self.add_warning(
                var_name,
                f"Invalid boolean value '{value}'. Expected: true/false, 1/0, yes/no",
            )

    def validate_port(self, var_name: str, required: bool = False) -> None:
        """Validate port number."""
        self.validate_numeric(var_name, min_value=1, max_value=65535, required=required, is_int=True)

    def validate_url(self, var_name: str, required: bool = False) -> None:
        """Validate URL format."""
        value = self.get_env(var_name)

        if not value:
            if required:
                self.add_error(var_name, "Required URL is not set")
            return

        try:
            parsed = urlparse(value)
            if not parsed.scheme or not parsed.netloc:
                self.add_error(var_name, f"Invalid URL format '{value}' (missing scheme or netloc)")
        except Exception as e:
            self.add_error(var_name, f"Invalid URL format '{value}': {e}")

    def validate_path(self, var_name: str, must_exist: bool = False, can_create: bool = True) -> None:
        """Validate path variable."""
        value = self.get_env(var_name)
        if not value:
            return

        path = Path(value)

        if must_exist and not path.exists():
            self.add_error(var_name, f"Path does not exist: {value}")
            return

        if can_create and not path.exists():
            try:
                # Check if parent directory exists or can be created
                parent = path.parent
                if not parent.exists():
                    # Test if we can create the parent directory
                    parent.mkdir(parents=True, exist_ok=True)
                    # Clean up test directory if we just created it
                    if not any(parent.iterdir()):
                        parent.rmdir()
            except (OSError, PermissionError) as e:
                self.add_error(var_name, f"Cannot create path '{value}': {e}")

    def validate_production_secrets(self) -> None:
        """Validate that production secrets are properly configured."""
        env = self.get_env("ENV")
        if env != "production":
            return

        for secret in self.PRODUCTION_SECRETS:
            value = self.get_env(secret)
            if not value:
                self.add_warning(
                    secret,
                    f"Production secret '{secret}' is not set. This may cause runtime errors.",
                )

    def validate_unsafe_defaults(self) -> None:
        """Warn about unsafe default values in production."""
        env = self.get_env("ENV")
        if env != "production":
            return

        for var, unsafe_value in self.UNSAFE_DEFAULTS.items():
            value = self.get_env(var)
            if value == unsafe_value:
                self.add_warning(
                    var,
                    f"Using default value in production. Change '{var}' for security.",
                )

    def validate_redis_url(self) -> None:
        """Validate Redis URL."""
        redis_url = self.get_env("REDIS_URL")
        if not redis_url:
            return

        if not redis_url.startswith(("redis://", "rediss://")):
            self.add_error(
                "REDIS_URL",
                f"Invalid Redis URL format '{redis_url}'. Must start with redis:// or rediss://",
            )

    def validate_rate_limits(self) -> None:
        """Validate rate limit configuration."""
        # QPS limits must be positive
        qps_vars = [
            "GLOBAL_QPS_LIMIT",
            "TEAM_QPS_LIMIT",
            "TENANT_QPS_LIMIT",
            "USER_QPS_LIMIT",
        ]
        for var in qps_vars:
            self.validate_numeric(var, min_value=0.1)

        # QPM and QPH limits
        qpm_vars = ["GLOBAL_QPM_LIMIT", "TEAM_QPM_LIMIT", "TENANT_QPM_LIMIT", "USER_QPM_LIMIT"]
        for var in qpm_vars:
            self.validate_numeric(var, min_value=1, is_int=True)

        # Validate rate limit storage backend
        storage = self.get_env("RATE_LIMIT_STORAGE")
        if storage and storage not in self.VALID_RATE_LIMIT_STORAGE:
            self.add_error(
                "RATE_LIMIT_STORAGE",
                f"Invalid value '{storage}'. Must be one of: {', '.join(self.VALID_RATE_LIMIT_STORAGE)}",
            )

    def validate_budgets(self) -> None:
        """Validate budget configuration."""
        budget_vars = [
            "DAILY_BUDGET_LIMIT",
            "MONTHLY_BUDGET_LIMIT",
            "TENANT_DAILY_BUDGET_LIMIT",
            "TENANT_MONTHLY_BUDGET_LIMIT",
        ]
        for var in budget_vars:
            self.validate_numeric(var, min_value=0.01)

        # Cost per operation
        cost_vars = ["COST_PER_API_CALL", "COST_PER_TOKEN", "COST_PER_EMBEDDING"]
        for var in cost_vars:
            self.validate_numeric(var, min_value=0)

        # Threshold percentages (0-100)
        threshold_vars = ["BUDGET_WARNING_THRESHOLD", "BUDGET_CRITICAL_THRESHOLD"]
        for var in threshold_vars:
            self.validate_numeric(var, min_value=0, max_value=100)

    def validate_worker_settings(self) -> None:
        """Validate worker and queue configuration."""
        self.validate_numeric("WORKER_CONCURRENCY", min_value=1, is_int=True)
        self.validate_numeric("MAX_WORKERS", min_value=1, is_int=True)
        self.validate_numeric("MIN_WORKERS", min_value=1, is_int=True)

        # Check that MIN_WORKERS <= MAX_WORKERS
        min_workers = self.get_env("MIN_WORKERS")
        max_workers = self.get_env("MAX_WORKERS")
        if min_workers and max_workers:
            try:
                if int(min_workers) > int(max_workers):
                    self.add_error(
                        "MIN_WORKERS",
                        f"MIN_WORKERS ({min_workers}) cannot exceed MAX_WORKERS ({max_workers})",
                    )
            except ValueError:
                pass  # Already caught by validate_numeric

        # Timeouts
        timeout_vars = ["TASK_TIMEOUT", "LONG_TASK_TIMEOUT", "DEFAULT_TASK_TTL"]
        for var in timeout_vars:
            self.validate_numeric(var, min_value=1, is_int=True)

        # Queue settings
        self.validate_numeric("QUEUE_MAX_SIZE", min_value=1, is_int=True)
        self.validate_numeric("QUEUE_POLL_INTERVAL", min_value=0.1)

    def validate_security_settings(self) -> None:
        """Validate security and RBAC configuration."""
        # Token expiration times
        self.validate_numeric("ACCESS_TOKEN_EXPIRE", min_value=60, is_int=True)
        self.validate_numeric("REFRESH_TOKEN_EXPIRE", min_value=3600, is_int=True)

        # Password policy
        self.validate_numeric("MIN_PASSWORD_LENGTH", min_value=8, max_value=128, is_int=True)
        self.validate_boolean("REQUIRE_SPECIAL_CHARS")
        self.validate_boolean("REQUIRE_NUMBERS")
        self.validate_boolean("REQUIRE_UPPERCASE")

        # Session settings
        self.validate_numeric("SESSION_TIMEOUT", min_value=60, is_int=True)
        self.validate_numeric("MAX_CONCURRENT_SESSIONS", min_value=1, is_int=True)

        # Config paths
        config_paths = [
            "TEAMS_CONFIG_PATH",
            "WORKSPACES_CONFIG_PATH",
            "DELEGATIONS_CONFIG_PATH",
            "PERMISSIONS_CONFIG_PATH",
        ]
        for var in config_paths:
            self.validate_path(var, must_exist=False, can_create=True)

    def validate_health_monitoring(self) -> None:
        """Validate health check and monitoring configuration."""
        self.validate_boolean("HEALTH_CHECK_ENABLED")
        self.validate_port("HEALTH_CHECK_PORT")

        # Probe settings
        probe_vars = [
            "LIVENESS_PROBE_INTERVAL",
            "READINESS_PROBE_INTERVAL",
            "LIVENESS_PROBE_TIMEOUT",
            "READINESS_PROBE_TIMEOUT",
        ]
        for var in probe_vars:
            self.validate_numeric(var, min_value=1, is_int=True)

        self.validate_numeric("LIVENESS_PROBE_FAILURE_THRESHOLD", min_value=1, is_int=True)
        self.validate_numeric("READINESS_PROBE_FAILURE_THRESHOLD", min_value=1, is_int=True)

        # Metrics
        self.validate_boolean("METRICS_ENABLED")
        self.validate_port("METRICS_PORT")

        metrics_provider = self.get_env("METRICS_PROVIDER")
        if metrics_provider and metrics_provider not in self.VALID_METRICS_PROVIDERS:
            self.add_warning(
                "METRICS_PROVIDER",
                f"Unknown provider '{metrics_provider}'. Common values: {', '.join(self.VALID_METRICS_PROVIDERS)}",
            )

        # Tracing
        self.validate_boolean("TRACING_ENABLED")
        tracing_provider = self.get_env("TRACING_PROVIDER")
        if tracing_provider and tracing_provider not in self.VALID_TRACING_PROVIDERS:
            self.add_warning(
                "TRACING_PROVIDER",
                f"Unknown provider '{tracing_provider}'. Common values: {', '.join(self.VALID_TRACING_PROVIDERS)}",
            )

        self.validate_port("JAEGER_AGENT_PORT")

        sampler_type = self.get_env("JAEGER_SAMPLER_TYPE")
        if sampler_type and sampler_type not in self.VALID_JAEGER_SAMPLER_TYPES:
            self.add_warning(
                "JAEGER_SAMPLER_TYPE",
                f"Unknown sampler '{sampler_type}'. Valid values: {', '.join(self.VALID_JAEGER_SAMPLER_TYPES)}",
            )

        # Sampler param (0.0 to 1.0 for probabilistic)
        sampler_param = self.get_env("JAEGER_SAMPLER_PARAM")
        if sampler_param and sampler_type == "probabilistic":
            self.validate_numeric("JAEGER_SAMPLER_PARAM", min_value=0.0, max_value=1.0)

    def validate_dashboard(self) -> None:
        """Validate dashboard configuration."""
        self.validate_boolean("DASHBOARD_ENABLED")
        self.validate_port("DASHBOARD_PORT")
        self.validate_numeric("DASHBOARD_REFRESH_INTERVAL", min_value=1, is_int=True)

        # Data retention
        self.validate_numeric("DASHBOARD_METRICS_RETENTION_DAYS", min_value=1, is_int=True)
        self.validate_numeric("DASHBOARD_LOGS_RETENTION_DAYS", min_value=1, is_int=True)

    def validate_paths(self) -> None:
        """Validate all path configurations."""
        path_vars = ["DATA_PATH", "LOGS_PATH", "CACHE_PATH", "TEMP_PATH", "BACKUP_PATH"]
        for var in path_vars:
            self.validate_path(var, must_exist=False, can_create=True)

    def validate_database(self) -> None:
        """Validate database configuration."""
        db_type = self.get_env("DATABASE_TYPE")
        if db_type and db_type not in self.VALID_DATABASE_TYPES:
            self.add_warning(
                "DATABASE_TYPE",
                f"Unknown database type '{db_type}'. Common values: {', '.join(self.VALID_DATABASE_TYPES)}",
            )

        # PostgreSQL settings
        if db_type == "postgresql":
            self.validate_port("DATABASE_PORT")
            self.validate_numeric("DATABASE_POOL_SIZE", min_value=1, is_int=True)
            self.validate_numeric("DATABASE_MAX_OVERFLOW", min_value=0, is_int=True)

        # MongoDB settings
        mongodb_uri = self.get_env("MONGODB_URI")
        if mongodb_uri:
            self.validate_url("MONGODB_URI")
            self.validate_numeric("MONGODB_MAX_POOL_SIZE", min_value=1, is_int=True)

        # URG (graph database) settings
        urg_db_type = self.get_env("URG_DB_TYPE")
        if urg_db_type and urg_db_type not in self.VALID_URG_DB_TYPES:
            self.add_warning(
                "URG_DB_TYPE",
                f"Unknown URG database type '{urg_db_type}'. Valid values: {', '.join(self.VALID_URG_DB_TYPES)}",
            )

    def validate_autoscaling(self) -> None:
        """Validate auto-scaling configuration."""
        self.validate_boolean("AUTO_SCALING_ENABLED")
        self.validate_numeric("MIN_INSTANCES", min_value=1, is_int=True)
        self.validate_numeric("MAX_INSTANCES", min_value=1, is_int=True)

        # Check MIN <= MAX
        min_instances = self.get_env("MIN_INSTANCES")
        max_instances = self.get_env("MAX_INSTANCES")
        if min_instances and max_instances:
            try:
                if int(min_instances) > int(max_instances):
                    self.add_error(
                        "MIN_INSTANCES",
                        f"MIN_INSTANCES ({min_instances}) cannot exceed MAX_INSTANCES ({max_instances})",
                    )
            except ValueError:
                pass

        # Thresholds (0-100)
        self.validate_numeric("SCALE_UP_THRESHOLD", min_value=0, max_value=100)
        self.validate_numeric("SCALE_DOWN_THRESHOLD", min_value=0, max_value=100)

    def validate_all(self) -> bool:
        """Run all validations and return True if successful."""
        # Core validations
        self.validate_required_vars()
        self.validate_env()
        self.validate_log_level()

        # Redis
        self.validate_redis_url()

        # Worker and queue settings
        self.validate_worker_settings()

        # Budgets and costs
        self.validate_budgets()

        # Rate limits
        self.validate_rate_limits()

        # Security
        self.validate_security_settings()
        self.validate_production_secrets()
        self.validate_unsafe_defaults()

        # Health and monitoring
        self.validate_health_monitoring()

        # Dashboard
        self.validate_dashboard()

        # Paths
        self.validate_paths()

        # Database
        self.validate_database()

        # Auto-scaling
        self.validate_autoscaling()

        return len(self.errors) == 0

    def print_results(self) -> None:
        """Print validation results."""
        if self.errors:
            print("\n" + "=" * 70)
            print("VALIDATION ERRORS")
            print("=" * 70)
            for error in self.errors:
                print(f"  {error}")
            print()

        if self.warnings:
            print("\n" + "=" * 70)
            print("VALIDATION WARNINGS")
            print("=" * 70)
            for warning in self.warnings:
                print(f"  {warning}")
            print()

        if not self.errors and not self.warnings:
            print("\n" + "=" * 70)
            print("VALIDATION PASSED")
            print("=" * 70)
            print("  All environment variables are valid.")
            print()


def validate_config(strict: bool = False) -> tuple[bool, list[str], list[str]]:
    """Validate environment configuration.

    Args:
        strict: If True, treat warnings as errors

    Returns:
        Tuple of (success, errors, warnings)
    """
    validator = ConfigValidator(strict=strict)
    success = validator.validate_all()

    errors = [str(e) for e in validator.errors]
    warnings = [str(w) for w in validator.warnings]

    return success, errors, warnings


def main() -> int:
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(description="Validate environment configuration for OpenAI Agents Workflows")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors",
    )
    parser.add_argument(
        "--env-file",
        type=str,
        help="Path to .env file to load (optional)",
    )

    args = parser.parse_args()

    # Load .env file if specified
    if args.env_file:
        try:
            from dotenv import load_dotenv

            load_dotenv(args.env_file)
            print(f"Loaded environment from: {args.env_file}\n")
        except ImportError:
            print("Warning: python-dotenv not installed. Cannot load .env file.")
            print("Install with: pip install python-dotenv\n")
        except Exception as e:
            print(f"Error loading .env file: {e}\n")

    # Run validation
    validator = ConfigValidator(strict=args.strict)
    success = validator.validate_all()
    validator.print_results()

    # Exit with appropriate code
    if success:
        print("Exit code: 0 (success)")
        return 0
    else:
        error_count = len(validator.errors)
        warning_count = len(validator.warnings)
        print(f"Exit code: 1 (failed with {error_count} error(s), {warning_count} warning(s))")
        return 1


if __name__ == "__main__":
    sys.exit(main())
