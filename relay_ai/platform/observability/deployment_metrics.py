"""
Deployment Pipeline Metrics Collector

Exports Prometheus metrics for all deployment stages:
- Build, push, deploy (Railway), deploy (Vercel)
- Health checks, database migrations, smoke tests
- Rollbacks and post-deployment health

Metrics are pushed to Prometheus Pushgateway for CI/CD environments.
"""

import json
import logging
import os
import time
from typing import Any, Optional

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, push_to_gateway

logger = logging.getLogger(__name__)


class DeploymentMetricsCollector:
    """
    Prometheus metrics collector for deployment pipeline.

    Usage:
        collector = DeploymentMetricsCollector()

        # Record stage start
        collector.record_stage_start(
            environment="production",
            deployment_id="run-12345",
            service="api",
            stage="build"
        )

        # Record stage completion
        collector.record_stage_complete(
            environment="production",
            deployment_id="run-12345",
            service="api",
            stage="build",
            status="success",
            duration_seconds=95.4
        )

        # Record deployment complete
        collector.record_deployment_complete(
            environment="production",
            deployment_id="run-12345",
            total_duration_seconds=456.2
        )
    """

    def __init__(self, registry: Optional[CollectorRegistry] = None):
        """Initialize metrics collector with Prometheus registry."""
        self.registry = registry or CollectorRegistry()

        # Environment configuration
        self.pushgateway_url = os.getenv("PUSHGATEWAY_URL", "http://localhost:9091")
        self.job_name = "deployment-pipeline"
        self.instance_name = os.getenv("GITHUB_RUN_ID", "local")

        # ===== COUNTERS =====
        self.deployment_total = Counter(
            "deployment_total",
            "Total deployments by status",
            ["environment", "deployment_id", "service", "stage", "status"],
            registry=self.registry,
        )

        self.deployment_errors_total = Counter(
            "deployment_errors_total",
            "Total deployment errors by type",
            ["environment", "deployment_id", "service", "stage", "error_type"],
            registry=self.registry,
        )

        self.deployment_rollback_total = Counter(
            "deployment_rollback_total",
            "Total rollback events",
            ["environment", "deployment_id", "reason", "status"],
            registry=self.registry,
        )

        self.smoke_test_total = Counter(
            "smoke_test_total",
            "Total smoke tests executed",
            ["environment", "deployment_id", "test_name", "status"],
            registry=self.registry,
        )

        self.migration_total = Counter(
            "migration_total",
            "Total database migrations",
            ["environment", "deployment_id", "migration_name", "status"],
            registry=self.registry,
        )

        # ===== GAUGES =====
        self.deployment_in_progress = Gauge(
            "deployment_in_progress",
            "Whether deployment is currently in progress",
            ["environment", "deployment_id", "branch", "triggered_by"],
            registry=self.registry,
        )

        self.deployment_stage_duration_seconds = Gauge(
            "deployment_stage_duration_seconds",
            "Duration of deployment stage in seconds",
            ["environment", "deployment_id", "service", "stage", "status"],
            registry=self.registry,
        )

        self.api_health_check_latency_ms = Gauge(
            "api_health_check_latency_ms",
            "Health check latency in milliseconds",
            ["environment", "deployment_id", "status"],
            registry=self.registry,
        )

        self.post_deployment_error_rate = Gauge(
            "post_deployment_error_rate",
            "Error rate in 5-minute window after deployment",
            ["environment", "deployment_id", "service"],
            registry=self.registry,
        )

        self.database_migration_lag_seconds = Gauge(
            "database_migration_lag_seconds",
            "Total migration duration in seconds",
            ["environment", "deployment_id", "migration_count"],
            registry=self.registry,
        )

        self.deployment_infrastructure_cost = Gauge(
            "deployment_infrastructure_cost",
            "Infrastructure cost for deployment",
            ["environment", "deployment_id", "resource"],
            registry=self.registry,
        )

        # ===== HISTOGRAMS =====
        self.time_to_deploy_seconds = Histogram(
            "time_to_deploy_seconds",
            "Total time from deployment start to production stabilization",
            ["environment"],
            buckets=(60, 300, 600, 900, 1200, 1500, 1800),
            registry=self.registry,
        )

        # Internal tracking
        self._stage_start_times: dict[str, float] = {}

    # ===== RECORDING METHODS =====

    def record_stage_start(self, environment: str, deployment_id: str, service: str, stage: str) -> None:
        """Record stage start time."""
        key = f"{deployment_id}:{service}:{stage}"
        self._stage_start_times[key] = time.time()
        logger.info(f"Stage started: {stage} for {service}")

    def record_stage_complete(
        self,
        environment: str,
        deployment_id: str,
        service: str,
        stage: str,
        status: str = "success",
        duration_seconds: Optional[float] = None,
        error_type: Optional[str] = None,
    ) -> None:
        """
        Record stage completion.

        Args:
            environment: Deployment environment (production/staging)
            deployment_id: GitHub run ID or deployment ID
            service: Service name (api/web/database)
            stage: Stage name (build/deploy/health_check/migration/smoke_test)
            status: 'success' or 'failure'
            duration_seconds: Optional explicit duration (auto-calculated if not provided)
            error_type: Error type if status='failure'
        """
        # Calculate duration if not provided
        if duration_seconds is None:
            key = f"{deployment_id}:{service}:{stage}"
            if key in self._stage_start_times:
                duration_seconds = time.time() - self._stage_start_times.pop(key)
            else:
                logger.warning(f"No start time recorded for {key}")
                duration_seconds = 0

        # Record duration gauge
        self.deployment_stage_duration_seconds.labels(
            environment=environment, deployment_id=deployment_id, service=service, stage=stage, status=status
        ).set(duration_seconds)

        # Record counter
        self.deployment_total.labels(
            environment=environment, deployment_id=deployment_id, service=service, stage=stage, status=status
        ).inc()

        # Record error if present
        if error_type:
            self.deployment_errors_total.labels(
                environment=environment,
                deployment_id=deployment_id,
                service=service,
                stage=stage,
                error_type=error_type,
            ).inc()

        logger.info(f"Stage complete: {stage} ({status}) - " f"duration: {duration_seconds:.2f}s")

        # Push to gateway
        self._push_metrics()

    def record_health_check(
        self,
        environment: str,
        deployment_id: str,
        latency_ms: float,
        status: str,  # 'healthy' or 'unhealthy'
        endpoint: str = "/health",
    ) -> None:
        """Record health check result."""
        self.api_health_check_latency_ms.labels(
            environment=environment, deployment_id=deployment_id, status=status
        ).set(latency_ms)

        logger.info(f"Health check: {status} - " f"latency: {latency_ms}ms - " f"endpoint: {endpoint}")
        self._push_metrics()

    def record_migration_complete(
        self,
        environment: str,
        deployment_id: str,
        migration_name: str,
        duration_seconds: float,
        success: bool,
        migration_count: Optional[int] = None,
    ) -> None:
        """Record database migration completion."""
        self.migration_total.labels(
            environment=environment,
            deployment_id=deployment_id,
            migration_name=migration_name,
            status="success" if success else "failure",
        ).inc()

        if migration_count is not None:
            self.database_migration_lag_seconds.labels(
                environment=environment, deployment_id=deployment_id, migration_count=str(migration_count)
            ).set(duration_seconds)

        logger.info(
            f"Migration: {migration_name} ({'success' if success else 'failure'}) - "
            f"duration: {duration_seconds:.2f}s"
        )
        self._push_metrics()

    def record_smoke_test(
        self,
        environment: str,
        deployment_id: str,
        test_name: str,
        success: bool,
        duration_seconds: Optional[float] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Record smoke test result."""
        self.smoke_test_total.labels(
            environment=environment,
            deployment_id=deployment_id,
            test_name=test_name,
            status="success" if success else "failure",
        ).inc()

        status = "passed" if success else "failed"
        logger.info(f"Smoke test: {test_name} - {status}")
        if error_message:
            logger.error(f"  Error: {error_message}")

        self._push_metrics()

    def record_deployment_start(
        self, environment: str, deployment_id: str, branch: str, triggered_by: str = "github_actions"
    ) -> None:
        """Record deployment start."""
        self.deployment_in_progress.labels(
            environment=environment, deployment_id=deployment_id, branch=branch, triggered_by=triggered_by
        ).set(1)

        logger.info(f"Deployment started: {deployment_id} on {branch}")
        self._push_metrics()

    def record_deployment_complete(
        self, environment: str, deployment_id: str, total_duration_seconds: float, success: bool = True
    ) -> None:
        """
        Record total deployment duration and mark deployment complete.

        Args:
            environment: Deployment environment
            deployment_id: GitHub run ID
            total_duration_seconds: Total time from start to end
            success: Whether deployment succeeded
        """
        # Record total duration histogram
        self.time_to_deploy_seconds.labels(environment=environment).observe(total_duration_seconds)

        # Mark deployment as complete
        self.deployment_in_progress.labels(
            environment=environment,
            deployment_id=deployment_id,
            branch=os.getenv("GITHUB_REF_NAME", "unknown"),
            triggered_by="github_actions",
        ).set(0)

        logger.info(
            f"Deployment complete: {deployment_id} - "
            f"duration: {total_duration_seconds:.2f}s - "
            f"status: {'success' if success else 'failure'}"
        )
        self._push_metrics()

    def record_rollback(
        self,
        environment: str,
        deployment_id: str,
        previous_deployment_id: str,
        reason: str,  # 'health_check_failed', 'test_failed', 'manual', etc.
        success: bool = True,
        duration_seconds: Optional[float] = None,
    ) -> None:
        """Record rollback event."""
        self.deployment_rollback_total.labels(
            environment=environment,
            deployment_id=deployment_id,
            reason=reason,
            status="success" if success else "failure",
        ).inc()

        logger.warning(
            f"Rollback triggered: {deployment_id} -> {previous_deployment_id} - "
            f"reason: {reason} - "
            f"status: {'success' if success else 'failure'}"
        )
        self._push_metrics()

    def record_post_deployment_error_rate(
        self, environment: str, deployment_id: str, service: str, error_rate: float  # 0.0 to 1.0
    ) -> None:
        """Record error rate in post-deployment window."""
        self.post_deployment_error_rate.labels(
            environment=environment, deployment_id=deployment_id, service=service
        ).set(error_rate)

        logger.info(f"Post-deployment error rate: {error_rate:.2%}")
        self._push_metrics()

    def record_infrastructure_cost(
        self,
        environment: str,
        deployment_id: str,
        resource: str,  # 'railway_compute', 'vercel_build', 'database_migration'
        cost_usd: float,
    ) -> None:
        """Record infrastructure cost for deployment."""
        self.deployment_infrastructure_cost.labels(
            environment=environment, deployment_id=deployment_id, resource=resource
        ).set(cost_usd)

        logger.info(f"Infrastructure cost: {resource} = ${cost_usd:.2f}")
        self._push_metrics()

    # ===== INTERNAL METHODS =====

    def _push_metrics(self) -> None:
        """Push metrics to Prometheus Pushgateway."""
        try:
            if self.pushgateway_url and self.pushgateway_url != "disabled":
                push_to_gateway(
                    self.pushgateway_url,
                    job=self.job_name,
                    instance=self.instance_name,
                    registry=self.registry,
                    timeout=10,
                )
        except Exception as e:
            logger.error(f"Failed to push metrics: {e}")

    def get_metrics_dict(self) -> dict[str, Any]:
        """Export all current metrics as dictionary for debugging."""
        metrics = {}
        for metric_family in self.registry.collect():
            for metric in metric_family.samples:
                key = f"{metric.name}{dict(metric.labels)}"
                metrics[key] = metric.value
        return metrics

    def export_metrics_json(self) -> str:
        """Export all current metrics as JSON string."""
        return json.dumps(self.get_metrics_dict(), indent=2, default=str)


# Global instance
_collector: Optional[DeploymentMetricsCollector] = None


def get_deployment_metrics() -> DeploymentMetricsCollector:
    """Get or create global deployment metrics collector."""
    global _collector
    if _collector is None:
        _collector = DeploymentMetricsCollector()
    return _collector


# Convenience functions for direct usage
def record_stage_complete(
    environment: str,
    deployment_id: str,
    service: str,
    stage: str,
    status: str = "success",
    duration_seconds: Optional[float] = None,
    error_type: Optional[str] = None,
) -> None:
    """Convenience function to record stage completion."""
    get_deployment_metrics().record_stage_complete(
        environment=environment,
        deployment_id=deployment_id,
        service=service,
        stage=stage,
        status=status,
        duration_seconds=duration_seconds,
        error_type=error_type,
    )


def record_health_check(
    environment: str, deployment_id: str, latency_ms: float, status: str, endpoint: str = "/health"
) -> None:
    """Convenience function to record health check."""
    get_deployment_metrics().record_health_check(
        environment=environment, deployment_id=deployment_id, latency_ms=latency_ms, status=status, endpoint=endpoint
    )


def record_deployment_complete(
    environment: str, deployment_id: str, total_duration_seconds: float, success: bool = True
) -> None:
    """Convenience function to record deployment completion."""
    get_deployment_metrics().record_deployment_complete(
        environment=environment,
        deployment_id=deployment_id,
        total_duration_seconds=total_duration_seconds,
        success=success,
    )
