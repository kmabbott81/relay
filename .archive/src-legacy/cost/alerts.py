"""
Alert System (Sprint 30)

Simple alert sink that writes to console + governance events log.
Future email/Teams hooks can be added later.
"""

from datetime import UTC, datetime

from .enforcer import emit_governance_event


def emit_alert(kind: str, tenant: str, message: str, severity: str = "warning") -> None:
    """
    Emit alert to console and log.

    Args:
        kind: Alert type (budget_exceeded, anomaly, etc.)
        tenant: Tenant identifier
        message: Alert message
        severity: Severity level (info, warning, critical)
    """
    timestamp = datetime.now(UTC).isoformat()

    # Console output
    severity_icon = {
        "info": "ℹ️",
        "warning": "⚠️",
        "critical": "🚨",
    }.get(severity, "•")

    print(f"[{timestamp}] {severity_icon} ALERT [{kind}] {tenant}: {message}")

    # Log to governance events
    emit_governance_event(
        {
            "event": "alert",
            "kind": kind,
            "tenant": tenant,
            "message": message,
            "severity": severity,
        }
    )
