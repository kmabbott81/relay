"""Integration tests for DJP workflow end-to-end functionality."""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def sample_tasks():
    """Sample tasks for integration testing."""
    return ["What is 2 + 2?", "Name the capital of France.", "Explain photosynthesis in one sentence."]


@pytest.fixture
def temp_runs_dir():
    """Create a temporary runs directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        runs_dir = Path(temp_dir) / "runs"
        runs_dir.mkdir()
        yield str(runs_dir)


def run_djp_workflow(
    task: str, preset: str = "deterministic", runs_dir: str = "runs", extra_args: list = None
) -> dict[str, Any]:
    """
    Run the DJP workflow and return the artifact data.

    Args:
        task: Task to process
        preset: Preset to use
        runs_dir: Directory to save runs
        extra_args: Additional CLI arguments

    Returns:
        Dictionary containing artifact data
    """
    # Build command
    cmd = [
        "python",
        "-m",
        "src.run_workflow",
        "--preset",
        preset,
        "--task",
        task,
        "--quiet",  # Suppress output for cleaner tests
    ]

    if extra_args:
        cmd.extend(extra_args)

    # Set RUNS_DIR environment variable if provided
    env = os.environ.copy()
    if runs_dir != "runs":
        env["RUNS_DIR"] = runs_dir

    # Run the workflow
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=60, env=env, cwd=Path.cwd()  # 1 minute timeout
    )

    if result.returncode != 0:
        raise RuntimeError(f"Workflow failed: {result.stderr}")

    # Find the most recent artifact
    runs_path = Path(runs_dir)
    if not runs_path.exists():
        runs_path = Path("runs")  # Fallback to default

    artifacts = sorted(runs_path.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)

    if not artifacts:
        raise RuntimeError("No artifacts found after workflow execution")

    # Load and return the most recent artifact
    with open(artifacts[0], encoding="utf-8") as f:
        return json.load(f)


def run_replay_workflow(artifact_path: Path, task: str = None) -> dict[str, Any]:
    """
    Replay a workflow and return the new artifact data.

    Args:
        artifact_path: Path to the artifact to replay
        task: Optional task override

    Returns:
        Dictionary containing new artifact data
    """
    cmd = ["python", "scripts/replay.py", "--replay", str(artifact_path)]

    if task:
        cmd.extend(["--task", task])

    # Run the replay
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=Path.cwd())  # 1 minute timeout

    if result.returncode != 0:
        raise RuntimeError(f"Replay failed: {result.stderr}")

    # Find the most recent artifact (should be the replayed one)
    runs_path = Path("runs")
    artifacts = sorted(runs_path.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)

    if not artifacts:
        raise RuntimeError("No artifacts found after replay execution")

    # Load and return the most recent artifact
    with open(artifacts[0], encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available - skipping integration test")
def test_deterministic_workflow_reproducibility(sample_tasks, temp_runs_dir):
    """Test that deterministic preset produces reproducible results."""
    task = sample_tasks[0]  # Use first sample task

    # Run workflow twice with deterministic preset
    artifact1 = run_djp_workflow(task, preset="deterministic", runs_dir=temp_runs_dir)
    # TODO(Sprint 45): replace with wait_until(...) for faster polling
    time.sleep(1)  # Ensure different timestamps
    artifact2 = run_djp_workflow(task, preset="deterministic", runs_dir=temp_runs_dir)

    # Both artifacts should have the same structure
    assert artifact1["schema_version"] == artifact2["schema_version"]
    assert artifact1["run_metadata"]["task"] == artifact2["run_metadata"]["task"]

    # Parameters should be identical (deterministic preset)
    params1 = artifact1["run_metadata"]["parameters"]
    params2 = artifact2["run_metadata"]["parameters"]

    # Seed should be the same (deterministic)
    assert params1.get("seed") == params2.get("seed") == 12345
    assert params1.get("temperature") == params2.get("temperature") == 0.0
    assert params1.get("preset_name") == params2.get("preset_name") == "deterministic"

    # Results should be similar structure (may vary slightly due to API)
    assert len(artifact1["debate"]["drafts"]) > 0
    assert len(artifact2["debate"]["drafts"]) > 0
    assert artifact1["judge"]["winner_provider"] is not None
    assert artifact2["judge"]["winner_provider"] is not None


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available - skipping integration test")
def test_preset_configuration_applied(sample_tasks, temp_runs_dir):
    """Test that preset configuration is properly applied to artifacts."""
    task = sample_tasks[1]  # Use second sample task

    # Test quick preset
    artifact = run_djp_workflow(task, preset="quick", runs_dir=temp_runs_dir)
    params = artifact["run_metadata"]["parameters"]

    # Verify quick preset parameters are applied
    assert params.get("max_tokens") == 800
    assert params.get("temperature") == 0.2
    assert params.get("fastpath") is True
    assert params.get("max_debaters") == 2
    assert params.get("timeout_s") == 60
    assert params.get("margin_threshold") == 3
    assert params.get("preset_name") == "quick"

    # Verify artifact structure
    assert artifact["schema_version"] == "1.1"
    assert artifact["run_metadata"]["task"] == task
    assert "debate" in artifact
    assert "judge" in artifact
    assert "publish" in artifact
    assert "provenance" in artifact


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not available - skipping integration test")
def test_workflow_replay_consistency(sample_tasks, temp_runs_dir):
    """Test that replay produces consistent results for deterministic workflows."""
    task = sample_tasks[0]  # Use first sample task

    # Run initial workflow
    original_artifact = run_djp_workflow(task, preset="deterministic", runs_dir=temp_runs_dir)

    # Save original artifact to a known location for replay
    artifact_path = Path(temp_runs_dir) / "original_artifact.json"
    with open(artifact_path, "w", encoding="utf-8") as f:
        json.dump(original_artifact, f, indent=2)

    # Replay the workflow
    replayed_artifact = run_replay_workflow(artifact_path)

    # Compare key fields that should be identical
    original_params = original_artifact["run_metadata"]["parameters"]
    replayed_params = replayed_artifact["run_metadata"]["parameters"]

    # Parameters should be identical
    assert original_params.get("max_tokens") == replayed_params.get("max_tokens")
    assert original_params.get("temperature") == replayed_params.get("temperature")
    assert original_params.get("seed") == replayed_params.get("seed")
    assert original_params.get("fastpath") == replayed_params.get("fastpath")

    # Task should be the same
    assert original_artifact["run_metadata"]["task"] == replayed_artifact["run_metadata"]["task"]

    # Both should have valid structure
    assert original_artifact["schema_version"] == replayed_artifact["schema_version"]
    assert len(original_artifact["debate"]["drafts"]) > 0
    assert len(replayed_artifact["debate"]["drafts"]) > 0
    assert original_artifact["judge"]["winner_provider"] is not None
    assert replayed_artifact["judge"]["winner_provider"] is not None


def test_mock_integration_workflow_structure():
    """Test workflow structure with mocked components (no API calls)."""
    # This test doesn't require API keys and validates the integration structure

    # Test that we can import and instantiate key components
    from relay_ai.artifacts import create_run_artifact
    from relay_ai.schemas import Draft, Judgment, ScoredDraft

    # Create mock data
    mock_drafts = [
        Draft(
            provider="mock/provider",
            answer="Mock answer",
            evidence=["Mock evidence 1", "Mock evidence 2"],
            confidence=0.8,
            safety_flags=[],
        )
    ]

    mock_judgment = Judgment(
        ranked=[
            ScoredDraft(
                provider="mock/provider",
                answer="Mock answer",
                evidence=["Mock evidence 1", "Mock evidence 2"],
                confidence=0.8,
                safety_flags=[],
                score=8.5,
                reasons="Mock reasoning",
                subscores={"task_fit": 4.0, "support": 3.0, "clarity": 1.5},
            )
        ],
        winner_provider="mock/provider",
    )

    # Create artifact
    artifact = create_run_artifact(
        task="Mock integration test task",
        max_tokens=1000,
        temperature=0.3,
        trace_name="mock-integration",
        drafts=mock_drafts,
        judgment=mock_judgment,
        status="published",
        provider="mock/provider",
        text="Mock published text",
        allowed_models=["mock/provider"],
        start_time=time.time(),
        preset_name="deterministic",
    )

    # Verify artifact structure
    assert artifact["schema_version"] == "1.1"
    assert artifact["run_metadata"]["task"] == "Mock integration test task"
    assert artifact["run_metadata"]["parameters"]["preset_name"] == "deterministic"
    assert len(artifact["debate"]["drafts"]) == 1
    assert len(artifact["judge"]["ranked_drafts"]) == 1
    assert artifact["publish"]["status"] == "published"
    assert artifact["publish"]["text"] == "Mock published text"
    assert "provenance" in artifact


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
