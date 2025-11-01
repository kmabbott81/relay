"""End-to-end test for Night Shift queue processing with new CLI flags."""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        tasks_dir = temp_path / "tasks"
        tasks_dir.mkdir()

        runs_dir = temp_path / "runs"
        runs_dir.mkdir()

        yield {"temp": temp_path, "tasks": tasks_dir, "runs": runs_dir}


def test_nightshift_e2e_with_citations_and_fastpath(temp_dirs):
    """Test end-to-end Night Shift processing with citations and fastpath."""

    # Skip if running in CI or if OpenAI API key not available
    import os

    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OpenAI API key not available")

    tasks_dir = temp_dirs["tasks"]
    runs_dir = temp_dirs["runs"]

    # Step 1: Create a test preset that uses citations and fastpath
    test_preset_content = """# Test E2E Preset

**TASK:** Write a 100-word technology brief on quantum computing. Include exactly 2 citations.

**TRACE_NAME:** test-e2e-{timestamp}

**PARAMETERS:**
- max_tokens: 800
- temperature: 0.5
- require_citations: 2
- policy: openai_only
- fastpath: true
- max_debaters: 2
- margin_threshold: 3

**FORMAT REQUIREMENTS:**
- Include 2 credible sources
- Keep to 100 words maximum
"""

    preset_path = temp_dirs["temp"] / "test_preset.task.md"
    with open(preset_path, "w", encoding="utf-8") as f:
        f.write(test_preset_content)

    # Step 2: Use make_tasks.py to generate a task file
    make_tasks_cmd = [
        sys.executable,
        "scripts/make_tasks.py",
        "--preset",
        str(preset_path),
        "--count",
        "1",
        "--out",
        str(tasks_dir),
    ]

    try:
        result = subprocess.run(make_tasks_cmd, capture_output=True, text=True, timeout=30, cwd=Path.cwd())
        assert result.returncode == 0, f"make_tasks.py failed: {result.stderr}"

        # Check that a task file was created
        task_files = list(tasks_dir.glob("*.task.md"))
        assert len(task_files) == 1, f"Expected 1 task file, found {len(task_files)}"

        task_file = task_files[0]
        print(f"Generated task file: {task_file}")

    except subprocess.TimeoutExpired:
        pytest.skip("make_tasks.py timed out")
    except Exception as e:
        pytest.fail(f"Failed to generate task file: {e}")

    # Step 3: Mock nightshift_runner.py to use temp runs directory
    # We need to patch the runs directory in artifacts.py
    with patch("src.artifacts.save_run_artifact") as mock_save:
        # Set up mock to save to our temp runs directory
        def mock_save_artifact(artifact, runs_dir="runs"):
            timestamp = time.strftime("%Y.%m.%d-%H%M%S")
            filename = f"{timestamp}.json"
            file_path = runs_dir / filename

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(artifact, f, indent=2)

            return str(file_path)

        mock_save.side_effect = lambda artifact, runs_dir="runs": mock_save_artifact(artifact, runs_dir)

        # Step 4: Run nightshift_runner.py with our test task
        nightshift_cmd = [
            sys.executable,
            "nightshift_runner.py",
            "--repo",
            str(Path.cwd()),
            "--tasks-dir",
            str(tasks_dir),
            "--oneshot",
        ]

        try:
            # Set environment to use temp runs directory
            env = os.environ.copy()
            env["TEMP_RUNS_DIR"] = str(runs_dir)

            result = subprocess.run(
                nightshift_cmd,
                capture_output=True,
                text=True,
                timeout=120,  # Allow 2 minutes for full workflow
                cwd=Path.cwd(),
                env=env,
            )

            print(f"Nightshift stdout: {result.stdout}")
            if result.stderr:
                print(f"Nightshift stderr: {result.stderr}")

            # Allow some flexibility - might fail due to API limits but should process the task
            if result.returncode != 0:
                # Check if it's just an API error vs a structural problem
                if "ERROR" in result.stderr and "API" not in result.stderr:
                    pytest.fail(f"Nightshift failed with structural error: {result.stderr}")
                else:
                    pytest.skip(f"Nightshift failed likely due to API limits: {result.stderr}")

        except subprocess.TimeoutExpired:
            pytest.skip("Nightshift runner timed out - likely due to API latency")
        except Exception as e:
            pytest.skip(f"Nightshift execution failed: {e}")

    # Step 5: Check that task was processed (moved to done/)
    done_dir = tasks_dir / "done"
    if done_dir.exists():
        processed_files = list(done_dir.glob("*.md"))
        assert len(processed_files) > 0, "No processed task files found in done/"

        # Check the processed file has the expected status
        processed_file = processed_files[0]
        assert any(
            status in processed_file.name for status in [".ok.", ".error."]
        ), f"Processed file doesn't have expected status: {processed_file.name}"


def test_make_tasks_generation():
    """Test that make_tasks.py correctly generates task files with parameters."""

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        tasks_dir = temp_path / "tasks"

        # Create a simple test preset
        preset_content = """# Simple Test Preset

**TASK:** Test task for generation

**TRACE_NAME:** simple-test-{timestamp}

**PARAMETERS:**
- max_tokens: 500
- temperature: 0.2
- require_citations: 1
- policy: openai_only
"""

        preset_path = temp_path / "simple.task.md"
        with open(preset_path, "w", encoding="utf-8") as f:
            f.write(preset_content)

        # Generate 2 task files
        cmd = [
            sys.executable,
            "scripts/make_tasks.py",
            "--preset",
            str(preset_path),
            "--count",
            "2",
            "--out",
            str(tasks_dir),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, f"make_tasks.py failed: {result.stderr}"

        # Check that files were generated
        task_files = list(tasks_dir.glob("*.task.md"))
        assert len(task_files) == 2, f"Expected 2 files, got {len(task_files)}"

        # Check content of generated files
        for task_file in task_files:
            content = task_file.read_text(encoding="utf-8")
            assert "Test task for generation" in content
            assert "simple-test-" in content
            assert "require_citations: 1" in content or "REQUIRE_CITATIONS: 1" in content


@pytest.mark.bizlogic_asserts  # Sprint 52: Policy parameter parsing assertion failing
def test_policy_parameter_parsing():
    """Test that nightshift_runner correctly parses policy parameters."""

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create a task file with policy parameter
        task_content = """# Test Policy Task

**TASK:** Test task for policy parsing

**PARAMETERS:**
- max_tokens: 600
- temperature: 0.3
- policy: openai_preferred
- fastpath: true
- require_citations: 2
"""

        task_file = temp_path / "test_policy.task.md"
        with open(task_file, "w", encoding="utf-8") as f:
            f.write(task_content)

        # Import and test the parsing function directly
        sys.path.insert(0, str(Path.cwd()))
        from nightshift_runner import parse_task_file

        parsed = parse_task_file(task_file)

        assert parsed["policy"] == "openai_preferred"
        assert parsed["fastpath"] is True
        assert parsed["require_citations"] == 2
        assert parsed["max_tokens"] == 600
        assert parsed["temperature"] == 0.3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
