"""UI configuration management with YAML support.

Provides:
- Default configuration values
- YAML config file loading/saving
- Model allowlist management
- Config-to-allowed-models conversion
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore

DEFAULTS = {
    "policy": "openai_preferred",
    "temperature": 0.3,
    "max_tokens": 1000,
    "redaction_rules_path": "",
    "allowed_models": {
        "openai": ["gpt-4o", "gpt-4o-mini"],
        "anthropic": ["claude-3-5-sonnet-20241022"],
        "google": ["gemini-1.5-pro"],
    },
}


def ensure_yaml():
    """Ensure PyYAML is available, raise if not."""
    global yaml
    if yaml is None:
        try:
            import yaml as _y  # type: ignore

            yaml = _y
        except ImportError:
            raise RuntimeError("PyYAML not installed. Run: pip install pyyaml") from None


def load_config(path: str | os.PathLike | None) -> dict[str, Any]:
    """Load configuration from YAML file, merging with defaults.

    Args:
        path: Path to YAML config file, or None for defaults only

    Returns:
        Configuration dict with defaults merged
    """
    cfg = DEFAULTS.copy()
    if not path:
        return cfg
    fp = Path(path)
    if not fp.exists():
        return cfg

    ensure_yaml()
    data = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}

    # Shallow merge
    for k, v in data.items():
        cfg[k] = v

    return cfg


def save_config(path: str | os.PathLike, cfg: dict[str, Any]) -> None:
    """Save configuration to YAML file.

    Args:
        path: Path to save YAML config
        cfg: Configuration dict to save
    """
    ensure_yaml()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)


def to_allowed_models(cfg: dict[str, Any]) -> list[str]:
    """Convert config allowed_models dict to flat list.

    Args:
        cfg: Configuration dict with allowed_models

    Returns:
        List of model strings in format "provider/model"
    """
    am = cfg.get("allowed_models") or {}
    out = []
    for prov, models in am.items():
        for m in models or []:
            out.append(f"{prov}/{m}")
    return out
