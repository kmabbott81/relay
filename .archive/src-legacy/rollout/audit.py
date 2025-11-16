"""Rollout audit logging.

Sprint 54: Audit trail for rollout decisions.

Logs all rollout percentage changes to a markdown file for easy review.
Captures manual changes (by=manual) and future automated changes (by=controller).

Log format:
    2025-10-08T15:00:00Z  google  0% -> 10%  reason=Initial canary  by=manual
    2025-10-15T09:00:00Z  google  10% -> 0%  reason=error spike  by=controller

This log serves as:
- Historical record of rollout decisions
- Input for tuning automated controller thresholds
- Evidence for post-mortems and retrospectives
"""

from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path("docs/evidence/sprint-54/rollout_log.md")


def append_rollout_log(feature: str, old_pct: int, new_pct: int, reason: str, by: str = "manual") -> None:
    """Append a rollout decision to the audit log.

    Creates the log file with a header if it doesn't exist.
    Always appends to preserve full history.

    Args:
        feature: Feature name (e.g., "google")
        old_pct: Previous rollout percentage (0-100)
        new_pct: New rollout percentage (0-100)
        reason: Human-readable reason for the change
        by: Who/what made the change ("manual" or "controller")

    Example:
        # Manual rollout
        append_rollout_log(
            feature="google",
            old_pct=0,
            new_pct=10,
            reason="Initial canary test",
            by="manual"
        )

        # Automated rollback
        append_rollout_log(
            feature="google",
            old_pct=50,
            new_pct=10,
            reason="Error rate > 1%",
            by="controller"
        )
    """
    # Ensure parent directory exists
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Create log with header if it doesn't exist
    if not LOG_PATH.exists():
        LOG_PATH.write_text(
            "# Gmail Rollout Audit Log\n\n"
            "All rollout percentage changes are logged here.\n\n"
            "Format: `timestamp  feature  old% -> new%  reason=...  by=...`\n\n"
            "---\n\n",
            encoding="utf-8",
        )

    # Format timestamp in UTC
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Format log entry
    line = f"{ts}  {feature}  {old_pct}% -> {new_pct}%  reason={reason}  by={by}\n"

    # Append to log
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line)

    print(f"[AUDIT] Rollout change logged: {feature} {old_pct}% -> {new_pct}% ({reason})")
