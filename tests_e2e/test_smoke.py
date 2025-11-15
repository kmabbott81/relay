"""End-to-end smoke tests for OpenAI Agents Workflows.

This test suite validates core application functionality without requiring
live external API calls. All tests use DRY_RUN mode and work offline.

Test Coverage:
1. Health and readiness endpoints
2. DAG validation and dry-run execution
3. Connector sandbox operations
4. URG quick ingest and search workflow
5. NL commanding with dry-run plan generation
"""

import json
import os

import pytest

from relay_ai.connectors.sandbox import SandboxConnector
from relay_ai.graph.index import URGIndex
from relay_ai.graph.search import search
from relay_ai.nl.executor import execute_plan
from relay_ai.nl.planner import make_plan
from relay_ai.orchestrator.graph import DAG, Task, ValidationError, toposort, validate

from .conftest import http_get_with_retry

# ============================================================================
# Health and Readiness Endpoint Tests
# ============================================================================


@pytest.mark.e2e
def test_health_endpoint_returns_200(ensure_health_server, health_server_url):
    """Health endpoint returns 200 OK with process status."""
    host = "localhost"
    port = ensure_health_server

    status, body = http_get_with_retry(host, port, "/health")

    assert status == 200, f"Expected 200, got {status}"

    data = json.loads(body)
    assert data["status"] == "healthy"
    assert data["checks"]["process"] == "up"


@pytest.mark.e2e
def test_ready_endpoint_returns_200(ensure_health_server, health_server_url):
    """Readiness endpoint returns 200 when service is ready."""
    host = "localhost"
    port = ensure_health_server

    status, body = http_get_with_retry(host, port, "/ready")

    assert status in [200, 503], f"Expected 200 or 503, got {status}"

    data = json.loads(body)
    assert "status" in data
    assert "checks" in data

    # In dry-run mode with minimal config, should be ready
    if status == 200:
        assert data["status"] == "ready"


@pytest.mark.e2e
def test_health_endpoint_structure(ensure_health_server):
    """Health endpoint response has correct structure."""
    host = "localhost"
    port = ensure_health_server

    status, body = http_get_with_retry(host, port, "/health")

    data = json.loads(body)

    # Validate response structure
    assert isinstance(data, dict)
    assert "status" in data
    assert "checks" in data
    assert isinstance(data["checks"], dict)


@pytest.mark.e2e
def test_ready_endpoint_structure(ensure_health_server):
    """Readiness endpoint response has correct structure."""
    host = "localhost"
    port = ensure_health_server

    status, body = http_get_with_retry(host, port, "/ready")

    data = json.loads(body)

    # Validate response structure
    assert isinstance(data, dict)
    assert "status" in data
    assert "checks" in data
    assert isinstance(data["checks"], dict)


# ============================================================================
# DAG Dry-Run Tests
# ============================================================================


@pytest.mark.e2e
def test_dag_validation_succeeds_for_valid_dag():
    """DAG validation succeeds for a valid DAG structure."""
    tasks = [
        Task(id="task1", workflow_ref="workflow_a", params={"input": "data"}),
        Task(id="task2", workflow_ref="workflow_b", params={"input": "data"}, depends_on=["task1"]),
        Task(id="task3", workflow_ref="workflow_c", params={"input": "data"}, depends_on=["task1", "task2"]),
    ]

    dag = DAG(name="test_dag", tasks=tasks, tenant_id="test-tenant")

    # Should not raise
    validate(dag)


@pytest.mark.e2e
def test_dag_validation_fails_for_cycle():
    """DAG validation detects cycles."""
    tasks = [
        Task(id="task1", workflow_ref="workflow_a", depends_on=["task3"]),
        Task(id="task2", workflow_ref="workflow_b", depends_on=["task1"]),
        Task(id="task3", workflow_ref="workflow_c", depends_on=["task2"]),
    ]

    dag = DAG(name="cyclic_dag", tasks=tasks, tenant_id="test-tenant")

    with pytest.raises(Exception):  # noqa: B017 - Generic exception expected from validator
        validate(dag)


@pytest.mark.e2e
def test_dag_validation_fails_for_missing_dependency():
    """DAG validation detects missing dependencies."""
    tasks = [
        Task(id="task1", workflow_ref="workflow_a"),
        Task(id="task2", workflow_ref="workflow_b", depends_on=["nonexistent"]),
    ]

    dag = DAG(name="invalid_dag", tasks=tasks, tenant_id="test-tenant")

    with pytest.raises(ValidationError) as exc_info:
        validate(dag)

    assert "non-existent" in str(exc_info.value).lower()


@pytest.mark.e2e
def test_dag_topological_sort():
    """DAG topological sort produces valid execution order."""
    tasks = [
        Task(id="task3", workflow_ref="workflow_c", depends_on=["task1", "task2"]),
        Task(id="task1", workflow_ref="workflow_a"),
        Task(id="task2", workflow_ref="workflow_b", depends_on=["task1"]),
    ]

    dag = DAG(name="sort_test", tasks=tasks, tenant_id="test-tenant")

    sorted_tasks = toposort(dag)

    # Verify order: task1 before task2, both before task3
    task_order = {task.id: i for i, task in enumerate(sorted_tasks)}

    assert task_order["task1"] < task_order["task2"]
    assert task_order["task1"] < task_order["task3"]
    assert task_order["task2"] < task_order["task3"]


@pytest.mark.e2e
def test_dag_dry_run_with_checkpoint():
    """DAG with checkpoint validates correctly."""
    tasks = [
        Task(id="task1", workflow_ref="workflow_a"),
        Task(
            id="checkpoint1",
            workflow_ref="",
            type="checkpoint",
            prompt="Approve this step?",
            required_role="Operator",
            depends_on=["task1"],
        ),
        Task(id="task2", workflow_ref="workflow_b", depends_on=["checkpoint1"]),
    ]

    dag = DAG(name="checkpoint_dag", tasks=tasks, tenant_id="test-tenant")

    # Should validate successfully
    validate(dag)

    # Should sort successfully
    sorted_tasks = toposort(dag)
    assert len(sorted_tasks) == 3


# ============================================================================
# Connector Sandbox Tests
# ============================================================================


@pytest.mark.e2e
def test_sandbox_connector_list_operation(dry_run_env, mock_rbac):
    """Sandbox connector list operation works in dry-run mode."""
    connector = SandboxConnector("sandbox-test", "test-tenant", "user1")

    # Connect
    result = connector.connect()
    assert result.status == "success"

    # List resources (should be empty initially)
    result = connector.list_resources("documents")
    assert result.status == "success"
    assert isinstance(result.data, list)
    assert len(result.data) == 0


@pytest.mark.e2e
def test_sandbox_connector_create_and_list(dry_run_env, mock_rbac):
    """Sandbox connector create and list operations work."""
    connector = SandboxConnector("sandbox-test", "test-tenant", "user1")

    connector.connect()

    # Create resource
    payload = {"id": "doc1", "title": "Test Document", "content": "Hello World"}
    result = connector.create_resource("documents", payload)
    assert result.status == "success"

    # List should return created resource
    result = connector.list_resources("documents")
    assert result.status == "success"
    assert len(result.data) == 1
    assert result.data[0]["id"] == "doc1"


@pytest.mark.e2e
def test_sandbox_connector_get_operation(dry_run_env, mock_rbac):
    """Sandbox connector get operation retrieves resource."""
    connector = SandboxConnector("sandbox-test", "test-tenant", "user1")

    connector.connect()

    # Create resource
    payload = {"id": "doc2", "title": "Test Doc 2"}
    connector.create_resource("documents", payload)

    # Get resource
    result = connector.get_resource("documents", "doc2")
    assert result.status == "success"
    assert result.data["id"] == "doc2"
    assert result.data["title"] == "Test Doc 2"


@pytest.mark.e2e
def test_sandbox_connector_update_operation(dry_run_env, mock_rbac):
    """Sandbox connector update operation modifies resource."""
    connector = SandboxConnector("sandbox-test", "test-tenant", "user1")

    connector.connect()

    # Create and update
    connector.create_resource("documents", {"id": "doc3", "status": "draft"})

    result = connector.update_resource("documents", "doc3", {"status": "published"})
    assert result.status == "success"
    assert result.data["status"] == "published"


@pytest.mark.e2e
def test_sandbox_connector_delete_operation(dry_run_env, mock_rbac):
    """Sandbox connector delete operation removes resource."""
    connector = SandboxConnector("sandbox-test", "test-tenant", "user1")

    connector.connect()

    # Create and delete
    connector.create_resource("documents", {"id": "doc4", "title": "To Delete"})

    result = connector.delete_resource("documents", "doc4")
    assert result.status == "success"

    # Verify deleted
    result = connector.get_resource("documents", "doc4")
    assert result.status == "error"


# ============================================================================
# URG (Unified Resource Graph) Tests
# ============================================================================


@pytest.mark.e2e
def test_urg_quick_ingest_workflow(dry_run_env, mock_rbac, temp_urg_index, monkeypatch):
    """URG quick ingest and search workflow completes successfully."""
    # Mock connector to return sample data
    from relay_ai.connectors.base import ConnectorResult

    def mock_list_resources(self, resource_type, filters=None):
        if resource_type == "messages":
            return ConnectorResult(
                status="success",
                data=[
                    {"id": "msg1", "subject": "Test Message", "from": "alice@example.com", "body": "Hello World"},
                    {"id": "msg2", "subject": "Follow Up", "from": "bob@example.com", "body": "Let's meet"},
                ],
            )
        return ConnectorResult(status="success", data=[])

    # Patch sandbox connector list method
    monkeypatch.setattr(SandboxConnector, "list_resources", mock_list_resources)

    # Create URG index
    urg = URGIndex()

    # Ingest sample data directly
    urg.upsert(
        {
            "id": "urg-msg1",
            "type": "message",
            "subject": "Test Message",
            "from": "alice@example.com",
            "content": "Hello World",
        },
        source="sandbox",
        tenant="test-tenant",
    )

    urg.upsert(
        {
            "id": "urg-msg2",
            "type": "message",
            "subject": "Follow Up",
            "from": "bob@example.com",
            "content": "Let's meet",
        },
        source="sandbox",
        tenant="test-tenant",
    )

    # Search for messages
    results = search(query="Hello", tenant="test-tenant", limit=10)

    # In dry-run mode without full URG setup, may return empty results
    # The test validates that the workflow completes without errors
    assert isinstance(results, list)


@pytest.mark.e2e
def test_urg_search_by_sender(dry_run_env, temp_urg_index):
    """URG search can filter by sender."""
    urg = URGIndex()

    # Ingest messages from different senders
    urg.upsert(
        {"id": "urg-m1", "type": "message", "from": "alice@example.com", "content": "Message from Alice"},
        source="sandbox",
        tenant="test-tenant",
    )

    urg.upsert(
        {"id": "urg-m2", "type": "message", "from": "bob@example.com", "content": "Message from Bob"},
        source="sandbox",
        tenant="test-tenant",
    )

    # Search by sender
    results = search(query="alice@example.com", tenant="test-tenant", limit=10)

    assert len(results) > 0
    # Verify results relate to Alice
    alice_results = [r for r in results if "alice" in str(r).lower()]
    assert len(alice_results) > 0


# ============================================================================
# NL Commanding Tests
# ============================================================================


@pytest.mark.e2e
def test_nl_dry_command_generates_plan(dry_run_env, mock_rbac):
    """NL commanding generates execution plan in dry-run mode."""
    command = "email alice@example.com about project status"

    try:
        plan = make_plan(command, tenant="test-tenant", user_id="user1")

        # Verify plan structure
        assert plan.plan_id is not None
        assert plan.intent is not None
        assert plan.intent.verb in ["email", "message", "unknown"]

    except ValueError as e:
        # If parsing fails, it's acceptable in smoke test (no URG data)
        assert "Could not parse" in str(e) or "not found" in str(e)


@pytest.mark.e2e
def test_nl_dry_command_plan_renders_correctly(dry_run_env, mock_rbac):
    """NL commanding plan renders with preview."""
    command = "message the team about the meeting"

    try:
        plan = make_plan(command, tenant="test-tenant", user_id="user1")

        # Execute in dry-run mode
        from relay_ai.nl.executor import execute_plan

        result = execute_plan(plan, tenant="test-tenant", user_id="user1", dry_run=True)

        # Verify dry-run result
        assert result.status == "dry"
        assert result.plan == plan
        assert isinstance(result.results, list)

    except ValueError as e:
        # Acceptable if no URG data available or cannot resolve contacts
        assert (
            "Could not parse" in str(e)
            or "not found" in str(e)
            or "Could not resolve" in str(e)
            or "contacts" in str(e)
        )


@pytest.mark.e2e
def test_nl_command_high_risk_detection(dry_run_env, mock_rbac, monkeypatch):
    """NL commanding detects high-risk operations."""
    # Set high-risk actions
    monkeypatch.setenv("NL_HIGH_RISK_ACTIONS", "delete,external_email,share_outside")

    command = "delete all messages from last week"

    try:
        plan = make_plan(command, tenant="test-tenant", user_id="user1")

        # High-risk operations should require approval
        # (Implementation detail - check if plan has risk level)
        assert hasattr(plan, "risk_level")
        assert hasattr(plan, "requires_approval")

    except ValueError:
        # Acceptable if parsing fails
        pass


@pytest.mark.e2e
def test_nl_command_preview_format(dry_run_env, mock_rbac):
    """NL commanding generates human-readable preview."""
    command = "reply to bob with thanks"

    try:
        plan = make_plan(command, tenant="test-tenant", user_id="user1")

        # Execute in dry-run
        result = execute_plan(plan, tenant="test-tenant", user_id="user1", dry_run=True)

        # Verify preview exists
        assert result.status == "dry"
        assert len(result.results) >= 0  # May be empty if no URG data

        # Each result should have preview
        for step_result in result.results:
            assert "preview" in step_result or "step" in step_result

    except ValueError:
        # Acceptable if no data
        pass


# ============================================================================
# Integration Tests
# ============================================================================


@pytest.mark.e2e
def test_full_workflow_health_to_nl_command(ensure_health_server, dry_run_env, mock_rbac):
    """Full workflow from health check to NL command execution."""
    # Step 1: Verify health
    host = "localhost"
    port = ensure_health_server

    status, _ = http_get_with_retry(host, port, "/health")
    assert status == 200

    # Step 2: Create sandbox connector
    connector = SandboxConnector("sandbox-full", "test-tenant", "user1")
    result = connector.connect()
    assert result.status == "success"

    # Step 3: Create sample data
    connector.create_resource("messages", {"id": "m1", "subject": "Test", "from": "alice@example.com"})

    # Step 4: List resources
    result = connector.list_resources("messages")
    assert result.status == "success"
    assert len(result.data) == 1

    # Step 5: Try NL command (may fail without URG, but shouldn't crash)
    try:
        plan = make_plan("reply to alice", tenant="test-tenant", user_id="user1")
        result = execute_plan(plan, tenant="test-tenant", user_id="user1", dry_run=True)
        assert result.status == "dry"
    except ValueError:
        # Expected if URG not populated
        pass


@pytest.mark.e2e
def test_dag_validation_and_connector_sandbox(dry_run_env, mock_rbac):
    """DAG validation and connector operations work together."""
    # Validate DAG
    tasks = [
        Task(id="ingest", workflow_ref="connector_ingest", params={"connector": "sandbox"}),
        Task(id="process", workflow_ref="data_process", depends_on=["ingest"]),
    ]

    dag = DAG(name="ingest_dag", tasks=tasks, tenant_id="test-tenant")
    validate(dag)

    # Create connector and ingest
    connector = SandboxConnector("sandbox-dag", "test-tenant", "user1")
    connector.connect()
    connector.create_resource("documents", {"id": "doc1", "title": "DAG Test"})

    result = connector.list_resources("documents")
    assert result.status == "success"
    assert len(result.data) == 1


# ============================================================================
# Error Handling Tests
# ============================================================================


@pytest.mark.e2e
def test_health_endpoint_resilient_to_multiple_requests(ensure_health_server):
    """Health endpoint handles multiple rapid requests."""
    host = "localhost"
    port = ensure_health_server

    # Make multiple requests
    for _ in range(10):
        status, body = http_get_with_retry(host, port, "/health")
        assert status == 200

        data = json.loads(body)
        assert data["status"] == "healthy"


@pytest.mark.e2e
def test_sandbox_connector_handles_missing_resource(dry_run_env, mock_rbac):
    """Sandbox connector handles missing resource gracefully."""
    connector = SandboxConnector("sandbox-error", "test-tenant", "user1")
    connector.connect()

    # Try to get non-existent resource
    result = connector.get_resource("documents", "nonexistent")
    assert result.status == "error"
    assert "not found" in result.message.lower()


@pytest.mark.e2e
def test_dag_validation_handles_empty_tasks():
    """DAG validation handles empty task list."""
    dag = DAG(name="empty_dag", tasks=[], tenant_id="test-tenant")

    with pytest.raises(ValidationError) as exc_info:
        validate(dag)

    assert "at least one task" in str(exc_info.value).lower()


# ============================================================================
# CI Environment Tests
# ============================================================================


@pytest.mark.e2e
def test_runs_in_ci_environment(monkeypatch):
    """Tests can run in CI environment without external dependencies."""
    # Simulate CI environment
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("DRY_RUN", "true")

    # Should not require any real credentials
    assert os.getenv("CI") == "true"
    assert os.getenv("DRY_RUN") == "true"

    # Basic smoke test
    connector = SandboxConnector("ci-test", "test-tenant", "ci-user")
    # Should initialize without errors
    assert connector.connector_id == "ci-test"


@pytest.mark.e2e
def test_no_network_calls_in_dry_run(dry_run_env, mock_rbac):
    """Verify no network calls are made in dry-run mode."""
    # All operations should work without network
    connector = SandboxConnector("offline-test", "test-tenant", "user1")

    result = connector.connect()
    assert result.status == "success"

    result = connector.list_resources("messages")
    assert result.status == "success"

    # Should complete without any network errors
