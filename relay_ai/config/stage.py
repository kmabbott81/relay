"""
Stage Detection and Configuration Loader

This module provides automatic detection of the current deployment stage (BETA, STAGING, PROD)
and loads stage-specific configuration from environment variables following the naming convention:
RELAY_[STAGE]_[SERVICE]_[VARIABLE]

Usage:
    from relay_ai.config.stage import get_stage, get_config, is_production

    stage = get_stage()  # Returns Stage.BETA
    config = get_config()  # Returns stage-specific config dict

    if is_production():
        # Production-only code path
        enable_strict_validation()
"""

import os
from enum import Enum
from typing import Any, Optional


class Stage(Enum):
    """Deployment stages for Relay platform."""

    BETA = "beta"
    STAGING = "staging"  # ARCHIVED 2025-11-19 - See STAGING_ARCHIVAL_DECISION_2025-11-19.md
    PROD = "prod"

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"Stage.{self.name}"


def get_stage() -> Stage:
    """
    Get current deployment stage from RELAY_STAGE environment variable.

    Returns:
        Stage: The current deployment stage (BETA, STAGING, or PROD)

    Raises:
        ValueError: If RELAY_STAGE is set to an invalid value

    Examples:
        >>> stage = get_stage()
        >>> print(stage)
        Stage.BETA
    """
    stage_str = os.getenv("RELAY_STAGE", "beta").lower()

    valid_stages = {s.value for s in Stage}
    if stage_str not in valid_stages:
        raise ValueError(f"Invalid RELAY_STAGE: '{stage_str}'. " f"Must be one of: {', '.join(sorted(valid_stages))}")

    return Stage(stage_str)


def is_beta() -> bool:
    """Check if running in BETA environment."""
    return get_stage() == Stage.BETA


def is_staging() -> bool:
    """Check if running in STAGING environment."""
    return get_stage() == Stage.STAGING


def is_production() -> bool:
    """Check if running in PRODUCTION environment."""
    return get_stage() == Stage.PROD


def get_stage_name() -> str:
    """
    Get stage name in uppercase for environment variable construction.

    Returns:
        str: Stage name in uppercase (BETA, STAGING, PROD)
    """
    return get_stage().name


def _get_env_var(service: str, variable: str, required: bool = False, default: Optional[str] = None) -> Optional[str]:
    """
    Internal helper to retrieve stage-specific environment variable.

    Uses naming convention: RELAY_[STAGE]_[SERVICE]_[VARIABLE]

    Args:
        service: Service identifier (e.g., "SUPABASE", "API", "DB")
        variable: Variable name (e.g., "URL", "KEY", "TOKEN")
        required: If True, raises error if variable not found
        default: Default value if variable not found and not required

    Returns:
        The environment variable value, or default if not found

    Raises:
        RuntimeError: If required variable not found
    """
    stage_name = get_stage_name()
    env_var = f"RELAY_{stage_name}_{service}_{variable}"
    value = os.getenv(env_var, default)

    if required and not value:
        raise RuntimeError(
            f"Required environment variable not set: {env_var}\n"
            f"You are running in {stage_name} mode. "
            f"Make sure this variable is configured for your environment."
        )

    return value


def get_config() -> dict[str, Any]:
    """
    Load stage-specific configuration from environment variables.

    Returns configuration dictionary with all service URLs, tokens, and credentials.

    Returns:
        Dict[str, Any]: Stage-specific configuration containing:
            - stage: Current stage identifier
            - supabase_url: Supabase project URL
            - supabase_key: Supabase anonymous key
            - api_url: API endpoint URL
            - db_url: Database connection string
            - vercel_token: Vercel deployment token (optional)

    Raises:
        RuntimeError: If required configuration is missing

    Examples:
        >>> config = get_config()
        >>> print(config['api_url'])
        https://relay-beta-api.railway.app
    """
    stage = get_stage()

    if stage == Stage.BETA:
        return {
            "stage": "beta",
            "stage_enum": Stage.BETA,
            "supabase_url": _get_env_var("SUPABASE", "URL", required=True),
            "supabase_key": _get_env_var("SUPABASE", "ANON_KEY", required=True),
            "api_url": _get_env_var("API", "URL", default="https://relay-beta-api.railway.app"),
            "db_url": _get_env_var("DB", "URL", required=True),
            "vercel_token": _get_env_var("VERCEL", "TOKEN"),
            "user_limit": 50,
            "query_limit_per_day": 100,
        }

    elif stage == Stage.STAGING:
        return {
            "stage": "staging",
            "stage_enum": Stage.STAGING,
            "supabase_url": _get_env_var("SUPABASE", "URL", required=True),
            "supabase_key": _get_env_var("SUPABASE", "ANON_KEY", required=True),
            "api_url": _get_env_var("API", "URL", default="https://relay-staging-api.railway.app"),
            "db_url": _get_env_var("DB", "URL", required=True),
            "vercel_token": _get_env_var("VERCEL", "TOKEN"),
            "user_limit": None,  # Unlimited
            "query_limit_per_day": None,  # Unlimited
        }

    else:  # PROD
        return {
            "stage": "prod",
            "stage_enum": Stage.PROD,
            "supabase_url": _get_env_var("SUPABASE", "URL", required=True),
            "supabase_key": _get_env_var("SUPABASE", "ANON_KEY", required=True),
            "api_url": _get_env_var("API", "URL", default="https://relay-prod-api.railway.app"),
            "db_url": _get_env_var("DB", "URL", required=True),
            "vercel_token": _get_env_var("VERCEL", "TOKEN"),
            "user_limit": None,  # Unlimited
            "query_limit_per_day": None,  # Unlimited per subscription
        }


def get_supabase_config() -> dict[str, str]:
    """
    Get Supabase-specific configuration for the current stage.

    Returns:
        Dict[str, str]: Contains 'url' and 'key' for Supabase client initialization
    """
    config = get_config()
    return {
        "url": config["supabase_url"],
        "key": config["supabase_key"],
    }


def get_database_url() -> str:
    """
    Get database connection URL for the current stage.

    Returns:
        str: PostgreSQL connection string
    """
    config = get_config()
    db_url = config["db_url"]
    if not db_url:
        raise RuntimeError("Database URL not configured for current stage")
    return db_url


def get_stage_constraints() -> dict[str, Optional[int]]:
    """
    Get user and query constraints for the current stage.

    Returns:
        Dict[str, Optional[int]]: Contains 'user_limit' and 'query_limit_per_day'
            Values are None for unlimited
    """
    config = get_config()
    return {
        "user_limit": config.get("user_limit"),
        "query_limit_per_day": config.get("query_limit_per_day"),
    }


def validate_stage_configuration() -> bool:
    """
    Validate that all required configuration for current stage is available.

    Used during startup to fail fast if configuration is incomplete.

    Returns:
        bool: True if all configuration is valid

    Raises:
        RuntimeError: If any required configuration is missing

    Examples:
        >>> validate_stage_configuration()
        True
    """
    try:
        stage = get_stage()
        config = get_config()

        # Verify all required fields are present
        required_fields = ["supabase_url", "supabase_key", "db_url"]
        for field in required_fields:
            if not config.get(field):
                raise RuntimeError(
                    f"Missing required configuration: {field} " f"(from RELAY_{stage.name}_{field.upper()})"
                )

        return True

    except (ValueError, RuntimeError) as e:
        raise RuntimeError(f"Stage configuration validation failed: {str(e)}") from e


def get_stage_info() -> dict[str, Any]:
    """
    Get comprehensive information about the current stage setup.

    Used for logging and debugging deployment configuration.

    Returns:
        Dict[str, Any]: Information about current stage including name, environment, and limits
    """
    stage = get_stage()
    config = get_config()

    return {
        "stage": str(stage),
        "stage_enum": stage,
        "stage_name_upper": get_stage_name(),
        "is_production": is_production(),
        "is_beta": is_beta(),
        "is_staging": is_staging(),
        "api_url": config["api_url"],
        "user_limit": config.get("user_limit"),
        "query_limit_per_day": config.get("query_limit_per_day"),
        "supabase_project_id": _extract_project_id(config["supabase_url"]),
    }


def _extract_project_id(supabase_url: str) -> str:
    """
    Extract Supabase project ID from URL.

    Args:
        supabase_url: Supabase project URL

    Returns:
        str: Project ID (the subdomain)

    Examples:
        >>> url = "https://hmqmxmxkxqdrqpdmlgtn.supabase.co"
        >>> _extract_project_id(url)
        'hmqmxmxkxqdrqpdmlgtn'
    """
    if not supabase_url:
        return "unknown"

    # Extract subdomain from https://[PROJECT_ID].supabase.co
    parts = supabase_url.split(".")
    if len(parts) >= 1:
        # Get the last segment before .supabase.co
        return parts[0].replace("https://", "").replace("http://", "")

    return "unknown"


# Startup logging (executed once when module is imported)
def log_stage_info() -> None:
    """Log stage information at startup for debugging."""
    try:
        info = get_stage_info()
        stage = get_stage()
        print(f"✓ Relay running in {stage.value.upper()} mode " f"({info['supabase_project_id']})")
    except Exception as e:
        print(f"⚠ Warning: Could not log stage info: {e}")
