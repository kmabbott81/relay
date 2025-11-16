from __future__ import annotations

import os


def load_dotenv_if_present() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return
    # Load .env if present
    for p in (".env", ".env.local", ".env.development"):
        if os.path.exists(p):
            load_dotenv(p, override=False)


def detect_providers() -> dict[str, bool]:
    """Return which providers are enabled by env keys."""
    return {
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "google": bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_VERTEX_PROJECT")),
    }


# Extremely rough $ estimates; tune later or replace with live pricing.
PRICING = {
    "openai": {"prompt_per_1k": 0.005, "completion_per_1k": 0.015},
    "anthropic": {"prompt_per_1k": 0.008, "completion_per_1k": 0.024},
    "google": {"prompt_per_1k": 0.0035, "completion_per_1k": 0.0105},
}


def pricing_for(provider: str) -> dict[str, float]:
    return PRICING.get(provider, {"prompt_per_1k": 0.0, "completion_per_1k": 0.0})
