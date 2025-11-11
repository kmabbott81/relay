"""Tests for audit logging."""

import json
import tempfile
from pathlib import Path

from relay_ai.security.audit import AuditAction, AuditLogger, AuditResult, get_audit_logger


def test_audit_logger_creates_log_file():
    """Audit logger creates log file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = AuditLogger(audit_dir=tmpdir)

        logger.log_success(
            tenant_id="tenant1",
            user_id="user1",
            action=AuditAction.RUN_WORKFLOW,
            resource_type="workflow",
            resource_id="wf1",
        )

        # Check log file exists
        log_files = list(Path(tmpdir).glob("audit-*.jsonl"))
        assert len(log_files) == 1


def test_audit_event_log_line_format():
    """Audit event produces valid JSON log line."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = AuditLogger(audit_dir=tmpdir)

        event = logger.log(
            tenant_id="tenant1",
            user_id="user1",
            action=AuditAction.APPROVE_ARTIFACT,
            resource_type="artifact",
            resource_id="art1",
            result=AuditResult.SUCCESS,
            metadata={"cost_usd": 0.05},
        )

        # Verify log line is valid JSON
        log_line = event.to_log_line()
        data = json.loads(log_line)

        assert data["tenant_id"] == "tenant1"
        assert data["user_id"] == "user1"
        assert data["action"] == "approve_artifact"
        assert data["result"] == "success"
        assert data["metadata"]["cost_usd"] == 0.05


def test_audit_log_denied():
    """Log denied action."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = AuditLogger(audit_dir=tmpdir)

        event = logger.log_denied(
            tenant_id="tenant1",
            user_id="user1",
            action=AuditAction.DELETE_TEMPLATE,
            resource_type="template",
            resource_id="tpl1",
            reason="Insufficient permissions",
        )

        assert event.result == AuditResult.DENIED
        assert event.reason == "Insufficient permissions"


def test_audit_log_failure():
    """Log failed action."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = AuditLogger(audit_dir=tmpdir)

        event = logger.log_failure(
            tenant_id="tenant1",
            user_id="user1",
            action=AuditAction.RUN_WORKFLOW,
            resource_type="workflow",
            resource_id="wf1",
            reason="API timeout",
            metadata={"duration_s": 30},
        )

        assert event.result == AuditResult.FAILURE
        assert event.reason == "API timeout"


def test_audit_query_by_tenant():
    """Query audit logs by tenant."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = AuditLogger(audit_dir=tmpdir)

        # Log events for different tenants
        logger.log_success("tenant1", "user1", AuditAction.RUN_WORKFLOW, "workflow", "wf1")
        logger.log_success("tenant1", "user2", AuditAction.RUN_WORKFLOW, "workflow", "wf2")
        logger.log_success("tenant2", "user3", AuditAction.RUN_WORKFLOW, "workflow", "wf3")

        # Query tenant1 only
        events = logger.query(tenant_id="tenant1")

        assert len(events) == 2
        assert all(e.tenant_id == "tenant1" for e in events)


def test_audit_query_by_action():
    """Query audit logs by action."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = AuditLogger(audit_dir=tmpdir)

        # Log different actions
        logger.log_success("tenant1", "user1", AuditAction.RUN_WORKFLOW, "workflow", "wf1")
        logger.log_success("tenant1", "user1", AuditAction.APPROVE_ARTIFACT, "artifact", "art1")
        logger.log_success("tenant1", "user1", AuditAction.REJECT_ARTIFACT, "artifact", "art2")

        # Query approvals only
        events = logger.query(action=AuditAction.APPROVE_ARTIFACT)

        assert len(events) == 1
        assert events[0].action == AuditAction.APPROVE_ARTIFACT


def test_audit_query_by_result():
    """Query audit logs by result."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = AuditLogger(audit_dir=tmpdir)

        # Log mixed results
        logger.log_success("tenant1", "user1", AuditAction.RUN_WORKFLOW, "workflow", "wf1")
        logger.log_denied("tenant1", "user2", AuditAction.DELETE_TEMPLATE, "template", "tpl1", "No permission")
        logger.log_failure("tenant1", "user3", AuditAction.RUN_WORKFLOW, "workflow", "wf2", "API error")

        # Query failures only
        events = logger.query(result=AuditResult.DENIED)

        assert len(events) == 1
        assert events[0].result == AuditResult.DENIED


def test_audit_query_limit():
    """Query respects limit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = AuditLogger(audit_dir=tmpdir)

        # Log 10 events
        for i in range(10):
            logger.log_success("tenant1", f"user{i}", AuditAction.RUN_WORKFLOW, "workflow", f"wf{i}")

        # Query with limit=3
        events = logger.query(limit=3)

        assert len(events) == 3


def test_global_audit_logger():
    """Global audit logger singleton works."""
    logger1 = get_audit_logger()
    logger2 = get_audit_logger()

    assert logger1 is logger2  # Same instance
