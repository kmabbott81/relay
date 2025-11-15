"""
Tests for DAG Integration with Templates (Sprint 32)

Covers template-based DAG execution via adapter.
"""

import json

import pytest
import yaml

from relay_ai.orchestrator.graph import DAG, Task
from relay_ai.orchestrator.runner import run_dag
from relay_ai.workflows.adapter import template_adapter


@pytest.fixture
def setup_template_system(tmp_path, monkeypatch):
    """Setup complete template system for testing."""
    # Setup paths
    registry_dir = tmp_path / "registry"
    schemas_dir = tmp_path / "schemas"
    registry_dir.mkdir()
    schemas_dir.mkdir()

    monkeypatch.setenv("TEMPLATE_REGISTRY_PATH", str(registry_dir))
    monkeypatch.setenv("TEMPLATE_SCHEMAS_PATH", str(schemas_dir))
    monkeypatch.setenv("USER_RBAC_ROLE", "Author")

    # Create template
    template_yaml = registry_dir / "test_workflow_1.0.yaml"
    template_yaml.write_text(yaml.dump({"workflow_ref": "inbox_drive_sweep", "description": "Test", "parameters": {}}))

    # Create schema
    schema_json = schemas_dir / "test_workflow_1.0.schema.json"
    schema_json.write_text(json.dumps({"fields": {"inbox_items": {"type": "string", "required": True}}}))

    # Register template
    from relay_ai.template_registry.registry import register

    register(
        name="test_workflow",
        version="1.0",
        workflow_ref="inbox_drive_sweep",
        schema_ref="test_workflow_1.0.schema.json",
    )


def test_template_adapter_success(setup_template_system):
    """Test template adapter with valid params."""
    result = template_adapter({"template_name": "test_workflow", "template_version": "1.0", "inbox_items": "test"})

    assert isinstance(result, dict)
    assert "summary" in result


def test_template_adapter_missing_template_name():
    """Test template adapter without template_name."""
    with pytest.raises(ValueError, match="requires template_name"):
        template_adapter({"param": "value"})


def test_template_adapter_validation_failure(setup_template_system):
    """Test template adapter with invalid params."""
    with pytest.raises(ValueError, match="Parameter validation failed"):
        template_adapter({"template_name": "test_workflow", "template_version": "1.0"})
        # Missing required inbox_items


def test_dag_with_template_task(setup_template_system, tmp_path, monkeypatch):
    """Test DAG execution with template-based task."""
    # Setup events path
    events_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("ORCH_EVENTS_PATH", str(events_path))

    # Create DAG with template task
    dag = DAG(
        name="test_dag",
        tasks=[
            Task(
                id="template_task",
                type="workflow",
                workflow_ref="template",
                params={
                    "template_name": "test_workflow",
                    "template_version": "1.0",
                    "inbox_items": "test items",
                },
                depends_on=[],
            )
        ],
        tenant_id="test-tenant",
    )

    # Run DAG
    result = run_dag(dag, tenant="test-tenant", events_path=str(events_path))

    assert result["status"] == "success"
    assert result["tasks_succeeded"] == 1
    assert "template_task" in result["task_outputs"]


def test_dag_with_template_task_dry_run(setup_template_system, tmp_path, monkeypatch):
    """Test dry-run with template task."""
    events_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("ORCH_EVENTS_PATH", str(events_path))

    dag = DAG(
        name="test_dag",
        tasks=[
            Task(
                id="template_task",
                type="workflow",
                workflow_ref="template",
                params={"template_name": "test_workflow"},
                depends_on=[],
            )
        ],
        tenant_id="test-tenant",
    )

    result = run_dag(dag, tenant="test-tenant", dry_run=True)

    assert result["dry_run"] is True
    assert result["tasks_planned"] == 1


def test_dag_with_chained_template_tasks(setup_template_system, tmp_path, monkeypatch):
    """Test DAG with multiple template tasks."""
    events_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("ORCH_EVENTS_PATH", str(events_path))

    dag = DAG(
        name="test_dag",
        tasks=[
            Task(
                id="task1",
                type="workflow",
                workflow_ref="template",
                params={
                    "template_name": "test_workflow",
                    "template_version": "1.0",
                    "inbox_items": "items",
                },
                depends_on=[],
            ),
            Task(
                id="task2",
                type="workflow",
                workflow_ref="template",
                params={
                    "template_name": "test_workflow",
                    "template_version": "1.0",
                    "inbox_items": "more items",
                },
                depends_on=["task1"],
            ),
        ],
        tenant_id="test-tenant",
    )

    result = run_dag(dag, tenant="test-tenant", events_path=str(events_path))

    assert result["status"] == "success"
    assert result["tasks_succeeded"] == 2
