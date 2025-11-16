"""Configuration for Debate → Judge → Publish workflow and AI Orchestrator."""

import json
import os
from pathlib import Path
from typing import Optional

ALLOWED_PUBLISH_MODELS = ["openai/gpt-4.1", "openai/gpt-4o", "openai/gpt-4o-mini"]

# AI Orchestrator v0.1 Configuration
DEFAULT_AI_MODEL = "gpt-4o-mini"
DEFAULT_AI_MAX_OUTPUT_TOKENS = 800
DEFAULT_AI_MAX_TOKENS_PER_MIN = 8000


def get_openai_api_key() -> Optional[str]:
    """Get OpenAI API key from environment."""
    return os.getenv("OPENAI_API_KEY")


def get_anthropic_api_key() -> Optional[str]:
    """Get Anthropic API key from environment."""
    return os.getenv("ANTHROPIC_API_KEY")


def get_google_api_key() -> Optional[str]:
    """Get Google API key from environment."""
    return os.getenv("GOOGLE_API_KEY")


def get_provider_api_keys() -> dict[str, Optional[str]]:
    """Get all provider API keys for LiteLLM models."""
    return {
        "openai": get_openai_api_key(),
        "anthropic": get_anthropic_api_key(),
        "google": get_google_api_key(),
    }


def has_required_keys() -> bool:
    """Check if minimum required API keys are available."""
    return get_openai_api_key() is not None


def load_policy(path_or_name: str) -> list[str]:
    """
    Load policy configuration from file or by name.

    Args:
        path_or_name: Either a file path or a policy name (without .json extension)

    Returns:
        List of allowed provider model names

    Raises:
        FileNotFoundError: If policy file doesn't exist
        json.JSONDecodeError: If policy file is not valid JSON
        KeyError: If policy file doesn't contain ALLOWED_PUBLISH_MODELS key
    """
    # Check if it's a path or a name
    if path_or_name.endswith(".json") or os.path.exists(path_or_name):
        # Treat as file path
        policy_path = Path(path_or_name)
    else:
        # Treat as policy name, look in policies directory
        policy_path = Path("policies") / f"{path_or_name}.json"

    if not policy_path.exists():
        raise FileNotFoundError(f"Policy file not found: {policy_path}")

    with open(policy_path, encoding="utf-8") as f:
        policy_data = json.load(f)

    if "ALLOWED_PUBLISH_MODELS" not in policy_data:
        raise KeyError(f"Policy file {policy_path} missing required key: ALLOWED_PUBLISH_MODELS")

    return policy_data["ALLOWED_PUBLISH_MODELS"]


def get_openai_client_and_limits() -> tuple[object, int, str]:
    """Get OpenAI client with cost control limits.

    Returns:
        Tuple of (client, max_output_tokens, model_name)

    Raises:
        ValueError: If OPENAI_API_KEY not set
    """
    import openai

    api_key = get_openai_api_key()
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")

    client = openai.OpenAI(api_key=api_key)

    model = os.getenv("AI_MODEL", DEFAULT_AI_MODEL)
    max_output_tokens = int(os.getenv("AI_MAX_OUTPUT_TOKENS", str(DEFAULT_AI_MAX_OUTPUT_TOKENS)))

    return client, max_output_tokens, model
