"""Memory subsystem alert rules and escalation (R1 Phase 1)

Alert levels:
- CRITICAL: Requires immediate page (on-call within 5 min)
- HIGH: Significant degradation, create ticket
- MEDIUM: Monitoring needed, watch trends
- LOW: Informational, log for review

Alert routing:
- CRITICAL: PagerDuty immediate + Slack critical channel
- HIGH: Slack ops channel + create Jira ticket
- MEDIUM: Log to metrics system + daily digest
- LOW: Archive for trend analysis
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels"""

    CRITICAL = "critical"  # Page immediately
    HIGH = "high"  # Ticket + notification
    MEDIUM = "medium"  # Log for review
    LOW = "low"  # Archive


class AlertName(Enum):
    """Alert identifiers"""

    # Security
    LEAK_ATTEMPT = "memory_leak_attempt"
    RLS_VIOLATION = "memory_rls_violation"
    INVALID_HASH = "memory_invalid_hash"

    # Performance
    QUERY_LATENCY = "memory_query_latency_exceeded"
    RERANK_SKIPS = "memory_rerank_skips_high"
    TTFV_REGRESSION = "memory_ttfv_regression"

    # Resource
    CHUNK_CARDINALITY = "memory_chunk_cardinality_high"
    INDEX_SIZE = "memory_index_size_high"
    POOL_UTILIZATION = "database_pool_utilization_high"

    # Operational
    INDEX_ERROR_RATE = "memory_index_error_rate"
    QUERY_ERROR_RATE = "memory_query_error_rate"


@dataclass
class AlertRule:
    """Definition of an alert rule"""

    name: AlertName
    severity: AlertSeverity
    condition: str  # Human-readable condition
    threshold: float
    window_minutes: int = 5  # Time window for aggregation
    grace_period_sec: int = 0  # Grace period after deployment
    suppress_during_deploy: bool = False
    runbook_url: str = ""

    def matches(self, current_value: float) -> bool:
        """Check if current value exceeds threshold"""
        return current_value > self.threshold


@dataclass
class AlertContext:
    """Context for alert evaluation"""

    metric_name: str
    current_value: float
    threshold: float
    labels: dict[str, str] = None
    previous_value: Optional[float] = None
    trend: str = "stable"  # "increasing", "decreasing", "stable"
    affected_users: Optional[list[str]] = None


@dataclass
class Alert:
    """An active alert"""

    name: AlertName
    severity: AlertSeverity
    message: str
    context: AlertContext
    triggered_at: float = 0  # Unix timestamp
    resolved_at: Optional[float] = None
    fired_count: int = 1
    last_notification_at: Optional[float] = 0

    def is_active(self) -> bool:
        """Check if alert is currently active"""
        return self.resolved_at is None


class AlertRuleBook:
    """Collection of alert rules with evaluation logic"""

    # Alert definitions (tuned thresholds)
    RULES = {
        AlertName.LEAK_ATTEMPT: AlertRule(
            name=AlertName.LEAK_ATTEMPT,
            severity=AlertSeverity.CRITICAL,
            condition="cross_tenant_access_attempts > 0 in 5m window",
            threshold=0.0,  # ANY leak attempt
            window_minutes=5,
            runbook_url="https://docs.example.com/runbooks/memory-leak",
            suppress_during_deploy=False,
        ),
        AlertName.RLS_VIOLATION: AlertRule(
            name=AlertName.RLS_VIOLATION,
            severity=AlertSeverity.CRITICAL,
            condition="rls_blocks > threshold (possible attack)",
            threshold=10.0,  # Per 5-minute window
            window_minutes=5,
            runbook_url="https://docs.example.com/runbooks/rls-violation",
        ),
        AlertName.QUERY_LATENCY: AlertRule(
            name=AlertName.QUERY_LATENCY,
            severity=AlertSeverity.HIGH,
            condition="query_p95 > 400ms (rerank budget exceeded)",
            threshold=400.0,
            window_minutes=10,
            grace_period_sec=300,  # 5 min grace after deploy
            runbook_url="https://docs.example.com/runbooks/query-latency",
        ),
        AlertName.RERANK_SKIPS: AlertRule(
            name=AlertName.RERANK_SKIPS,
            severity=AlertSeverity.HIGH,
            condition="rerank_skips > 10/min (GPU degradation)",
            threshold=10.0,
            window_minutes=1,
            runbook_url="https://docs.example.com/runbooks/gpu-degradation",
        ),
        AlertName.TTFV_REGRESSION: AlertRule(
            name=AlertName.TTFV_REGRESSION,
            severity=AlertSeverity.MEDIUM,
            condition="ttfv_p95 > 1.5s (regression from R0.5)",
            threshold=1500.0,
            window_minutes=15,
            runbook_url="https://docs.example.com/runbooks/ttfv",
        ),
        AlertName.CHUNK_CARDINALITY: AlertRule(
            name=AlertName.CHUNK_CARDINALITY,
            severity=AlertSeverity.MEDIUM,
            condition="unique_user_chunk_counts > 10k (monitor)",
            threshold=10000.0,
            window_minutes=60,
        ),
        AlertName.INDEX_ERROR_RATE: AlertRule(
            name=AlertName.INDEX_ERROR_RATE,
            severity=AlertSeverity.HIGH,
            condition="index_errors / index_total > 5%",
            threshold=0.05,
            window_minutes=5,
            runbook_url="https://docs.example.com/runbooks/index-errors",
        ),
        AlertName.QUERY_ERROR_RATE: AlertRule(
            name=AlertName.QUERY_ERROR_RATE,
            severity=AlertSeverity.HIGH,
            condition="query_errors / query_total > 5%",
            threshold=0.05,
            window_minutes=5,
            runbook_url="https://docs.example.com/runbooks/query-errors",
        ),
    }

    def get_rule(self, name: AlertName) -> Optional[AlertRule]:
        """Get alert rule by name"""
        return self.RULES.get(name)

    def evaluate_all(self, metrics: dict[str, Any]) -> list[Alert]:
        """Evaluate all rules against current metrics

        Args:
            metrics: Dict of metric_name -> current_value

        Returns:
            List of triggered alerts
        """
        alerts = []

        # TODO: Implement rule evaluation logic
        # This would check each rule against current metrics

        return alerts


class AlertManager:
    """Manages alert state and notifications"""

    def __init__(self, on_alert: Optional[Callable[[Alert], None]] = None):
        """Initialize alert manager

        Args:
            on_alert: Callback when alert fires
        """
        self.rulebook = AlertRuleBook()
        self._active_alerts: dict[AlertName, Alert] = {}
        self._alert_history: list[Alert] = []
        self._on_alert = on_alert

    def evaluate(self, metrics: dict[str, Any]) -> list[Alert]:
        """Evaluate all rules and update alert state

        Args:
            metrics: Dict of current metrics

        Returns:
            List of newly triggered alerts
        """
        new_alerts = self.rulebook.evaluate_all(metrics)

        new_triggered = []
        for alert in new_alerts:
            if alert.name not in self._active_alerts:
                # New alert
                self._active_alerts[alert.name] = alert
                new_triggered.append(alert)
                logger.warning(f"Alert triggered: {alert.name.value} - {alert.message}")

                if self._on_alert:
                    self._on_alert(alert)
            else:
                # Existing alert, increment counter
                existing = self._active_alerts[alert.name]
                existing.fired_count += 1

        # Check for resolved alerts
        for name in list(self._active_alerts.keys()):
            if not any(a.name == name for a in new_alerts):
                # Alert no longer firing
                alert = self._active_alerts.pop(name)
                alert.resolved_at = 0  # TODO: Set to current timestamp
                logger.info(f"Alert resolved: {alert.name.value}")
                self._alert_history.append(alert)

        return new_triggered

    def get_active_alerts(self) -> list[Alert]:
        """Get currently active alerts"""
        return list(self._active_alerts.values())

    def get_alert_summary(self) -> dict[str, Any]:
        """Get summary of alert state

        Returns:
            {
                "total_active": 5,
                "critical": 1,
                "high": 2,
                "medium": 2,
                "alerts": [...]
            }
        """
        active = self.get_active_alerts()

        severity_counts = {}
        for alert in active:
            severity = alert.severity.value
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        return {
            "total_active": len(active),
            "critical": severity_counts.get("critical", 0),
            "high": severity_counts.get("high", 0),
            "medium": severity_counts.get("medium", 0),
            "low": severity_counts.get("low", 0),
            "alerts": [
                {
                    "name": a.name.value,
                    "severity": a.severity.value,
                    "message": a.message,
                    "fired_count": a.fired_count,
                }
                for a in active
            ],
        }


def format_alert_for_notification(alert: Alert) -> str:
    """Format alert for Slack/email notification

    Args:
        alert: Alert to format

    Returns:
        Formatted message string
    """
    severity_emoji = {
        AlertSeverity.CRITICAL: "CRITICAL",
        AlertSeverity.HIGH: "WARNING",
        AlertSeverity.MEDIUM: "INFO",
        AlertSeverity.LOW: "DEBUG",
    }.get(alert.severity, "?")

    lines = [
        f"[{severity_emoji}] {alert.name.value}",
        f"Message: {alert.message}",
        f"Value: {alert.context.current_value:.2f}",
        f"Threshold: {alert.context.threshold:.2f}",
    ]

    if alert.context.trend and alert.context.trend != "stable":
        lines.append(f"Trend: {alert.context.trend}")

    if alert.context.affected_users:
        lines.append(f"Affected: {len(alert.context.affected_users)} users")

    if alert.rulebook.get_rule(alert.name):
        rule = alert.rulebook.get_rule(alert.name)
        if rule and rule.runbook_url:
            lines.append(f"Runbook: {rule.runbook_url}")

    return "\n".join(lines)


# SLO-based alerting
@dataclass
class SLOAlert:
    """Alert based on SLO breach"""

    name: str
    sli_name: str  # Service Level Indicator
    slo_target: float  # e.g., 0.999 for 99.9%
    current_sli: float  # e.g., 0.998
    error_budget_remaining: float  # % of error budget remaining
    is_breached: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sli_name": self.sli_name,
            "slo_target": f"{self.slo_target:.3%}",
            "current_sli": f"{self.current_sli:.3%}",
            "error_budget_remaining": f"{self.error_budget_remaining:.1%}",
            "is_breached": self.is_breached,
        }


class SLOMonitor:
    """Monitor SLO compliance and error budgets"""

    def __init__(self):
        """Initialize SLO monitor with Memory R1 SLOs"""
        self.slos = {
            "availability": {
                "target": 0.999,  # 99.9% uptime
                "error_budget_minutes_per_month": 43.2,  # 0.1% of 43200 minutes
            },
            "query_latency": {
                "target": 0.95,  # 95% of queries < 400ms
                "p95_budget_ms": 400.0,
            },
            "index_reliability": {
                "target": 0.999,  # 99.9% of indexes succeed
                "error_budget": 0.001,
            },
        }

    def evaluate_slo(self, slo_name: str, current_value: float) -> SLOAlert:
        """Evaluate if SLO is being met

        Args:
            slo_name: SLO to check
            current_value: Current SLI value

        Returns:
            SLOAlert with breach status
        """
        slo = self.slos.get(slo_name, {})
        target = slo.get("target", 0.0)

        is_breached = current_value < target

        # Calculate error budget remaining
        if target > 0:
            error_budget_used = 1.0 - (current_value / target)
            error_budget_remaining = max(0, 1.0 - error_budget_used)
        else:
            error_budget_remaining = 0.0

        return SLOAlert(
            name=slo_name,
            sli_name=slo_name,
            slo_target=target,
            current_sli=current_value,
            error_budget_remaining=error_budget_remaining,
            is_breached=is_breached,
        )

    def get_all_slo_status(self, metrics: dict[str, float]) -> list[SLOAlert]:
        """Get status of all SLOs

        Returns:
            List of SLOAlert for each SLO
        """
        alerts = []

        for slo_name in self.slos.keys():
            if slo_name in metrics:
                alerts.append(self.evaluate_slo(slo_name, metrics[slo_name]))

        return alerts
