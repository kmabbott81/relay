"""Tests for template metrics tagging."""

import json
import tempfile
from pathlib import Path

from src.metrics import filter_runs_by_template, load_runs, summarize_template_kpis


def test_load_runs_includes_template_fields():
    """Metrics DataFrame should include template name, version, and key."""
    # Create a temporary template artifact
    with tempfile.TemporaryDirectory() as tmpdir:
        artifact_dir = Path(tmpdir) / "ui" / "templates"
        artifact_dir.mkdir(parents=True)

        artifact = {
            "template": {"name": "Test Template", "version": "1.0", "key": "test_template", "context": "markdown"},
            "inputs": {"name": "Alice"},
            "provenance": {
                "template_body": "Hello {{name}}",
                "resolved_inputs": {"name": "Alice"},
                "timestamp": 1633024800,
            },
            "result": {
                "status": "published",
                "provider": "openai/gpt-4o",
                "text": "Hello Alice",
                "reason": "",
                "usage": [],
            },
            "cost_projection": {"cost_usd": 0.0123, "tokens_estimated": 1500, "margin_pct": 50.0},
        }

        artifact_file = artifact_dir / "test_artifact.json"
        artifact_file.write_text(json.dumps(artifact), encoding="utf-8")

        # Load runs
        df = load_runs(tmpdir)

        assert not df.empty
        assert "template_name" in df.columns
        assert "template_version" in df.columns
        assert "template_key" in df.columns

        # Check values
        row = df.iloc[0]
        assert row["template_name"] == "Test Template"
        assert row["template_version"] == "1.0"
        assert row["template_key"] == "test_template"


def test_filter_runs_by_template():
    """Should be able to filter runs by template name."""
    with tempfile.TemporaryDirectory() as tmpdir:
        artifact_dir = Path(tmpdir) / "ui" / "templates"
        artifact_dir.mkdir(parents=True)

        # Create two template artifacts
        for i, template_name in enumerate(["Template A", "Template B"]):
            artifact = {
                "template": {"name": template_name, "version": "1.0", "key": f"template_{i}", "context": "markdown"},
                "inputs": {},
                "provenance": {"template_body": "Test", "resolved_inputs": {}, "timestamp": 1633024800 + i},
                "result": {"status": "published", "provider": "test", "text": "output", "reason": "", "usage": []},
            }

            artifact_file = artifact_dir / f"test_artifact_{i}.json"
            artifact_file.write_text(json.dumps(artifact), encoding="utf-8")

        # Load and filter
        df = load_runs(tmpdir)
        assert len(df) == 2

        filtered = filter_runs_by_template(df, "Template A")
        assert len(filtered) == 1
        assert filtered.iloc[0]["template_name"] == "Template A"


def test_summarize_template_kpis():
    """Should calculate KPIs grouped by template."""
    with tempfile.TemporaryDirectory() as tmpdir:
        artifact_dir = Path(tmpdir) / "ui" / "templates"
        artifact_dir.mkdir(parents=True)

        # Create multiple runs for same template
        for i in range(3):
            artifact = {
                "template": {"name": "Test Template", "version": "1.0", "key": "test_template", "context": "markdown"},
                "inputs": {},
                "provenance": {"template_body": "Test", "resolved_inputs": {}, "timestamp": 1633024800 + i},
                "result": {
                    "status": "published" if i < 2 else "advisory_only",
                    "provider": "test",
                    "text": "output",
                    "reason": "",
                    "usage": [],
                },
                "cost_projection": {
                    "cost_usd": 0.01 + i * 0.005,
                    "tokens_estimated": 1000 + i * 100,
                    "margin_pct": 50.0,
                },
            }

            artifact_file = artifact_dir / f"test_artifact_{i}.json"
            artifact_file.write_text(json.dumps(artifact), encoding="utf-8")

        # Load and summarize
        df = load_runs(tmpdir)
        kpis = summarize_template_kpis(df)

        assert not kpis.empty
        assert "template_name" in kpis.columns
        assert "template_version" in kpis.columns
        assert "total_runs" in kpis.columns
        assert "published_runs" in kpis.columns
        assert "advisory_runs" in kpis.columns
        assert "avg_cost" in kpis.columns
        assert "avg_tokens" in kpis.columns
        assert "success_rate" in kpis.columns

        # Check values
        row = kpis.iloc[0]
        assert row["template_name"] == "Test Template"
        assert row["total_runs"] == 3
        assert row["published_runs"] == 2
        assert row["advisory_runs"] == 1
        assert row["success_rate"] == 2 / 3


def test_template_kpis_multiple_templates():
    """Should group KPIs by different templates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        artifact_dir = Path(tmpdir) / "ui" / "templates"
        artifact_dir.mkdir(parents=True)

        # Create runs for two different templates
        templates = [("Template A", 2), ("Template B", 3)]

        idx = 0
        for template_name, count in templates:
            for _ in range(count):
                artifact = {
                    "template": {
                        "name": template_name,
                        "version": "1.0",
                        "key": template_name.lower().replace(" ", "_"),
                        "context": "markdown",
                    },
                    "inputs": {},
                    "provenance": {"template_body": "Test", "resolved_inputs": {}, "timestamp": 1633024800 + idx},
                    "result": {"status": "published", "provider": "test", "text": "output", "reason": "", "usage": []},
                    "cost_projection": {"cost_usd": 0.01, "tokens_estimated": 1000, "margin_pct": 50.0},
                }

                artifact_file = artifact_dir / f"test_artifact_{idx}.json"
                artifact_file.write_text(json.dumps(artifact), encoding="utf-8")
                idx += 1

        # Load and summarize
        df = load_runs(tmpdir)
        kpis = summarize_template_kpis(df)

        assert len(kpis) == 2
        assert set(kpis["template_name"]) == {"Template A", "Template B"}

        # Template B should be first (more runs)
        assert kpis.iloc[0]["template_name"] == "Template B"
        assert kpis.iloc[0]["total_runs"] == 3


def test_metrics_handles_non_template_artifacts():
    """Metrics should handle mix of template and non-template artifacts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create template artifact
        artifact_dir = Path(tmpdir) / "ui" / "templates"
        artifact_dir.mkdir(parents=True)

        template_artifact = {
            "template": {"name": "Test Template", "version": "1.0", "key": "test", "context": "markdown"},
            "provenance": {"timestamp": 1633024800},
            "result": {"status": "published", "provider": "test", "text": "output", "usage": []},
        }

        artifact_file = artifact_dir / "template_artifact.json"
        artifact_file.write_text(json.dumps(template_artifact), encoding="utf-8")

        # Create non-template artifact (regular workflow)
        regular_artifact = {
            "run_metadata": {"timestamp": "2025-10-01T12:00:00", "task": "test task"},
            "publish": {"status": "published", "provider": "test"},
            "provenance": {},
        }

        regular_file = Path(tmpdir) / "regular_artifact.json"
        regular_file.write_text(json.dumps(regular_artifact), encoding="utf-8")

        # Load runs
        df = load_runs(tmpdir)

        assert len(df) == 2

        # Template artifact should have template fields
        template_row = df[df["template_name"] == "Test Template"].iloc[0]
        assert template_row["template_name"] == "Test Template"

        # Regular artifact should have empty template fields
        regular_row = df[df["template_name"] == ""].iloc[0]
        assert regular_row["template_name"] == ""
        assert regular_row["template_version"] == ""
