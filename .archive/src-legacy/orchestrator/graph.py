"""
DAG Core - Task and DAG models with validation and topological sorting.
"""

from dataclasses import dataclass, field


@dataclass
class Task:
    """Represents a single task in a DAG."""

    id: str
    workflow_ref: str  # Reference to workflow in WORKFLOW_MAP (or empty for checkpoints)
    params: dict = field(default_factory=dict)
    retries: int = 0
    depends_on: list[str] = field(default_factory=list)
    type: str = "workflow"  # "workflow" or "checkpoint"

    # Checkpoint-specific fields
    prompt: str | None = None  # Human-readable approval prompt
    required_role: str | None = None  # RBAC role required to approve
    inputs: dict | None = None  # Expected input schema for approval


@dataclass
class DAG:
    """Represents a Directed Acyclic Graph of tasks."""

    name: str
    tasks: list[Task]
    tenant_id: str = "local-dev"


class CycleDetectedError(Exception):
    """Raised when a cycle is detected in the DAG."""

    pass


class ValidationError(Exception):
    """Raised when DAG validation fails."""

    pass


def validate(dag: DAG) -> None:
    """
    Validate a DAG for basic correctness.

    Args:
        dag: DAG to validate

    Raises:
        ValidationError: If validation fails
        CycleDetectedError: If a cycle is detected
    """
    if not dag.tasks:
        raise ValidationError("DAG must have at least one task")

    task_ids = {task.id for task in dag.tasks}

    # Check for duplicate task IDs
    if len(task_ids) != len(dag.tasks):
        raise ValidationError("Duplicate task IDs found")

    # Check dependencies reference valid tasks
    for task in dag.tasks:
        for dep in task.depends_on:
            if dep not in task_ids:
                raise ValidationError(f"Task '{task.id}' depends on non-existent task '{dep}'")

    # Check for cycles
    try:
        toposort(dag)
    except CycleDetectedError:
        raise


def toposort(dag: DAG) -> list[Task]:
    """
    Perform topological sort on DAG tasks.

    Args:
        dag: DAG to sort

    Returns:
        List of tasks in topological order

    Raises:
        CycleDetectedError: If a cycle is detected
    """
    # Build dependency graph
    in_degree = {task.id: 0 for task in dag.tasks}
    graph = {task.id: task for task in dag.tasks}

    for task in dag.tasks:
        for _ in task.depends_on:
            in_degree[task.id] += 1

    # Kahn's algorithm
    queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
    result = []

    while queue:
        current_id = queue.pop(0)
        result.append(graph[current_id])

        # Find tasks that depend on current
        for task in dag.tasks:
            if current_id in task.depends_on:
                in_degree[task.id] -= 1
                if in_degree[task.id] == 0:
                    queue.append(task.id)

    if len(result) != len(dag.tasks):
        raise CycleDetectedError(f"Cycle detected in DAG '{dag.name}'")

    return result


def merge_payloads(upstream: dict[str, dict]) -> dict:
    """
    Merge upstream task outputs into a single namespaced dict.

    Args:
        upstream: Dict mapping task_id -> output dict

    Returns:
        Merged dict with namespaced keys to avoid clobber

    Example:
        upstream = {
            "task1": {"result": "foo"},
            "task2": {"result": "bar"}
        }
        Returns: {
            "task1__result": "foo",
            "task2__result": "bar"
        }
    """
    merged = {}
    for task_id, outputs in upstream.items():
        for key, value in outputs.items():
            namespaced_key = f"{task_id}__{key}"
            merged[namespaced_key] = value
    return merged
