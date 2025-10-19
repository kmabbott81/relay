"""Memory observability dashboard configurations (R1 Phase 1)

Dashboards for different personas:
1. Operations (on-call): Real-time health, incidents, drill-down
2. Developers (debugging): Traces, logs, performance profiles
3. Executives (business): Uptime %, cost trends, user impact
4. Cost Analytics: Model/feature/user attribution

All dashboards support:
- Drill-down from summary to detail
- Time range selection (1h, 6h, 24h, 7d)
- Live refresh (5s, 30s, 1m, off)
- Export (CSV, PNG, API)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class DashboardType(Enum):
    """Dashboard categories"""

    OPERATIONS = "operations"
    DEVELOPMENT = "development"
    BUSINESS = "business"
    COST = "cost"


@dataclass
class DashboardPanel:
    """A single dashboard visualization"""

    title: str
    metric_queries: list[str] = field(default_factory=list)
    visualization_type: str = "graph"  # graph, gauge, stat, table, heatmap
    height: int = 300
    width: int = 6  # Out of 12
    description: str = ""
    alert_threshold: Optional[float] = None
    drilldown_target: Optional[str] = None  # Link to another dashboard

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "metrics": self.metric_queries,
            "type": self.visualization_type,
            "height": self.height,
            "width": self.width,
            "description": self.description,
            "threshold": self.alert_threshold,
            "drilldown": self.drilldown_target,
        }


class DashboardBuilder:
    """Build dashboard configurations"""

    @staticmethod
    def build_operations_dashboard() -> list[DashboardPanel]:
        """Build on-call operations dashboard

        Structure:
        1. Status section (red/yellow/green health)
        2. SLI section (latency, errors, uptime)
        3. Incident section (active alerts)
        4. Resource section (pool, GPU, index)
        """

        panels = [
            # Row 1: Status indicators
            DashboardPanel(
                title="System Status",
                metric_queries=["memory_system_health_status"],
                visualization_type="stat",
                width=3,
                height=100,
                description="Overall health status (healthy/degraded/critical)",
            ),
            DashboardPanel(
                title="Availability SLI",
                metric_queries=["memory_availability_sli"],
                visualization_type="gauge",
                width=3,
                height=100,
                alert_threshold=0.999,
                description="% of successful queries (SLO: 99.9%)",
            ),
            DashboardPanel(
                title="Active Alerts",
                metric_queries=["alerts_active_count"],
                visualization_type="stat",
                width=3,
                height=100,
                description="Number of currently active alerts",
            ),
            DashboardPanel(
                title="Error Budget",
                metric_queries=["memory_error_budget_remaining"],
                visualization_type="gauge",
                width=3,
                height=100,
                alert_threshold=0.2,  # Alert when < 20% remaining
                description="Monthly error budget used (trigger: < 20%)",
            ),
            # Row 2: Latency (drill-down to rerank)
            DashboardPanel(
                title="Query Latency (Last Hour)",
                metric_queries=[
                    'memory_query_latency_ms{quantile="p50"}',
                    'memory_query_latency_ms{quantile="p95"}',
                    'memory_query_latency_ms{quantile="p99"}',
                ],
                visualization_type="graph",
                width=6,
                alert_threshold=400.0,  # p95 > 400ms = alert
                drilldown_target="memory_latency_drilldown",
                description="Query latency p50/p95/p99. RED: p95 > 400ms budget",
            ),
            DashboardPanel(
                title="Error Rate (Last Hour)",
                metric_queries=[
                    "rate(memory_query_errors_total[5m])",
                    "rate(memory_index_errors_total[5m])",
                ],
                visualization_type="graph",
                width=6,
                alert_threshold=0.05,  # 5% error rate
                drilldown_target="memory_errors_drilldown",
                description="Query and index error rates",
            ),
            # Row 3: Rerank performance
            DashboardPanel(
                title="Rerank Latency (Last Hour)",
                metric_queries=[
                    'memory_rerank_ms{quantile="p50"}',
                    'memory_rerank_ms{quantile="p95"}',
                ],
                visualization_type="graph",
                width=4,
                alert_threshold=120.0,
                description="Reranking latency (GPU-bound)",
            ),
            DashboardPanel(
                title="Rerank Circuit Breaker",
                metric_queries=["rate(memory_rerank_skipped_total[1m])"],
                visualization_type="graph",
                width=4,
                alert_threshold=10.0,  # > 10 skips/min
                description="Rerank skips/min (GPU degradation indicator)",
            ),
            DashboardPanel(
                title="Active Rerank Jobs",
                metric_queries=["memory_rerank_jobs_active"],
                visualization_type="gauge",
                width=4,
                alert_threshold=50.0,
                description="Current GPU reranking load",
            ),
            # Row 4: Resource utilization
            DashboardPanel(
                title="Database Pool: Memory Bucket",
                metric_queries=['database_pool_utilization_percent{pool="memory_bucket"}'],
                visualization_type="gauge",
                width=4,
                alert_threshold=80.0,
                description="Connection pool usage (alert if > 80%)",
            ),
            DashboardPanel(
                title="Index Size",
                metric_queries=["memory_index_size_bytes"],
                visualization_type="stat",
                width=4,
                description="Total vector index size (monitoring growth)",
            ),
            DashboardPanel(
                title="Chunk Count by User",
                metric_queries=["memory_chunk_count"],
                visualization_type="heatmap",
                width=4,
                alert_threshold=10000.0,
                description="Unique user chunk counts (cardinality monitor)",
            ),
            # Row 5: Security
            DashboardPanel(
                title="Security Events (Last 24h)",
                metric_queries=[
                    "memory_cross_tenant_access_attempts_total",
                    "memory_rls_blocks_total",
                    "memory_invalid_user_hash_total",
                ],
                visualization_type="table",
                width=12,
                alert_threshold=0.0,  # ANY event = alert
                description="Cross-tenant attempts, RLS blocks, hash errors",
            ),
        ]

        return panels

    @staticmethod
    def build_development_dashboard() -> list[DashboardPanel]:
        """Build developer/debug dashboard

        Structure:
        1. Trace search (find slow requests)
        2. Error logs (recent failures)
        3. Performance profiles (where time is spent)
        4. Service dependency graph
        """

        panels = [
            DashboardPanel(
                title="Trace Search",
                metric_queries=[],
                visualization_type="table",
                width=12,
                height=400,
                description="Find traces by: service, latency, user_id, error",
            ),
            DashboardPanel(
                title="Recent Errors",
                metric_queries=["memory_query_errors_by_type"],
                visualization_type="table",
                width=6,
                description="Top error types from last hour",
            ),
            DashboardPanel(
                title="Slow Queries (p99 > 500ms)",
                metric_queries=['memory_query_latency_ms{quantile="p99"}'],
                visualization_type="table",
                width=6,
                description="Individual slow queries for analysis",
            ),
            DashboardPanel(
                title="Service Dependency Graph",
                metric_queries=[],
                visualization_type="graph",
                width=12,
                height=400,
                description="Which services call memory subsystem",
            ),
        ]

        return panels

    @staticmethod
    def build_business_dashboard() -> list[DashboardPanel]:
        """Build executive/business dashboard

        Structure:
        1. Uptime % vs SLA
        2. Cost trends
        3. User adoption
        4. Feature usage
        """

        panels = [
            DashboardPanel(
                title="Uptime vs SLA",
                metric_queries=["memory_availability_sli", "memory_sla_target"],
                visualization_type="graph",
                width=6,
                description="Uptime percentage (green if above SLA)",
            ),
            DashboardPanel(
                title="Cost Trend (30d)",
                metric_queries=["memory_cost_daily"],
                visualization_type="graph",
                width=6,
                description="Daily cost (embeddings, reranking, storage)",
            ),
            DashboardPanel(
                title="Active Users",
                metric_queries=["memory_active_users_24h"],
                visualization_type="gauge",
                width=4,
                description="Users with memory activity last 24h",
            ),
            DashboardPanel(
                title="Memory Queries/Day",
                metric_queries=["rate(memory_query_total[1d])"],
                visualization_type="stat",
                width=4,
                description="Daily query volume trend",
            ),
            DashboardPanel(
                title="Avg Chunks per User",
                metric_queries=["memory_chunk_count_avg"],
                visualization_type="gauge",
                width=4,
                description="Average memory size per user",
            ),
        ]

        return panels

    @staticmethod
    def build_cost_dashboard() -> list[DashboardPanel]:
        """Build cost analytics dashboard

        Structure:
        1. Cost by model (Claude vs others)
        2. Cost by operation (embedding vs rerank)
        3. Cost by user (top spenders)
        4. Cost forecast
        """

        panels = [
            DashboardPanel(
                title="Cost by Model (30d)",
                metric_queries=["memory_cost_by_model"],
                visualization_type="pie_chart",
                width=6,
                description="Breakdown by embedding model",
            ),
            DashboardPanel(
                title="Cost by Operation",
                metric_queries=[
                    "memory_cost_embedding_total",
                    "memory_cost_rerank_total",
                    "memory_cost_storage_total",
                ],
                visualization_type="stacked_bar",
                width=6,
                description="Embedding vs reranking vs storage",
            ),
            DashboardPanel(
                title="Top 10 Users by Cost (30d)",
                metric_queries=["memory_cost_by_user_top10"],
                visualization_type="table",
                width=12,
                description="Cost per user (identify high-spend users)",
            ),
            DashboardPanel(
                title="Projected Monthly Cost",
                metric_queries=["memory_cost_forecast_month"],
                visualization_type="gauge",
                width=4,
                description="Forecast based on last 7 days",
            ),
            DashboardPanel(
                title="Cost Anomalies",
                metric_queries=["memory_cost_anomalies"],
                visualization_type="table",
                width=8,
                alert_threshold=1.5,  # 50% increase
                description="Users with unusual cost patterns",
            ),
        ]

        return panels


class OperationsDashboardConfig:
    """Runtime configuration for operations dashboard"""

    def __init__(self):
        self.name = "Memory System - Operations"
        self.description = "Real-time memory subsystem health for on-call engineers"
        self.dashboard_type = DashboardType.OPERATIONS
        self.refresh_interval = 30  # seconds
        self.time_range = "1h"  # default range
        self.panels = DashboardBuilder.build_operations_dashboard()

    def get_sli_targets(self) -> dict[str, float]:
        """Get SLI targets shown on dashboard"""
        return {
            "availability": 0.999,  # 99.9%
            "query_p95_latency_ms": 400.0,
            "error_rate": 0.001,  # 0.1%
            "rerank_success_rate": 0.95,  # 95% not skipped
        }

    def get_alert_conditions(self) -> dict[str, Any]:
        """Get alert conditions evaluated on this dashboard"""
        return {
            "leak_attempt": {"level": "critical", "value": "> 0"},
            "rls_violation": {"level": "critical", "value": "> 10 per 5m"},
            "query_latency": {"level": "high", "value": "p95 > 400ms"},
            "rerank_skips": {"level": "high", "value": "> 10 per min"},
            "pool_utilization": {"level": "high", "value": "> 80%"},
        }

    def to_dict(self) -> dict[str, Any]:
        """Export configuration"""
        return {
            "name": self.name,
            "description": self.description,
            "type": self.dashboard_type.value,
            "refresh_interval_sec": self.refresh_interval,
            "default_time_range": self.time_range,
            "panels": [p.to_dict() for p in self.panels],
            "sli_targets": self.get_sli_targets(),
            "alert_conditions": self.get_alert_conditions(),
        }


class DashboardFactory:
    """Create dashboard configurations by type"""

    @staticmethod
    def create(dashboard_type: DashboardType) -> Any:
        """Factory method to create dashboard config

        Args:
            dashboard_type: Type of dashboard to create

        Returns:
            Dashboard configuration object
        """

        if dashboard_type == DashboardType.OPERATIONS:
            return OperationsDashboardConfig()
        elif dashboard_type == DashboardType.DEVELOPMENT:
            return DevelopmentDashboardConfig()
        elif dashboard_type == DashboardType.BUSINESS:
            return BusinessDashboardConfig()
        elif dashboard_type == DashboardType.COST:
            return CostAnalyticsDashboardConfig()
        else:
            raise ValueError(f"Unknown dashboard type: {dashboard_type}")


class DevelopmentDashboardConfig:
    """Debug dashboard config"""

    def __init__(self):
        self.name = "Memory System - Development"
        self.dashboard_type = DashboardType.DEVELOPMENT
        self.panels = DashboardBuilder.build_development_dashboard()


class BusinessDashboardConfig:
    """Executive dashboard config"""

    def __init__(self):
        self.name = "Memory System - Business"
        self.dashboard_type = DashboardType.BUSINESS
        self.panels = DashboardBuilder.build_business_dashboard()


class CostAnalyticsDashboardConfig:
    """Cost analytics dashboard config"""

    def __init__(self):
        self.name = "Memory System - Cost Analytics"
        self.dashboard_type = DashboardType.COST
        self.panels = DashboardBuilder.build_cost_dashboard()


# Dashboard export helpers
def export_dashboard_as_json(dashboard_config: Any) -> dict[str, Any]:
    """Export dashboard configuration as JSON"""
    return {
        "name": getattr(dashboard_config, "name", "Unknown"),
        "type": getattr(dashboard_config, "dashboard_type", "unknown").value,
        "panels": [p.to_dict() for p in getattr(dashboard_config, "panels", [])],
    }


def export_dashboard_as_grafana_json(dashboard_config: Any) -> dict[str, Any]:
    """Export dashboard in Grafana JSON format"""
    # This would be a more detailed export with Grafana-specific fields
    base = export_dashboard_as_json(dashboard_config)
    base["grafana_version"] = "8.0"
    base["uid"] = f"memory-{dashboard_config.dashboard_type.value}"
    return base
