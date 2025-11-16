"""Circuit breaker for connector resilience.

States: closed (normal), open (failing), half_open (testing recovery).
"""

import json
import os
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


def get_circuit_state_path() -> Path:
    """Get circuit breaker state JSONL path."""
    return Path(os.environ.get("CIRCUIT_STATE_PATH", "logs/connectors/circuit_state.jsonl"))


def get_circuit_state(connector_id: str) -> str:
    """Get current circuit breaker state without full instantiation.

    Args:
        connector_id: Connector identifier

    Returns:
        Circuit state: "closed", "open", "half_open", or "unknown"
    """
    state_path = get_circuit_state_path()
    if not state_path.exists():
        return "closed"  # Default state

    # Last-wins
    latest = None
    try:
        with open(state_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line.strip())
                    if entry.get("connector_id") == connector_id:
                        latest = entry
                except json.JSONDecodeError:
                    continue
    except OSError:
        return "unknown"

    if latest:
        return latest.get("state", "closed")

    return "closed"


class CircuitBreaker:
    """Circuit breaker for connector operations."""

    def __init__(self, connector_id: str):
        """Initialize circuit breaker.

        Args:
            connector_id: Connector identifier
        """
        self.connector_id = connector_id
        self.failures_to_open = int(os.environ.get("CB_FAILURES_TO_OPEN", "5"))
        self.cooldown_seconds = int(os.environ.get("CB_COOLDOWN_S", "60"))
        self.half_open_prob = float(os.environ.get("CB_HALF_OPEN_PROB", "0.2"))

        # Load state
        self.state = "closed"
        self.failure_count = 0
        self.opened_at: Optional[datetime] = None
        self._load_state()

    def _load_state(self):
        """Load circuit breaker state from JSONL."""
        state_path = get_circuit_state_path()
        if not state_path.exists():
            return

        # Last-wins
        latest = None
        with open(state_path, encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line.strip())
                if entry["connector_id"] == self.connector_id:
                    latest = entry

        if latest:
            self.state = latest["state"]
            self.failure_count = latest.get("failure_count", 0)
            if latest.get("opened_at"):
                self.opened_at = datetime.fromisoformat(latest["opened_at"])

    def _save_state(self):
        """Save circuit breaker state to JSONL."""
        state_path = get_circuit_state_path()
        state_path.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "connector_id": self.connector_id,
            "state": self.state,
            "failure_count": self.failure_count,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "updated_at": datetime.now().isoformat(),
        }

        with open(state_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def allow(self) -> bool:
        """Check if operation is allowed.

        Returns:
            True if operation should proceed, False if circuit is open
        """
        if self.state == "closed":
            return True

        if self.state == "open":
            # Check cooldown
            if self.opened_at and datetime.now() - self.opened_at >= timedelta(seconds=self.cooldown_seconds):
                # Transition to half-open
                self.state = "half_open"
                self._save_state()
                return True
            return False

        if self.state == "half_open":
            # Probabilistically allow (test recovery)
            return random.random() < self.half_open_prob

        return False

    def record_success(self):
        """Record successful operation."""
        if self.state == "half_open":
            # Recovery confirmed
            self.state = "closed"
            self.failure_count = 0
            self.opened_at = None
            self._save_state()
        elif self.state == "closed":
            # Reset failure count on success
            if self.failure_count > 0:
                self.failure_count = 0
                self._save_state()

    def record_failure(self):
        """Record failed operation."""
        if self.state == "half_open":
            # Recovery failed, reopen
            self.state = "open"
            self.opened_at = datetime.now()
            self._save_state()
        elif self.state == "closed":
            self.failure_count += 1
            if self.failure_count >= self.failures_to_open:
                # Open circuit
                self.state = "open"
                self.opened_at = datetime.now()
            self._save_state()
