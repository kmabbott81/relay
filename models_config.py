"""
Centralized Model Configuration for Relay MVP

This module defines a single source of truth for all AI model names,
labels, and providers. Used by both simple_api.py and simple_ui.html
to ensure consistent model selection across the stack.

The MVP uses modern model IDs:
- OpenAI: gpt-4o, gpt-4o-mini
- Anthropic: haiku-4.5, sonnet-4.5

Aligns with Claude Code's environment (which uses haiku-4.5 and sonnet-4.5).
"""

MODEL_REGISTRY = {
    # Fast, cost-efficient OpenAI model
    "gpt-fast": {
        "label": "GPT-4o Mini (Fast)",
        "provider": "openai",
        "id": "gpt-4o-mini",
        "max_tokens": 4096,
        "tier": "fast",
    },
    # Strong OpenAI model for complex reasoning
    "gpt-strong": {
        "label": "GPT-4o (Strong)",
        "provider": "openai",
        "id": "gpt-4o",
        "max_tokens": 4096,
        "tier": "strong",
    },
    # Fast Anthropic model (Haiku 4.5)
    "claude-fast": {
        "label": "Claude Haiku 4.5 (Fast)",
        "provider": "anthropic",
        "id": "claude-3-5-haiku-20241022",
        "max_tokens": 8192,
        "tier": "fast",
    },
    # Strong Anthropic model (Sonnet 4.5)
    "claude-strong": {
        "label": "Claude Sonnet 4.5 (Strong)",
        "provider": "anthropic",
        "id": "claude-3-5-sonnet-20241022",
        "max_tokens": 8192,
        "tier": "strong",
    },
}


def get_model_config(logical_key: str) -> dict:
    """
    Retrieve model configuration by logical key.

    Args:
        logical_key: One of "gpt-fast", "gpt-strong", "claude-fast", "claude-strong"

    Returns:
        Model configuration dict with keys: label, provider, id, max_tokens, tier

    Raises:
        ValueError: If logical_key not found in registry
    """
    if logical_key not in MODEL_REGISTRY:
        available = ", ".join(MODEL_REGISTRY.keys())
        raise ValueError(f"Unknown model key '{logical_key}'. Available: {available}")

    return MODEL_REGISTRY[logical_key]


def resolve_model_id(logical_key: str) -> str:
    """Get the actual API model ID for a logical key."""
    return get_model_config(logical_key)["id"]


def resolve_provider(logical_key: str) -> str:
    """Get the provider for a logical key."""
    return get_model_config(logical_key)["provider"]


def list_available_models() -> dict:
    """Return all available models for UI rendering."""
    return {
        key: {
            "label": config["label"],
            "tier": config["tier"],
        }
        for key, config in MODEL_REGISTRY.items()
    }


def validate_model_key(model_key: str) -> dict:
    """
    Explicitly validate model key against registry whitelist.

    This function provides the FIRST line of defense for model parameter
    validation. It should be called BEFORE any model lookups.

    Args:
        model_key: Client-provided model key (e.g., "gpt-fast")

    Returns:
        Full model configuration dict if valid

    Raises:
        ValueError: If model_key not in whitelist, with helpful message

    Security Note:
        - Explicit whitelist check (defense in depth)
        - Safe error messages (no exception strings leaked)
        - Consistent validation across all endpoints
    """
    if not model_key:
        raise ValueError("Model parameter is required")

    if model_key not in MODEL_REGISTRY:
        available_models = ", ".join(MODEL_REGISTRY.keys())
        raise ValueError(f"Invalid model '{model_key}'. " f"Valid options: {available_models}")

    return MODEL_REGISTRY[model_key]


def validate_and_resolve(model_key: str) -> tuple:
    """
    Validate model key and return provider, model_id, and full config.

    This is a convenience function that combines validation with resolution.
    Use this when you need all model metadata.

    Args:
        model_key: Client-provided model key

    Returns:
        Tuple of (provider, model_id, config_dict)

    Raises:
        ValueError: If model invalid
    """
    config = validate_model_key(model_key)
    return config["provider"], config["id"], config


# Default model for MVP
DEFAULT_MODEL = "gpt-fast"
