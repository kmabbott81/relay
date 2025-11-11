"""Tests for hybrid queue router."""

import pytest

from relay_ai.queue_strategy import (
    HybridQueueRouter,
    QueueBackend,
    QueueConfig,
    TaskClass,
    TaskDefinition,
    enqueue_task,
    get_queue_router,
)


def sample_task_function(x: int, y: int) -> int:
    """Sample task function for testing."""
    return x + y


def test_queue_config_defaults_to_local():
    """Queue config defaults to local backend."""
    config = QueueConfig(realtime_backend=QueueBackend.LOCAL, bulk_backend=QueueBackend.LOCAL)

    assert config.realtime_backend == QueueBackend.LOCAL
    assert config.bulk_backend == QueueBackend.LOCAL


def test_router_initialization():
    """Router initializes with config."""
    config = QueueConfig(realtime_backend=QueueBackend.LOCAL, bulk_backend=QueueBackend.LOCAL)

    router = HybridQueueRouter(config=config)

    assert router.config.realtime_backend == QueueBackend.LOCAL
    assert router.config.bulk_backend == QueueBackend.LOCAL


def test_enqueue_realtime_task_local():
    """Enqueue realtime task to local backend."""
    config = QueueConfig(realtime_backend=QueueBackend.LOCAL, bulk_backend=QueueBackend.LOCAL)
    router = HybridQueueRouter(config=config)

    task = TaskDefinition(
        task_id="task1",
        task_class=TaskClass.REALTIME,
        function=sample_task_function,
        args=(2, 3),
        tenant_id="tenant1",
    )

    job_id = router.enqueue(task)

    assert job_id == "task1"


def test_enqueue_bulk_task_local():
    """Enqueue bulk task to local backend."""
    config = QueueConfig(realtime_backend=QueueBackend.LOCAL, bulk_backend=QueueBackend.LOCAL)
    router = HybridQueueRouter(config=config)

    task = TaskDefinition(
        task_id="task2", task_class=TaskClass.BULK, function=sample_task_function, args=(5, 10), tenant_id="tenant1"
    )

    job_id = router.enqueue(task)

    assert job_id == "task2"


def test_router_routes_to_correct_backend():
    """Router routes tasks to correct backend."""
    config = QueueConfig(
        realtime_backend=QueueBackend.REDIS,  # Will fallback to local if not available
        bulk_backend=QueueBackend.SQS,  # Will fallback to local if not available
    )
    router = HybridQueueRouter(config=config)

    assert router.get_backend_for_class(TaskClass.REALTIME) == QueueBackend.REDIS
    assert router.get_backend_for_class(TaskClass.BULK) == QueueBackend.SQS


def test_task_definition_with_kwargs():
    """Task definition supports kwargs."""
    task = TaskDefinition(
        task_id="task3",
        task_class=TaskClass.REALTIME,
        function=sample_task_function,
        args=(1,),
        kwargs={"y": 2},
        tenant_id="tenant1",
    )

    assert task.args == (1,)
    assert task.kwargs == {"y": 2}


def test_global_router_singleton():
    """Global router is singleton."""
    router1 = get_queue_router()
    router2 = get_queue_router()

    assert router1 is router2


@pytest.mark.api_mismatch  # Sprint 52: enqueue_task API changed, unexpected kwargs
def test_enqueue_task_convenience():
    """Convenience function for enqueueing works."""
    job_id = enqueue_task(
        task_id="task4",
        task_class=TaskClass.REALTIME,
        function=sample_task_function,
        tenant_id="tenant1",
        args=(3, 4),
    )

    assert job_id == "task4"


def test_local_backend_executes_immediately():
    """Local backend executes task immediately."""
    config = QueueConfig(realtime_backend=QueueBackend.LOCAL, bulk_backend=QueueBackend.LOCAL)
    router = HybridQueueRouter(config=config)

    results = []

    def collect_result(value):
        results.append(value)
        return value

    task = TaskDefinition(
        task_id="task5", task_class=TaskClass.REALTIME, function=collect_result, args=(42,), tenant_id="tenant1"
    )

    router.enqueue(task)

    # Task executed immediately
    assert 42 in results


def test_fallback_to_local_when_redis_unavailable():
    """Router falls back to local if Redis unavailable."""
    config = QueueConfig(
        realtime_backend=QueueBackend.REDIS, bulk_backend=QueueBackend.LOCAL, redis_url="redis://invalid:9999"
    )
    router = HybridQueueRouter(config=config)

    task = TaskDefinition(
        task_id="task6", task_class=TaskClass.REALTIME, function=sample_task_function, args=(1, 1), tenant_id="tenant1"
    )

    # Should fallback to local execution (no exception)
    job_id = router.enqueue(task)
    assert job_id == "task6"
