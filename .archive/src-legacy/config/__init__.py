"""Configuration package for OpenAI Agents Workflows."""

# Import from new validation module
# Re-export functions from parent config module for backward compatibility
# Import directly from relay_ai.config module (not src.config package)
import importlib.util
import sys
from pathlib import Path

from .validate import validate_config

# Dynamically load the config.py module from parent directory
_config_path = Path(__file__).parent.parent / "config.py"
_spec = importlib.util.spec_from_file_location("_legacy_config", _config_path)
_legacy_config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_legacy_config)

# Re-export all functions
get_openai_api_key = _legacy_config.get_openai_api_key
get_anthropic_api_key = _legacy_config.get_anthropic_api_key
get_google_api_key = _legacy_config.get_google_api_key
get_provider_api_keys = _legacy_config.get_provider_api_keys
has_required_keys = _legacy_config.has_required_keys
load_policy = _legacy_config.load_policy
ALLOWED_PUBLISH_MODELS = _legacy_config.ALLOWED_PUBLISH_MODELS

__all__ = [
    "validate_config",
    "get_openai_api_key",
    "get_anthropic_api_key",
    "get_google_api_key",
    "get_provider_api_keys",
    "has_required_keys",
    "load_policy",
    "ALLOWED_PUBLISH_MODELS",
]
