"""Tests for worker pool management."""

import threading
import time

from relay_ai.scale.worker_pool import Job, WorkerPool


def test_initial_worker_spawn():
    """Worker pool spawns initial workers on creation."""
    pool = WorkerPool(initial_workers=3)

    # Wait briefly for workers to start
    # TODO(Sprint 45): replace with wait_until(...) for faster polling
    time.sleep(0.1)

    stats = pool.get_stats()
    assert stats.total_workers == 3

    pool.shutdown(timeout_s=2)


def test_job_submission_and_execution():
    """Worker pool submits and executes jobs."""
    pool = WorkerPool(initial_workers=2)
    results = []

    def capture_result(value):
        results.append(value)

    job = Job(
        job_id="test-job-1",
        task=capture_result,
        args=(42,),
        kwargs={},
    )

    pool.submit_job(job)

    # Wait for job to complete
    # TODO(Sprint 45): replace with wait_until(...) for faster polling
    time.sleep(0.5)

    assert 42 in results
    stats = pool.get_stats()
    assert stats.jobs_completed >= 1

    pool.shutdown(timeout_s=2)


def test_job_execution_with_kwargs():
    """Worker pool executes jobs with kwargs."""
    pool = WorkerPool(initial_workers=1)
    results = []

    def capture_kwargs(**kwargs):
        results.append(kwargs)

    job = Job(
        job_id="test-job-kwargs",
        task=capture_kwargs,
        args=(),
        kwargs={"key1": "value1", "key2": "value2"},
    )

    pool.submit_job(job)
    # TODO(Sprint 45): replace with wait_until(...) for faster polling
    time.sleep(0.5)

    assert len(results) == 1
    assert results[0] == {"key1": "value1", "key2": "value2"}

    pool.shutdown(timeout_s=2)


def test_scale_up_add_workers():
    """Worker pool scales up by adding workers."""
    pool = WorkerPool(initial_workers=2)
    # TODO(Sprint 45): replace with wait_until(...) for faster polling
    time.sleep(0.1)

    initial_stats = pool.get_stats()
    assert initial_stats.total_workers == 2

    # Scale up to 5 workers
    success = pool.scale_to(5)
    # TODO(Sprint 45): replace with wait_until(...) for faster polling
    time.sleep(0.1)

    assert success is True
    stats = pool.get_stats()
    assert stats.total_workers == 5

    pool.shutdown(timeout_s=2)


def test_scale_down_with_graceful_drain(monkeypatch):
    """Worker pool scales down with graceful drain."""
    monkeypatch.setenv("WORKER_SHUTDOWN_TIMEOUT_S", "5")

    pool = WorkerPool(initial_workers=6)
    # TODO(Sprint 45): replace with wait_until(...) for faster polling
    time.sleep(0.1)

    initial_stats = pool.get_stats()
    assert initial_stats.total_workers == 6

    # Scale down to 3 workers
    success = pool.scale_to(3)

    assert success is True
    stats = pool.get_stats()
    assert stats.total_workers == 3

    pool.shutdown(timeout_s=2)


def test_scale_to_same_count_is_noop():
    """Worker pool scaling to current count is no-op."""
    pool = WorkerPool(initial_workers=4)
    # TODO(Sprint 45): replace with wait_until(...) for faster polling
    time.sleep(0.1)

    # Scale to same count
    success = pool.scale_to(4)

    assert success is True
    stats = pool.get_stats()
    assert stats.total_workers == 4

    pool.shutdown(timeout_s=2)


def test_statistics_tracking():
    """Worker pool tracks job completion statistics."""
    pool = WorkerPool(initial_workers=2)

    def successful_job():
        pass

    def failing_job():
        raise ValueError("Test error")

    # Submit successful jobs
    for i in range(3):
        job = Job(
            job_id=f"success-{i}",
            task=successful_job,
            args=(),
            kwargs={},
        )
        pool.submit_job(job)

    # Submit failing jobs
    for i in range(2):
        job = Job(
            job_id=f"fail-{i}",
            task=failing_job,
            args=(),
            kwargs={},
        )
        pool.submit_job(job)

    # Wait for jobs to complete
    # TODO(Sprint 45): replace with wait_until(...) for faster polling
    time.sleep(1.0)

    stats = pool.get_stats()
    assert stats.jobs_completed >= 3
    assert stats.jobs_failed >= 2

    pool.shutdown(timeout_s=2)


def test_active_jobs_tracking():
    """Worker pool tracks active jobs."""
    pool = WorkerPool(initial_workers=2)
    event = threading.Event()

    def blocking_job():
        event.wait()  # Block until signaled

    # Submit blocking jobs
    for i in range(2):
        job = Job(
            job_id=f"blocking-{i}",
            task=blocking_job,
            args=(),
            kwargs={},
        )
        pool.submit_job(job)

    # Wait for jobs to start
    # TODO(Sprint 45): replace with wait_until(...) for faster polling
    time.sleep(0.3)

    stats = pool.get_stats()
    assert stats.active_workers == 2
    assert stats.idle_workers == 0

    # Release jobs
    event.set()
    # TODO(Sprint 45): replace with wait_until(...) for faster polling
    time.sleep(0.3)

    stats = pool.get_stats()
    assert stats.active_workers == 0
    assert stats.idle_workers == 2

    pool.shutdown(timeout_s=2)


def test_queue_depth_tracking():
    """Worker pool tracks queue depth."""
    pool = WorkerPool(initial_workers=1)
    event = threading.Event()

    def blocking_job():
        event.wait()

    # Submit more jobs than workers
    for i in range(5):
        job = Job(
            job_id=f"queued-{i}",
            task=blocking_job,
            args=(),
            kwargs={},
        )
        pool.submit_job(job)

    # Wait for first job to start, others queued
    # TODO(Sprint 45): replace with wait_until(...) for faster polling
    time.sleep(0.3)

    stats = pool.get_stats()
    assert stats.queue_depth >= 4  # 5 jobs - 1 active

    # Release jobs
    event.set()
    # TODO(Sprint 45): replace with wait_until(...) for faster polling
    time.sleep(0.5)

    stats = pool.get_stats()
    assert stats.queue_depth == 0

    pool.shutdown(timeout_s=2)


def test_shutdown_with_graceful_drain(monkeypatch):
    """Worker pool shutdown drains pending jobs gracefully."""
    monkeypatch.setenv("WORKER_SHUTDOWN_TIMEOUT_S", "5")

    pool = WorkerPool(initial_workers=2)
    completed = []

    def quick_job(job_id):
        completed.append(job_id)
        # TODO(Sprint 45): replace with wait_until(...) for faster polling
        time.sleep(0.1)

    # Submit several jobs
    for i in range(5):
        job = Job(
            job_id=f"drain-{i}",
            task=quick_job,
            args=(f"drain-{i}",),
            kwargs={},
        )
        pool.submit_job(job)

    # Shutdown and wait for drain
    pool.shutdown(timeout_s=5)

    # All jobs should complete
    assert len(completed) == 5


def test_shutdown_timeout(monkeypatch):
    """Worker pool shutdown respects timeout."""
    monkeypatch.setenv("WORKER_SHUTDOWN_TIMEOUT_S", "1")

    pool = WorkerPool(initial_workers=2)
    event = threading.Event()

    def blocking_job():
        event.wait(timeout=10)  # Block for long time

    # Submit blocking jobs
    for i in range(2):
        job = Job(
            job_id=f"block-{i}",
            task=blocking_job,
            args=(),
            kwargs={},
        )
        pool.submit_job(job)

    # TODO(Sprint 45): replace with wait_until(...) for faster polling
    time.sleep(0.2)

    # Shutdown with short timeout
    start = time.time()
    pool.shutdown(timeout_s=1)
    elapsed = time.time() - start

    # Should timeout quickly (within 2 seconds)
    assert elapsed < 2

    event.set()  # Clean up


def test_region_awareness():
    """Worker pool is region-aware."""
    pool = WorkerPool(initial_workers=2, region="us-west")

    assert pool.region == "us-west"

    pool.shutdown(timeout_s=2)


def test_region_defaults_to_env(monkeypatch):
    """Worker pool region defaults to CURRENT_REGION env var."""
    monkeypatch.setenv("CURRENT_REGION", "eu-central")

    pool = WorkerPool(initial_workers=1)

    assert pool.region == "eu-central"

    pool.shutdown(timeout_s=2)


def test_region_defaults_to_default_region(monkeypatch):
    """Worker pool region defaults to 'default' if not specified."""
    monkeypatch.delenv("CURRENT_REGION", raising=False)

    pool = WorkerPool(initial_workers=1)

    assert pool.region == "default"

    pool.shutdown(timeout_s=2)


def test_concurrent_job_execution():
    """Worker pool executes jobs concurrently."""
    pool = WorkerPool(initial_workers=3)
    start_times = {}
    lock = threading.Lock()

    def timed_job(job_id):
        with lock:
            start_times[job_id] = time.time()
        # TODO(Sprint 45): replace with wait_until(...) for faster polling
        time.sleep(0.3)

    # Submit 3 jobs
    for i in range(3):
        job = Job(
            job_id=f"concurrent-{i}",
            task=timed_job,
            args=(f"concurrent-{i}",),
            kwargs={},
        )
        pool.submit_job(job)

    # Wait for all jobs to complete
    # TODO(Sprint 45): replace with wait_until(...) for faster polling
    time.sleep(1.0)

    # All 3 jobs should start within a short window (concurrent execution)
    times = list(start_times.values())
    assert len(times) == 3
    time_spread = max(times) - min(times)
    assert time_spread < 0.5  # Started within 500ms of each other

    pool.shutdown(timeout_s=2)


def test_job_failure_does_not_crash_worker():
    """Worker continues processing after job failure."""
    pool = WorkerPool(initial_workers=1)
    results = []

    def failing_job():
        raise ValueError("Intentional failure")

    def success_job(value):
        results.append(value)

    # Submit failing job
    pool.submit_job(Job(job_id="fail", task=failing_job, args=(), kwargs={}))
    # TODO(Sprint 45): replace with wait_until(...) for faster polling
    time.sleep(0.2)

    # Submit successful job
    pool.submit_job(Job(job_id="success", task=success_job, args=(42,), kwargs={}))
    # TODO(Sprint 45): replace with wait_until(...) for faster polling
    time.sleep(0.2)

    # Worker should still process successful job after failure
    assert 42 in results
    stats = pool.get_stats()
    assert stats.jobs_failed >= 1
    assert stats.jobs_completed >= 1

    pool.shutdown(timeout_s=2)


def test_empty_pool_shutdown():
    """Worker pool can shutdown with no active jobs."""
    pool = WorkerPool(initial_workers=2)
    # TODO(Sprint 45): replace with wait_until(...) for faster polling
    time.sleep(0.1)

    # Shutdown immediately
    pool.shutdown(timeout_s=2)

    stats = pool.get_stats()
    assert stats.total_workers == 0
