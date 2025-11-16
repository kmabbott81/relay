"""Audit logging for security and compliance."""

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class AuditAction(str, Enum):
    """Audit event actions."""

    # Workflow actions
    RUN_WORKFLOW = "run_workflow"
    PREVIEW_TEMPLATE = "preview_template"
    RENDER_TEMPLATE = "render_template"

    # Approval actions
    APPROVE_ARTIFACT = "approve_artifact"
    REJECT_ARTIFACT = "reject_artifact"

    # CRUD actions
    CREATE_TEMPLATE = "create_template"
    UPDATE_TEMPLATE = "update_template"
    DELETE_TEMPLATE = "delete_template"

    # Export actions
    EXPORT_ARTIFACT = "export_artifact"
    EXPORT_BATCH = "export_batch"

    # Config actions
    UPDATE_CONFIG = "update_config"

    # Ingestion actions
    INGEST_CORPUS = "ingest_corpus"
    INDEX_BUILD = "index_build"

    # Authentication actions
    LOGIN = "login"
    LOGOUT = "logout"
    AUTH_FAILURE = "auth_failure"


class AuditResult(str, Enum):
    """Audit event results."""

    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    ERROR = "error"


@dataclass
class AuditEvent:
    """Audit event record."""

    timestamp: str
    tenant_id: str
    user_id: str
    action: AuditAction
    resource_type: str
    resource_id: str
    result: AuditResult
    reason: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        # Convert enums to strings
        data["action"] = self.action.value
        data["result"] = self.result.value
        return data

    def to_log_line(self) -> str:
        """Convert to structured log line (JSON)."""
        return json.dumps(self.to_dict(), separators=(",", ":"))


class AuditLogger:
    """Audit logger for security events."""

    def __init__(self, audit_dir: str = "audit"):
        """
        Initialize audit logger.

        Args:
            audit_dir: Directory for audit logs
        """
        self.audit_dir = Path(audit_dir)
        self.audit_dir.mkdir(parents=True, exist_ok=True)

        # Get current date for daily log file
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.log_file = self.audit_dir / f"audit-{self.current_date}.jsonl"

    def log(
        self,
        tenant_id: str,
        user_id: str,
        action: AuditAction,
        resource_type: str,
        resource_id: str,
        result: AuditResult,
        reason: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditEvent:
        """
        Log an audit event.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier
            action: Action performed
            resource_type: Type of resource accessed
            resource_id: Resource identifier
            result: Result of the action
            reason: Optional reason (especially for failures)
            metadata: Additional metadata
            ip_address: Client IP address
            user_agent: Client user agent

        Returns:
            AuditEvent that was logged
        """
        event = AuditEvent(
            timestamp=datetime.utcnow().isoformat(),
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            reason=reason,
            metadata=metadata,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Write to log file
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(event.to_log_line() + "\n")
        except Exception as e:
            # Log to stderr if file write fails
            print(f"AUDIT_ERROR: Failed to write audit log: {e}", flush=True)
            print(f"AUDIT_EVENT: {event.to_log_line()}", flush=True)

        return event

    def log_success(
        self,
        tenant_id: str,
        user_id: str,
        action: AuditAction,
        resource_type: str,
        resource_id: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AuditEvent:
        """Log a successful action."""
        return self.log(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=AuditResult.SUCCESS,
            metadata=metadata,
        )

    def log_denied(
        self,
        tenant_id: str,
        user_id: str,
        action: AuditAction,
        resource_type: str,
        resource_id: str,
        reason: str,
    ) -> AuditEvent:
        """Log a denied action (authorization failure)."""
        return self.log(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=AuditResult.DENIED,
            reason=reason,
        )

    def log_failure(
        self,
        tenant_id: str,
        user_id: str,
        action: AuditAction,
        resource_type: str,
        resource_id: str,
        reason: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AuditEvent:
        """Log a failed action (execution error)."""
        return self.log(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=AuditResult.FAILURE,
            reason=reason,
            metadata=metadata,
        )

    def query(
        self,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        action: Optional[AuditAction] = None,
        result: Optional[AuditResult] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """
        Query audit logs.

        Args:
            tenant_id: Filter by tenant
            user_id: Filter by user
            action: Filter by action
            result: Filter by result
            start_date: Filter by start date (YYYY-MM-DD)
            end_date: Filter by end date (YYYY-MM-DD)
            limit: Maximum number of events to return

        Returns:
            List of matching audit events
        """
        events = []

        # Determine which log files to scan
        log_files = []
        if start_date and end_date:
            # TODO: Scan date range
            log_files = list(self.audit_dir.glob("audit-*.jsonl"))
        else:
            # Just scan current log file
            log_files = [self.log_file] if self.log_file.exists() else []

        for log_file in log_files:
            try:
                with open(log_file, encoding="utf-8") as f:
                    for line in f:
                        try:
                            data = json.loads(line.strip())

                            # Apply filters
                            if tenant_id and data.get("tenant_id") != tenant_id:
                                continue
                            if user_id and data.get("user_id") != user_id:
                                continue
                            if action and data.get("action") != action.value:
                                continue
                            if result and data.get("result") != result.value:
                                continue

                            # Reconstruct AuditEvent
                            event = AuditEvent(
                                timestamp=data["timestamp"],
                                tenant_id=data["tenant_id"],
                                user_id=data["user_id"],
                                action=AuditAction(data["action"]),
                                resource_type=data["resource_type"],
                                resource_id=data["resource_id"],
                                result=AuditResult(data["result"]),
                                reason=data.get("reason"),
                                metadata=data.get("metadata"),
                                ip_address=data.get("ip_address"),
                                user_agent=data.get("user_agent"),
                            )

                            events.append(event)

                            if len(events) >= limit:
                                return events

                        except (json.JSONDecodeError, KeyError, ValueError):
                            continue  # Skip malformed lines

            except FileNotFoundError:
                continue

        return events


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        audit_dir = os.getenv("AUDIT_LOG_DIR", "audit")
        _audit_logger = AuditLogger(audit_dir=audit_dir)
    return _audit_logger


def audit_log(
    tenant_id: str,
    user_id: str,
    action: AuditAction,
    resource_type: str,
    resource_id: str,
    result: AuditResult,
    **kwargs,
) -> AuditEvent:
    """Convenience function for logging audit events."""
    logger = get_audit_logger()
    return logger.log(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        **kwargs,
    )
