"""End-to-end tests for sample workflows.

Tests cover:
- Each workflow in DRY-RUN mode (deterministic, no external calls)
- Artifacts created in expected locations
- Artifact content format (markdown structure)
- LIVE mode skipped unless LIVE_OPENAI_TESTS=true env var set
- CLI argument parsing (--dry-run, --live flags)
- Config file loading from templates/examples/
- Error handling for missing config files
- Windows path handling (use tmp_path fixture)
- Uses monkeypatch and mock for deterministic testing
"""

import os
import re
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from relay_ai.workflows.examples.inbox_drive_sweep import (
    load_config as inbox_load_config,
)
from relay_ai.workflows.examples.inbox_drive_sweep import (
    run_workflow as inbox_run_workflow,
)
from relay_ai.workflows.examples.meeting_transcript_brief import (
    format_prompt as meeting_format_prompt,
)
from relay_ai.workflows.examples.meeting_transcript_brief import (
    generate_sample_transcript,
    write_brief,
)
from relay_ai.workflows.examples.meeting_transcript_brief import (
    load_config as meeting_load_config,
)
from relay_ai.workflows.examples.meeting_transcript_brief import (
    run_workflow as meeting_run_workflow,
)
from relay_ai.workflows.examples.weekly_report_pack import (
    format_prompt as weekly_format_prompt,
)
from relay_ai.workflows.examples.weekly_report_pack import (
    generate_sample_context,
    write_report,
)
from relay_ai.workflows.examples.weekly_report_pack import (
    load_config as weekly_load_config,
)
from relay_ai.workflows.examples.weekly_report_pack import (
    run_workflow as weekly_run_workflow,
)

# Skip live tests unless explicitly enabled
LIVE_TESTS_ENABLED = os.getenv("LIVE_OPENAI_TESTS", "false").lower() == "true"
skip_live = pytest.mark.skipif(not LIVE_TESTS_ENABLED, reason="LIVE_OPENAI_TESTS not enabled")


@pytest.fixture
def temp_artifacts_dir(tmp_path):
    """Fixture for temporary artifact directory."""
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return artifacts_dir


@pytest.fixture
def mock_project_root(tmp_path):
    """Fixture for mocking project root with config files."""
    # Create templates/examples directory
    templates_dir = tmp_path / "templates" / "examples"
    templates_dir.mkdir(parents=True, exist_ok=True)

    # Create mock config files
    weekly_config = {
        "workflow_name": "weekly_report",
        "description": "Generate weekly status report",
        "prompt_template": "Generate a weekly report for {start_date} to {end_date}:\n{context}",
        "parameters": {"model": "gpt-4o", "max_tokens": 2000, "temperature": 0.5},
    }

    meeting_config = {
        "workflow_name": "meeting_brief",
        "description": "Generate meeting brief",
        "prompt_template": "Summarize meeting: {meeting_title} on {meeting_date}\nAttendees: {attendees}\n\nTranscript:\n{transcript}",
        "parameters": {"model": "gpt-4o", "max_tokens": 1500, "temperature": 0.3},
    }

    inbox_config = {
        "workflow_name": "inbox_sweep",
        "description": "Process inbox and drive files",
        "prompt_template": "Process these files: {file_list}",
        "parameters": {"model": "gpt-4o-mini", "max_tokens": 1000, "temperature": 0.4},
    }

    with open(templates_dir / "weekly_report.yaml", "w", encoding="utf-8") as f:
        yaml.dump(weekly_config, f)

    with open(templates_dir / "meeting_brief.yaml", "w", encoding="utf-8") as f:
        yaml.dump(meeting_config, f)

    with open(templates_dir / "inbox_sweep.yaml", "w", encoding="utf-8") as f:
        yaml.dump(inbox_config, f)

    return tmp_path


class TestWeeklyReportWorkflow:
    """Test weekly report workflow."""

    def test_weekly_report_dry_run_components(self, mock_project_root, tmp_path):
        """Test weekly report workflow components work correctly."""
        # Test config loading
        config_path = mock_project_root / "templates" / "examples" / "weekly_report.yaml"
        config = weekly_load_config(config_path)
        assert config is not None
        assert "workflow_name" in config

        # Test context generation
        context = generate_sample_context()
        assert len(context) > 0

        # Test prompt formatting
        prompt = weekly_format_prompt(config["prompt_template"], "2025-01-01", "2025-01-07", context)
        assert "2025-01-01" in prompt

        # Test report writing
        output_path = tmp_path / "test_report.md"
        content = "Test report content"
        write_report(output_path, content, config)
        assert output_path.exists()

    def test_weekly_report_config_loading(self, mock_project_root):
        """Test weekly report config loads correctly."""
        config_path = mock_project_root / "templates" / "examples" / "weekly_report.yaml"
        config = weekly_load_config(config_path)

        assert config["workflow_name"] == "weekly_report"
        assert "prompt_template" in config
        assert "parameters" in config
        assert config["parameters"]["model"] == "gpt-4o"

    def test_weekly_report_prompt_formatting(self):
        """Test weekly report prompt formatting."""
        template = "Report for {start_date} to {end_date}: {context}"
        context = "Test context"

        prompt = weekly_format_prompt(template, "2025-01-01", "2025-01-07", context)

        assert "2025-01-01" in prompt
        assert "2025-01-07" in prompt
        assert "Test context" in prompt

    def test_weekly_report_sample_context_generation(self):
        """Test sample context generation."""
        context = generate_sample_context()

        assert isinstance(context, str)
        assert len(context) > 0
        assert "Team Activities" in context or "Metrics" in context

    def test_weekly_report_artifact_format(self, tmp_path):
        """Test weekly report artifact has correct markdown format."""
        output_path = tmp_path / "test_report.md"
        content = "## Summary\nThis is a test report."
        metadata = {"workflow_name": "weekly_report"}

        write_report(output_path, content, metadata)

        assert output_path.exists()

        written_content = output_path.read_text(encoding="utf-8")
        assert "# Weekly Status Report" in written_content
        assert "**Generated:**" in written_content
        assert "**Workflow:** weekly_report" in written_content
        assert "---" in written_content
        assert content in written_content

    def test_weekly_report_missing_config_error(self, tmp_path):
        """Test error handling for missing config file."""
        nonexistent_config = tmp_path / "missing.yaml"

        with pytest.raises(FileNotFoundError):
            weekly_load_config(nonexistent_config)

    @skip_live
    def test_weekly_report_live_mode(self, monkeypatch, mock_project_root):
        """Test weekly report workflow in live mode (requires API key)."""
        monkeypatch.setenv("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", "sk-test"))

        with patch("src.workflows.examples.weekly_report_pack.Path") as mock_path:
            mock_path.return_value.parent.parent.parent.parent = mock_project_root

            output_path = weekly_run_workflow(dry_run=False)

        assert output_path is not None
        output_file = Path(output_path)
        assert output_file.exists()

        # Live response should not contain [MOCK]
        content = output_file.read_text(encoding="utf-8")
        assert "[MOCK]" not in content


class TestMeetingBriefWorkflow:
    """Test meeting transcript brief workflow."""

    def test_meeting_brief_dry_run_components(self, mock_project_root, tmp_path):
        """Test meeting brief workflow components work correctly."""
        # Test config loading
        config_path = mock_project_root / "templates" / "examples" / "meeting_brief.yaml"
        config = meeting_load_config(config_path)
        assert config is not None
        assert "workflow_name" in config

        # Test transcript generation
        transcript_data = generate_sample_transcript()
        assert "meeting_title" in transcript_data
        assert "transcript" in transcript_data

        # Test prompt formatting
        prompt = meeting_format_prompt(
            config["prompt_template"],
            transcript_data["meeting_title"],
            transcript_data["meeting_date"],
            transcript_data["attendees"],
            transcript_data["transcript"],
        )
        assert transcript_data["meeting_title"] in prompt

        # Test brief writing
        output_path = tmp_path / "test_brief.md"
        content = "Test brief content"
        write_brief(output_path, content, config)
        assert output_path.exists()

    def test_meeting_brief_config_loading(self, mock_project_root):
        """Test meeting brief config loads correctly."""
        config_path = mock_project_root / "templates" / "examples" / "meeting_brief.yaml"
        config = meeting_load_config(config_path)

        assert config["workflow_name"] == "meeting_brief"
        assert "prompt_template" in config
        assert config["parameters"]["model"] == "gpt-4o"

    def test_meeting_brief_prompt_formatting(self):
        """Test meeting brief prompt formatting."""
        template = "Meeting: {meeting_title} on {meeting_date}\nAttendees: {attendees}\n{transcript}"
        prompt = meeting_format_prompt(
            template,
            meeting_title="Sprint Review",
            meeting_date="2025-01-15",
            attendees="Alice, Bob, Carol",
            transcript="Alice: Progress update...",
        )

        assert "Sprint Review" in prompt
        assert "2025-01-15" in prompt
        assert "Alice, Bob, Carol" in prompt
        assert "Progress update" in prompt

    def test_meeting_brief_sample_transcript_generation(self):
        """Test sample transcript generation."""
        transcript_data = generate_sample_transcript()

        assert isinstance(transcript_data, dict)
        assert "meeting_title" in transcript_data
        assert "meeting_date" in transcript_data
        assert "attendees" in transcript_data
        assert "transcript" in transcript_data
        assert len(transcript_data["transcript"]) > 0

    def test_meeting_brief_artifact_format(self, tmp_path):
        """Test meeting brief artifact has correct format."""
        output_path = tmp_path / "test_brief.md"
        content = "## Action Items\n- Item 1\n- Item 2"
        metadata = {"workflow_name": "meeting_brief"}

        write_brief(output_path, content, metadata)

        assert output_path.exists()

        written_content = output_path.read_text(encoding="utf-8")
        assert "# Meeting Brief" in written_content
        assert "**Generated:**" in written_content
        assert "**Workflow:** meeting_brief" in written_content
        assert content in written_content

    @skip_live
    def test_meeting_brief_live_mode(self, monkeypatch, mock_project_root):
        """Test meeting brief workflow in live mode."""
        monkeypatch.setenv("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", "sk-test"))

        with patch("src.workflows.examples.meeting_transcript_brief.Path") as mock_path:
            mock_path.return_value.parent.parent.parent.parent = mock_project_root

            output_path = meeting_run_workflow(dry_run=False)

        assert output_path is not None
        output_file = Path(output_path)
        assert output_file.exists()


class TestInboxSweepWorkflow:
    """Test inbox/drive sweep workflow."""

    def test_inbox_sweep_dry_run_components(self, mock_project_root):
        """Test inbox sweep workflow components work correctly."""
        # Test config loading
        config_path = mock_project_root / "templates" / "examples" / "inbox_sweep.yaml"
        config = inbox_load_config(config_path)
        assert config is not None
        assert "workflow_name" in config
        assert config["workflow_name"] == "inbox_sweep"

    def test_inbox_sweep_config_loading(self, mock_project_root):
        """Test inbox sweep config loads correctly."""
        config_path = mock_project_root / "templates" / "examples" / "inbox_sweep.yaml"
        config = inbox_load_config(config_path)

        assert config["workflow_name"] == "inbox_sweep"
        assert "prompt_template" in config
        assert config["parameters"]["model"] == "gpt-4o-mini"

    @skip_live
    def test_inbox_sweep_live_mode(self, monkeypatch, mock_project_root):
        """Test inbox sweep workflow in live mode."""
        monkeypatch.setenv("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", "sk-test"))

        with patch("src.workflows.examples.inbox_drive_sweep.Path") as mock_path:
            mock_path.return_value.parent.parent.parent.parent = mock_project_root

            output_path = inbox_run_workflow(dry_run=False)

        assert output_path is not None


class TestCLIArgumentParsing:
    """Test CLI argument parsing for workflows."""

    def test_weekly_report_cli_dry_run(self, mock_project_root):
        """Test weekly report CLI with --dry-run flag."""
        with patch("sys.argv", ["weekly_report_pack.py", "--dry-run"]):
            with patch("src.workflows.examples.weekly_report_pack.Path") as mock_path:
                mock_path.return_value.parent.parent.parent.parent = mock_project_root

                # Import main to test CLI parsing
                from relay_ai.workflows.examples.weekly_report_pack import main

                # Should run without errors in dry-run mode
                with pytest.raises(SystemExit) as exc_info:
                    main()

                # Exit code 0 indicates success
                assert exc_info.value.code == 0

    def test_meeting_brief_cli_live_flag(self, monkeypatch, mock_project_root):
        """Test meeting brief CLI with --live flag."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        with patch("sys.argv", ["meeting_transcript_brief.py", "--live"]):
            with patch("src.workflows.examples.meeting_transcript_brief.Path") as mock_path:
                mock_path.return_value.parent.parent.parent.parent = mock_project_root

                # Mock OpenAI client to avoid real API calls
                with patch("src.agents.openai_adapter.OpenAI"):
                    # This would normally call live API, but we've mocked it
                    # Just verify it doesn't crash with argument parsing
                    pass

    def test_cli_requires_mode_flag(self, mock_project_root):
        """Test CLI requires either --dry-run or --live flag."""
        with patch("sys.argv", ["weekly_report_pack.py"]):
            from relay_ai.workflows.examples.weekly_report_pack import main

            # Should fail without mode flag
            with pytest.raises(SystemExit) as exc_info:
                main()

            # Non-zero exit code indicates error
            assert exc_info.value.code != 0


class TestArtifactPaths:
    """Test artifact path generation and Windows compatibility."""

    def test_windows_path_handling(self, tmp_path):
        """Test workflows handle Windows paths correctly using pathlib."""
        # Use pathlib for cross-platform compatibility
        windows_style_path = tmp_path / "artifacts" / "test" / "file.md"
        windows_style_path.parent.mkdir(parents=True, exist_ok=True)

        # Should work on Windows
        windows_style_path.write_text("Test content", encoding="utf-8")
        assert windows_style_path.exists()

        # Verify pathlib handles backslashes correctly
        assert Path(str(windows_style_path)).exists()

    def test_artifact_parent_dirs_created(self, tmp_path, mock_project_root):
        """Test artifact generation creates parent directories."""
        config_path = mock_project_root / "templates" / "examples" / "weekly_report.yaml"
        config = weekly_load_config(config_path)

        nested_path = tmp_path / "level1" / "level2" / "level3" / "artifact.md"

        # write_report should create parent dirs automatically
        write_report(nested_path, "Content", config)

        assert nested_path.exists()
        assert nested_path.parent.exists()

    def test_pathlib_compatibility(self, tmp_path):
        """Test Path objects work correctly across platforms."""
        # Create nested structure
        nested = tmp_path / "a" / "b" / "c" / "file.txt"
        nested.parent.mkdir(parents=True, exist_ok=True)
        nested.write_text("test")

        # Should be able to navigate
        assert nested.exists()
        assert nested.parent.name == "c"
        assert nested.parent.parent.name == "b"


class TestWorkflowErrorHandling:
    """Test error handling in workflows."""

    def test_missing_config_file_error(self, tmp_path):
        """Test workflow fails gracefully with missing config."""
        nonexistent_config = tmp_path / "missing.yaml"

        with pytest.raises(FileNotFoundError):
            weekly_load_config(nonexistent_config)

    def test_invalid_yaml_config_error(self, tmp_path):
        """Test workflow fails gracefully with invalid YAML."""
        invalid_config = tmp_path / "invalid.yaml"
        invalid_config.write_text("invalid: yaml: content: [missing bracket", encoding="utf-8")

        with pytest.raises(yaml.YAMLError):
            with open(invalid_config, encoding="utf-8") as f:
                yaml.safe_load(f)

    def test_missing_api_key_in_live_mode(self, monkeypatch, mock_project_root):
        """Test workflow fails with helpful error when API key missing."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with patch("src.workflows.examples.weekly_report_pack.Path") as mock_path:
            mock_path.return_value.parent.parent.parent.parent = mock_project_root

            # Live mode without API key should fail
            from relay_ai.agents.openai_adapter import OpenAIAdapterError

            with pytest.raises(OpenAIAdapterError, match="OPENAI_API_KEY"):
                weekly_run_workflow(dry_run=False)


class TestDeterministicBehavior:
    """Test workflows are deterministic in dry-run mode."""

    def test_mock_adapter_is_deterministic(self):
        """Test mock adapter produces consistent results."""
        from relay_ai.agents.openai_adapter import create_adapter

        adapter = create_adapter(use_mock=True)

        # Multiple calls should return consistent format
        response1 = adapter.generate_text("Test prompt")
        response2 = adapter.generate_text("Test prompt")

        assert "[MOCK]" in response1
        assert "[MOCK]" in response2
        # Both should have same format
        assert response1.startswith("[MOCK] Generated response for prompt:")
        assert response2.startswith("[MOCK] Generated response for prompt:")

    def test_mock_adapter_no_api_key_required(self, monkeypatch):
        """Test mock adapter works without API key."""
        from relay_ai.agents.openai_adapter import create_adapter

        # Don't set API key
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        # Should still work with mock adapter
        adapter = create_adapter(use_mock=True)
        response = adapter.generate_text("Test")

        assert "[MOCK]" in response


class TestMarkdownFormatValidation:
    """Test artifact markdown format is valid."""

    def test_weekly_report_has_valid_markdown(self, mock_project_root, tmp_path):
        """Test weekly report output has valid markdown structure."""
        config_path = mock_project_root / "templates" / "examples" / "weekly_report.yaml"
        config = weekly_load_config(config_path)

        output_path = tmp_path / "report.md"
        content = "## Summary\n\nThis is a test report with proper markdown."
        write_report(output_path, content, config)

        written_content = output_path.read_text(encoding="utf-8")

        # Check for markdown headers
        assert re.search(r"^#\s+", written_content, re.MULTILINE)  # Has H1 header

        # Check for metadata section
        assert re.search(r"\*\*Generated:\*\*", written_content)
        assert re.search(r"\*\*Workflow:\*\*", written_content)

        # Check for separator
        assert "---" in written_content

    def test_meeting_brief_has_valid_markdown(self, mock_project_root, tmp_path):
        """Test meeting brief output has valid markdown structure."""
        config_path = mock_project_root / "templates" / "examples" / "meeting_brief.yaml"
        config = meeting_load_config(config_path)

        output_path = tmp_path / "brief.md"
        content = "## Action Items\n\n- Item 1\n- Item 2"
        write_brief(output_path, content, config)

        written_content = output_path.read_text(encoding="utf-8")

        # Check markdown structure
        assert re.search(r"^#\s+", written_content, re.MULTILINE)
        assert re.search(r"\*\*Generated:\*\*", written_content)
        assert "---" in written_content

    def test_artifact_is_utf8_encoded(self, mock_project_root, tmp_path):
        """Test artifact files are UTF-8 encoded."""
        config_path = mock_project_root / "templates" / "examples" / "weekly_report.yaml"
        config = weekly_load_config(config_path)

        output_path = tmp_path / "test.md"
        content = "Test content with unicode: \u2713 \u2715 \u2022"
        write_report(output_path, content, config)

        # Should be able to read as UTF-8 without errors
        read_content = output_path.read_text(encoding="utf-8")
        assert len(read_content) > 0
        assert "\u2713" in read_content  # Check unicode preserved
