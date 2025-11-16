"""Hybrid queue router for realtime and bulk task routing."""

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional


class TaskClass(str, Enum):
    """Task classification for routing."""

    REALTIME = "realtime"  # Low latency: chat, interactive approvals, previews
    BULK = "bulk"  # High throughput: batch ingest, indexing, long DJP runs


class QueueBackend(str, Enum):
    """Available queue backends."""

    LOCAL = "local"  # In-process (dev/testing)
    REDIS = "redis"  # Redis Queue (RQ) for realtime
    SQS = "sqs"  # AWS SQS for bulk
    PUBSUB = "pubsub"  # GCP Pub/Sub for bulk


@dataclass
class TaskDefinition:
    """Task to be queued."""

    task_id: str
    task_class: TaskClass
    function: Callable
    args: tuple = ()
    kwargs: dict[str, Any] = None
    tenant_id: str = "default"
    priority: int = 0  # Higher = more urgent

    def __post_init__(self):
        if self.kwargs is None:
            self.kwargs = {}


@dataclass
class QueueConfig:
    """Queue configuration."""

    realtime_backend: QueueBackend
    bulk_backend: QueueBackend
    redis_url: Optional[str] = None
    sqs_queue_url: Optional[str] = None
    pubsub_topic: Optional[str] = None
    max_retries: int = 3
    rate_limit_per_minute: Optional[int] = None


class HybridQueueRouter:
    """Routes tasks to appropriate queue backends."""

    def __init__(self, config: Optional[QueueConfig] = None):
        """
        Initialize router with configuration.

        Args:
            config: Queue configuration (defaults from env if None)
        """
        if config is None:
            config = self._load_config_from_env()

        self.config = config

        # Initialize backend connections (lazy)
        self._realtime_queue = None
        self._bulk_queue = None

    def _load_config_from_env(self) -> QueueConfig:
        """Load configuration from environment variables."""
        realtime_backend_str = os.getenv("QUEUE_BACKEND_REALTIME", "local")
        bulk_backend_str = os.getenv("QUEUE_BACKEND_BULK", "local")

        try:
            realtime_backend = QueueBackend(realtime_backend_str)
        except ValueError:
            print(f"Warning: Invalid QUEUE_BACKEND_REALTIME='{realtime_backend_str}', using 'local'")
            realtime_backend = QueueBackend.LOCAL

        try:
            bulk_backend = QueueBackend(bulk_backend_str)
        except ValueError:
            print(f"Warning: Invalid QUEUE_BACKEND_BULK='{bulk_backend_str}', using 'local'")
            bulk_backend = QueueBackend.LOCAL

        return QueueConfig(
            realtime_backend=realtime_backend,
            bulk_backend=bulk_backend,
            redis_url=os.getenv("REDIS_URL"),
            sqs_queue_url=os.getenv("SQS_QUEUE_URL"),
            pubsub_topic=os.getenv("PUBSUB_TOPIC"),
            max_retries=int(os.getenv("QUEUE_MAX_RETRIES", "3")),
            rate_limit_per_minute=int(os.getenv("QUEUE_RATE_LIMIT", "0")) or None,
        )

    def enqueue(self, task: TaskDefinition) -> str:
        """
        Enqueue task to appropriate backend.

        Args:
            task: Task definition

        Returns:
            Job ID or task ID
        """
        # Determine target backend
        if task.task_class == TaskClass.REALTIME:
            backend = self.config.realtime_backend
            queue = self._get_realtime_queue()
        else:
            backend = self.config.bulk_backend
            queue = self._get_bulk_queue()

        # Route to backend
        if backend == QueueBackend.LOCAL:
            return self._enqueue_local(task)
        elif backend == QueueBackend.REDIS:
            return self._enqueue_redis(task, queue)
        elif backend == QueueBackend.SQS:
            return self._enqueue_sqs(task, queue)
        elif backend == QueueBackend.PUBSUB:
            return self._enqueue_pubsub(task, queue)
        else:
            raise ValueError(f"Unsupported backend: {backend}")

    def _get_realtime_queue(self):
        """Get or create realtime queue connection."""
        if self._realtime_queue is None and self.config.realtime_backend == QueueBackend.REDIS:
            try:
                from redis import Redis
                from rq import Queue

                redis_conn = Redis.from_url(self.config.redis_url or "redis://localhost:6379")
                self._realtime_queue = Queue("realtime", connection=redis_conn)
            except ImportError:
                print("Warning: rq/redis not installed, falling back to local queue")
                self.config.realtime_backend = QueueBackend.LOCAL

        return self._realtime_queue

    def _get_bulk_queue(self):
        """Get or create bulk queue connection."""
        if self._bulk_queue is None:
            if self.config.bulk_backend == QueueBackend.SQS:
                try:
                    import boto3

                    self._bulk_queue = boto3.client("sqs")
                except ImportError:
                    print("Warning: boto3 not installed, falling back to local queue")
                    self.config.bulk_backend = QueueBackend.LOCAL

            elif self.config.bulk_backend == QueueBackend.PUBSUB:
                try:
                    from google.cloud import pubsub_v1

                    self._bulk_queue = pubsub_v1.PublisherClient()
                except ImportError:
                    print("Warning: google-cloud-pubsub not installed, falling back to local queue")
                    self.config.bulk_backend = QueueBackend.LOCAL

        return self._bulk_queue

    def _enqueue_local(self, task: TaskDefinition) -> str:
        """Execute task immediately in-process (dev/testing)."""
        print(f"[LOCAL] Executing task {task.task_id} ({task.task_class.value}) immediately")

        try:
            result = task.function(*task.args, **task.kwargs)
            print(f"[LOCAL] Task {task.task_id} completed: {result}")
            return task.task_id
        except Exception as e:
            print(f"[LOCAL] Task {task.task_id} failed: {e}")
            raise

    def _enqueue_redis(self, task: TaskDefinition, queue) -> str:
        """Enqueue to Redis Queue (RQ)."""
        if queue is None:
            # Fallback to local
            return self._enqueue_local(task)

        job = queue.enqueue(
            task.function,
            *task.args,
            **task.kwargs,
            job_id=task.task_id,
            job_timeout="5m" if task.task_class == TaskClass.REALTIME else "30m",
            retry=self.config.max_retries,
        )

        print(f"[REDIS] Enqueued task {task.task_id} to realtime queue")
        return job.id

    def _enqueue_sqs(self, task: TaskDefinition, queue) -> str:
        """Enqueue to AWS SQS."""
        if queue is None or not self.config.sqs_queue_url:
            # Fallback to local
            return self._enqueue_local(task)

        import json

        # Serialize task (simple JSON payload)
        message_body = json.dumps(
            {
                "task_id": task.task_id,
                "function": f"{task.function.__module__}.{task.function.__name__}",
                "args": task.args,
                "kwargs": task.kwargs,
                "tenant_id": task.tenant_id,
            }
        )

        response = queue.send_message(QueueUrl=self.config.sqs_queue_url, MessageBody=message_body)

        print(f"[SQS] Enqueued task {task.task_id} to bulk queue")
        return response["MessageId"]

    def _enqueue_pubsub(self, task: TaskDefinition, queue) -> str:
        """Enqueue to GCP Pub/Sub."""
        if queue is None or not self.config.pubsub_topic:
            # Fallback to local
            return self._enqueue_local(task)

        import json

        # Serialize task
        message_data = json.dumps(
            {
                "task_id": task.task_id,
                "function": f"{task.function.__module__}.{task.function.__name__}",
                "args": task.args,
                "kwargs": task.kwargs,
                "tenant_id": task.tenant_id,
            }
        ).encode("utf-8")

        future = queue.publish(self.config.pubsub_topic, message_data)
        message_id = future.result()

        print(f"[PUBSUB] Enqueued task {task.task_id} to bulk queue")
        return message_id

    def get_backend_for_class(self, task_class: TaskClass) -> QueueBackend:
        """Get configured backend for task class."""
        if task_class == TaskClass.REALTIME:
            return self.config.realtime_backend
        else:
            return self.config.bulk_backend


# Global router instance
_router: Optional[HybridQueueRouter] = None


def get_queue_router() -> HybridQueueRouter:
    """Get global queue router instance."""
    global _router
    if _router is None:
        _router = HybridQueueRouter()
    return _router


def enqueue_task(
    task_id: str,
    task_class: TaskClass,
    function: Callable,
    *args,
    tenant_id: str = "default",
    **kwargs,
) -> str:
    """Convenience function for enqueueing tasks."""
    router = get_queue_router()
    task = TaskDefinition(
        task_id=task_id, task_class=task_class, function=function, args=args, kwargs=kwargs, tenant_id=tenant_id
    )
    return router.enqueue(task)
