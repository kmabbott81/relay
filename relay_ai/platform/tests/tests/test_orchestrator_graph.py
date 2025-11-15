"""
Tests for DAG graph validation and topological sorting.
"""

import pytest

from relay_ai.orchestrator.graph import (
    DAG,
    CycleDetectedError,
    Task,
    ValidationError,
    merge_payloads,
    toposort,
    validate,
)


def test_valid_dag_validates():
    """Test that a valid DAG passes validation."""
    tasks = [
        Task(id="t1", workflow_ref="w1", params={}, depends_on=[]),
        Task(id="t2", workflow_ref="w2", params={}, depends_on=["t1"]),
    ]
    dag = DAG(name="test_dag", tasks=tasks)

    # Should not raise
    validate(dag)


def test_cycle_detected():
    """Test that cycles are detected with clear error."""
    tasks = [
        Task(id="t1", workflow_ref="w1", depends_on=["t2"]),
        Task(id="t2", workflow_ref="w2", depends_on=["t1"]),
    ]
    dag = DAG(name="test_dag", tasks=tasks)

    with pytest.raises(CycleDetectedError, match="Cycle detected"):
        validate(dag)


def test_namespaced_merge_avoids_clobber():
    """Test that merge_payloads namespaces keys to avoid collisions."""
    upstream = {
        "task1": {"result": "foo", "count": 10},
        "task2": {"result": "bar", "count": 20},
    }

    merged = merge_payloads(upstream)

    # Check namespacing prevents clobber
    assert merged["task1__result"] == "foo"
    assert merged["task1__count"] == 10
    assert merged["task2__result"] == "bar"
    assert merged["task2__count"] == 20

    # No un-namespaced keys
    assert "result" not in merged
    assert "count" not in merged


def test_toposort_orders_correctly():
    """Test topological sort produces correct order."""
    tasks = [
        Task(id="t3", workflow_ref="w3", depends_on=["t1", "t2"]),
        Task(id="t1", workflow_ref="w1", depends_on=[]),
        Task(id="t2", workflow_ref="w2", depends_on=["t1"]),
    ]
    dag = DAG(name="test_dag", tasks=tasks)

    ordered = toposort(dag)
    ordered_ids = [t.id for t in ordered]

    # t1 must come before t2 and t3
    assert ordered_ids.index("t1") < ordered_ids.index("t2")
    assert ordered_ids.index("t1") < ordered_ids.index("t3")
    # t2 must come before t3
    assert ordered_ids.index("t2") < ordered_ids.index("t3")


def test_empty_dag_fails_validation():
    """Test that empty DAG raises ValidationError."""
    dag = DAG(name="empty_dag", tasks=[])

    with pytest.raises(ValidationError, match="at least one task"):
        validate(dag)


def test_invalid_dependency_fails_validation():
    """Test that referencing non-existent task fails validation."""
    tasks = [
        Task(id="t1", workflow_ref="w1", depends_on=["nonexistent"]),
    ]
    dag = DAG(name="test_dag", tasks=tasks)

    with pytest.raises(ValidationError, match="non-existent task"):
        validate(dag)


def test_duplicate_task_ids_fails_validation():
    """Test that duplicate task IDs fail validation."""
    tasks = [
        Task(id="t1", workflow_ref="w1"),
        Task(id="t1", workflow_ref="w2"),  # Duplicate ID
    ]
    dag = DAG(name="test_dag", tasks=tasks)

    with pytest.raises(ValidationError, match="Duplicate task IDs"):
        validate(dag)
