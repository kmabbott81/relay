"""Run artifacts system for JSON serialization and loading."""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import ujson

try:
    import jsonschema

    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False

from .schemas import Draft, Judgment

# Import storage backend (optional, falls back to local)
try:
    from .storage import get_storage_backend, save_artifact_content

    STORAGE_AVAILABLE = True
except ImportError:
    STORAGE_AVAILABLE = False


def get_git_sha() -> str:
    """Get current git commit short SHA."""
    try:
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def get_python_version() -> str:
    """Get Python version."""
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def get_sdk_version() -> str:
    """Get Agents SDK version if available."""
    try:
        # Try to get version from agents module
        import agents

        if hasattr(agents, "__version__"):
            return agents.__version__
        # Fallback to package inspection
        import pkg_resources

        return pkg_resources.get_distribution("openai-agents").version
    except Exception:
        return "unknown"


def estimate_token_costs(model_usage: dict[str, dict[str, int]]) -> dict[str, float]:
    """Estimate costs based on token usage and rough pricing."""
    # Rough pricing per 1K tokens (input/output) - these are estimates
    PRICING = {
        "openai/gpt-4": (0.03, 0.06),
        "openai/gpt-4o": (0.005, 0.015),
        "openai/gpt-4o-mini": (0.00015, 0.0006),
        "anthropic/claude-3-5-sonnet-20240620": (0.003, 0.015),
        "google/gemini-1.5-pro": (0.0035, 0.0105),
    }

    costs = {}
    for provider, usage in model_usage.items():
        if provider in PRICING:
            input_cost = (usage["tokens_in"] / 1000) * PRICING[provider][0]
            output_cost = (usage["tokens_out"] / 1000) * PRICING[provider][1]
            costs[provider] = round(input_cost + output_cost, 4)
        else:
            costs[provider] = 0.0

    return costs


def create_provenance(start_time: float, model_usage: Optional[dict[str, dict[str, int]]] = None) -> dict[str, Any]:
    """Create provenance information for the run."""
    if model_usage is None:
        model_usage = {}

    return {
        "git_sha": get_git_sha(),
        "python_version": get_python_version(),
        "sdk_version": get_sdk_version(),
        "model_usage": model_usage,
        "estimated_costs": estimate_token_costs(model_usage),
        "duration_seconds": round(time.time() - start_time, 2),
    }


def load_artifact_schema() -> Optional[dict[str, Any]]:
    """Load the artifact JSON schema."""
    try:
        schema_path = Path("schemas/artifact.json")
        if schema_path.exists():
            with open(schema_path, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return None


def validate_artifact(artifact: dict[str, Any]) -> bool:
    """Validate artifact against schema if available."""
    if not JSONSCHEMA_AVAILABLE:
        return True  # Skip validation if jsonschema not available

    schema = load_artifact_schema()
    if not schema:
        return True  # Skip validation if schema not found

    try:
        jsonschema.validate(artifact, schema)
        return True
    except jsonschema.ValidationError as e:
        print(f"Artifact validation failed: {e.message}")
        return False


def create_run_artifact(
    task: str,
    max_tokens: int,
    temperature: float,
    trace_name: str,
    drafts: list[Draft],
    judgment: Judgment,
    status: str,
    provider: str,
    text: str,
    allowed_models: list[str],
    start_time: float,
    require_citations: int = 0,
    policy: str = "openai_only",
    fastpath: bool = False,
    max_debaters: Optional[int] = None,
    timeout_s: Optional[int] = None,
    margin_threshold: Optional[int] = None,
    seed: Optional[int] = None,
    model_usage: Optional[dict[str, dict[str, int]]] = None,
    reason: Optional[str] = None,
    preset_name: Optional[str] = None,
    grounded_corpus: Optional[str] = None,
    grounded_required: int = 0,
    redact: bool = True,
    redaction_rules: Optional[str] = None,
    redaction_metadata: Optional[dict[str, Any]] = None,
    corpus_docs_count: int = 0,
    citations: Optional[list[dict[str, str]]] = None,
    grounded_fail_reason: Optional[str] = None,
) -> dict[str, Any]:
    """
    Create a complete run artifact with all data.

    Args:
        task: The user's task
        max_tokens: Token limit used
        temperature: Temperature used
        trace_name: Trace identifier
        drafts: Original drafts from debate stage
        judgment: Judge's decision and ranking
        status: Publish status
        provider: Selected provider
        text: Published/advisory text
        allowed_models: List of allowed models for publishing

    Returns:
        Dictionary containing all run data
    """
    timestamp = datetime.now().isoformat()

    # Create parameters dict with all options
    parameters = {"max_tokens": max_tokens, "temperature": temperature, "allowed_models": allowed_models}

    # Add optional parameters if set
    if require_citations > 0:
        parameters["require_citations"] = require_citations
    if policy != "openai_only":
        parameters["policy"] = policy
    if fastpath:
        parameters["fastpath"] = fastpath
    if max_debaters is not None:
        parameters["max_debaters"] = max_debaters
    if timeout_s is not None:
        parameters["timeout_s"] = timeout_s
    if margin_threshold is not None:
        parameters["margin_threshold"] = margin_threshold
    if seed is not None:
        parameters["seed"] = seed
    if preset_name is not None:
        parameters["preset_name"] = preset_name
    if grounded_corpus is not None:
        parameters["grounded_corpus"] = grounded_corpus
    parameters["grounded_required"] = grounded_required
    parameters["redact"] = redact
    if redaction_rules is not None:
        parameters["redaction_rules"] = redaction_rules

    artifact = {
        "schema_version": "1.1",
        "run_metadata": {"timestamp": timestamp, "task": task, "trace_name": trace_name, "parameters": parameters},
        "debate": {
            "drafts": [
                {
                    "provider": draft.provider,
                    "answer": draft.answer,
                    "evidence": draft.evidence,
                    "confidence": draft.confidence,
                    "safety_flags": draft.safety_flags,
                }
                for draft in drafts
            ],
            "total_drafts": len(drafts),
        },
        "judge": {
            "ranked_drafts": [
                {
                    "provider": scored_draft.provider,
                    "answer": scored_draft.answer,
                    "evidence": scored_draft.evidence,
                    "confidence": scored_draft.confidence,
                    "safety_flags": scored_draft.safety_flags,
                    "score": scored_draft.score,
                    "reasons": scored_draft.reasons,
                    "subscores": scored_draft.subscores,
                }
                for scored_draft in judgment.ranked
            ],
            "winner_provider": judgment.winner_provider,
            "total_ranked": len(judgment.ranked),
        },
        "publish": {
            "status": status,
            "provider": provider,
            "text": text,
            "text_length": len(text) if text else 0,
            **({"reason": reason} if reason else {}),
            "redacted": redaction_metadata.get("redacted", False) if redaction_metadata else False,
            "redaction_events": redaction_metadata.get("events", []) if redaction_metadata else [],
        },
        "grounding": {
            "enabled": grounded_corpus is not None,
            "corpus_loaded": corpus_docs_count > 0,
            "corpus_docs": corpus_docs_count,
            "required_citations": grounded_required,
            "citations": citations or [],
            "grounded_fail_reason": grounded_fail_reason,
        },
        "provenance": create_provenance(start_time, model_usage),
    }

    return artifact


def save_run_artifact(artifact: dict[str, Any], runs_dir: Optional[str] = None) -> str:
    """
    Save run artifact to JSON file with validation.

    Supports local, S3, and GCS storage backends via RUNS_DIR configuration.

    Args:
        artifact: Run artifact dictionary
        runs_dir: Storage location override (default: uses RUNS_DIR env var or "runs")
                 Examples: "runs", "s3://bucket/prefix", "gs://bucket/prefix"

    Returns:
        Path/URI to saved file

    Environment Variables:
        RUNS_DIR: Storage location (local path, s3://, or gs://)
    """
    # Use env var if not specified
    if runs_dir is None:
        runs_dir = os.getenv("RUNS_DIR", "runs")

    # Validate artifact against schema
    if not validate_artifact(artifact):
        print("Warning: Artifact failed schema validation, saving anyway")

    # Create filename from timestamp
    timestamp = datetime.now().strftime("%Y.%m.%d-%H%M")
    filename = f"{timestamp}.json"

    # Serialize to JSON string
    content = ujson.dumps(artifact, indent=2, escape_forward_slashes=False)

    # Use cloud storage if available and configured
    if STORAGE_AVAILABLE and (runs_dir.startswith("s3://") or runs_dir.startswith("gs://")):
        try:
            return save_artifact_content(content, filename, runs_dir)
        except Exception as e:
            print(f"Warning: Cloud storage failed ({e}), falling back to local")
            runs_dir = "runs"

    # Fallback to local storage
    runs_path = Path(runs_dir)
    runs_path.mkdir(exist_ok=True)
    file_path = runs_path / filename

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return str(file_path)


def load_artifact(path: str) -> dict[str, Any]:
    """
    Load and rehydrate a run artifact.

    Args:
        path: Path to the JSON artifact file

    Returns:
        Dictionary containing the run data

    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If file is not valid JSON
    """
    with open(path, encoding="utf-8") as f:
        return ujson.load(f)


def get_latest_artifact(runs_dir: str = "runs") -> Optional[str]:
    """
    Get the path to the most recent artifact file.

    Args:
        runs_dir: Directory containing artifacts

    Returns:
        Path to latest artifact, or None if no artifacts found
    """
    runs_path = Path(runs_dir)
    if not runs_path.exists():
        return None

    json_files = list(runs_path.glob("*.json"))
    if not json_files:
        return None

    # Sort by filename (which includes timestamp)
    latest = sorted(json_files)[-1]
    return str(latest)


def list_artifacts(runs_dir: str = "runs") -> list[str]:
    """
    List all artifact files in the runs directory.

    Args:
        runs_dir: Directory containing artifacts

    Returns:
        List of artifact file paths, sorted by timestamp
    """
    runs_path = Path(runs_dir)
    if not runs_path.exists():
        return []

    json_files = list(runs_path.glob("*.json"))
    return sorted([str(f) for f in json_files])


def artifact_summary(artifact: dict[str, Any]) -> str:
    """
    Create a short summary of an artifact.

    Args:
        artifact: Loaded artifact dictionary

    Returns:
        Human-readable summary string
    """
    metadata = artifact["run_metadata"]
    judge = artifact["judge"]
    publish = artifact["publish"]

    return f"""Run Summary:
- Task: {metadata['task'][:60]}...
- Timestamp: {metadata['timestamp']}
- Trace: {metadata['trace_name']}
- Drafts: {artifact['debate']['total_drafts']}
- Winner: {judge['winner_provider']} (score: {judge['ranked_drafts'][0]['score']:.1f}/10)
- Status: {publish['status']} from {publish['provider']}
- Text Length: {publish['text_length']} characters"""
