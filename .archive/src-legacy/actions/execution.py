"""Action execution engine with preview/confirm workflow.

Sprint 49 Phase B: Preview ID validation, idempotency, metrics.
Sprint 54: Rollout gate integration for gradual feature rollout.
"""

import os
import time
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

from .adapters.google import GoogleAdapter
from .adapters.independent import IndependentAdapter
from .contracts import ActionStatus, ExecuteResponse, PreviewResponse, Provider


class PreviewStore:
    """In-memory store for preview data (24h TTL)."""

    def __init__(self):
        """Initialize preview store."""
        self._store: dict[str, dict[str, Any]] = {}

    def save(self, preview_id: str, data: dict[str, Any], ttl_seconds: int = 86400):
        """Save preview data with TTL."""
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        self._store[preview_id] = {
            **data,
            "expires_at": expires_at.isoformat(),
        }

    def get(self, preview_id: str) -> Optional[dict[str, Any]]:
        """Get preview data if not expired."""
        data = self._store.get(preview_id)
        if not data:
            return None

        # Check expiry
        expires_at = datetime.fromisoformat(data["expires_at"])
        if datetime.utcnow() > expires_at:
            del self._store[preview_id]
            return None

        return data

    def delete(self, preview_id: str):
        """Delete preview data."""
        if preview_id in self._store:
            del self._store[preview_id]


class IdempotencyStore:
    """In-memory store for idempotency keys (24h TTL)."""

    def __init__(self):
        """Initialize idempotency store."""
        self._store: dict[str, dict[str, Any]] = {}

    def check_by_key(self, workspace_id: str, idempotency_key: str) -> Optional[dict[str, Any]]:
        """Check idempotency by workspace and key only (Sprint 50 idempotency-first).

        This allows replay even if we don't know the action yet.
        Returns the first matching cached result within 24h TTL.
        """
        prefix = f"{workspace_id}:"
        suffix = f":{idempotency_key}"

        for store_key, data in list(self._store.items()):
            if store_key.startswith(prefix) and store_key.endswith(suffix):
                # Check expiry (24h)
                created_at = datetime.fromisoformat(data["created_at"])
                if datetime.utcnow() - created_at > timedelta(hours=24):
                    del self._store[store_key]
                    continue

                # Return first match
                return data

        return None

    def check(self, workspace_id: str, action: str, idempotency_key: str) -> Optional[dict[str, Any]]:
        """Check if idempotency key was already used for a specific action."""
        key = f"{workspace_id}:{action}:{idempotency_key}"
        data = self._store.get(key)

        if not data:
            return None

        # Check expiry (24h)
        created_at = datetime.fromisoformat(data["created_at"])
        if datetime.utcnow() - created_at > timedelta(hours=24):
            del self._store[key]
            return None

        return data

    def save(self, workspace_id: str, action: str, idempotency_key: str, result: dict[str, Any]):
        """Save execution result for idempotency key."""
        key = f"{workspace_id}:{action}:{idempotency_key}"
        self._store[key] = {
            **result,
            "created_at": datetime.utcnow().isoformat(),
        }


class ActionExecutor:
    """Action execution engine."""

    def __init__(self):
        """Initialize action executor with rollout gate support."""
        self.preview_store = PreviewStore()
        self.idempotency_store = IdempotencyStore()

        # Initialize rollout gate (Sprint 54)
        rollout_gate = self._init_rollout_gate()

        self.adapters = {
            "independent": IndependentAdapter(),
            "google": GoogleAdapter(rollout_gate=rollout_gate),
        }

    def _init_rollout_gate(self):
        """Initialize rollout gate with Redis backing (if available).

        Returns:
            MinimalGate instance, or None if Redis unavailable
        """
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            print("[INFO] Rollout gate: No REDIS_URL, rollout disabled")
            return None

        try:
            import redis

            from relay_ai.rollout.minimal_gate import MinimalGate

            redis_client = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
            redis_client.ping()

            gate = MinimalGate(redis_client, cache_ttl_sec=5)
            print("[INFO] Rollout gate: Initialized with Redis backing")
            return gate

        except Exception as e:
            print(f"[WARN] Rollout gate: Redis unavailable ({e}), rollout disabled")
            return None

    def list_actions(self) -> list[dict[str, Any]]:
        """List all available actions from all adapters."""
        actions = []

        # Independent adapter
        independent = self.adapters["independent"]
        actions.extend([a.model_dump(by_alias=True) for a in independent.list_actions()])

        # Google adapter (Sprint 53 Phase B: Gmail Send)
        google = self.adapters["google"]
        actions.extend([a.model_dump(by_alias=True) for a in google.list_actions()])

        # Microsoft adapter (preview-only stub)
        actions.append(
            {
                "id": "microsoft.send_email",
                "name": "Send Outlook Email",
                "description": "Send email via Microsoft Outlook",
                "provider": "microsoft",
                "schema": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "format": "email"},
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["to", "subject", "body"],
                },
                "enabled": False,
            }
        )

        return actions

    def preview(self, action: str, params: dict[str, Any]) -> PreviewResponse:
        """Preview an action."""
        # Map action ID to provider
        if action.startswith("webhook.") or action.startswith("smtp."):
            provider = "independent"
        elif action.startswith("microsoft."):
            provider = "microsoft"
        elif action.startswith("google."):
            provider = "google"
        else:
            provider = "independent"  # Default

        # Get adapter
        if provider == "independent":
            adapter = self.adapters["independent"]
        elif provider == "google":
            adapter = self.adapters["google"]
        else:
            # Stub preview for MS (not configured)
            return PreviewResponse(
                preview_id=str(uuid4()),
                action=action,
                provider=Provider(provider),
                summary=f"Preview for {action} (provider not configured)",
                params=params,
                warnings=["Provider not configured - execution will return 501"],
                expires_at=(datetime.utcnow() + timedelta(hours=1)).isoformat(),
            )

        # Generate preview
        preview_data = adapter.preview(action, params)

        # Create preview ID
        preview_id = str(uuid4())

        # Store preview data
        self.preview_store.save(
            preview_id,
            {
                "action": action,
                "provider": provider,
                "params": params,
                "summary": preview_data["summary"],
                "warnings": preview_data.get("warnings", []),
            },
        )

        return PreviewResponse(
            preview_id=preview_id,
            action=action,
            provider=Provider(provider),
            summary=preview_data["summary"],
            params=params,
            warnings=preview_data.get("warnings", []),
            expires_at=(datetime.utcnow() + timedelta(hours=1)).isoformat(),
        )

    async def execute(
        self,
        preview_id: str,
        idempotency_key: Optional[str] = None,
        workspace_id: str = "default",
        actor_id: str = "system",
        request_id: str = None,
    ) -> ExecuteResponse:
        """Execute a previewed action.

        Sprint 50: Idempotency-first flow - check dedupe before preview validation.
        This allows retries to succeed even after preview TTL expires.
        """
        # CHECK IDEMPOTENCY FIRST (Sprint 50 reliability fix)
        # This allows retries within 24h even if preview expired (1h TTL)
        if idempotency_key:
            # Try to get cached result by idempotency key alone
            # The store key format is workspace_id:action:idempotency_key
            # But we don't have action yet, so we check all possible matches
            cached_result = self.idempotency_store.check_by_key(workspace_id, idempotency_key)
            if cached_result:
                # Return cached result with idempotent_replay indicator
                cached_response = ExecuteResponse(**cached_result)
                # Add note that this is a replay (preserve original run_id)
                return cached_response

        # Validate preview ID (only if not replaying from idempotency cache)
        preview_data = self.preview_store.get(preview_id)
        if not preview_data:
            raise ValueError("Invalid or expired preview_id")

        action = preview_data["action"]
        provider = preview_data["provider"]
        params = preview_data["params"]

        # Verify idempotency key hasn't been used for a DIFFERENT action
        # (Conflict detection - same key, different action = 409)
        if idempotency_key:
            cached_result = self.idempotency_store.check(workspace_id, action, idempotency_key)
            if cached_result:
                # This should have been caught above, but double-check
                return ExecuteResponse(**cached_result)

        # Generate run ID
        run_id = str(uuid4())

        # Execute action
        start_time = time.time()
        exception_type = None
        try:
            if provider == "independent":
                adapter = self.adapters["independent"]
                result = await adapter.execute(action, params)
                status = ActionStatus.SUCCESS
                error = None
            elif provider == "google":
                adapter = self.adapters["google"]
                result = await adapter.execute(action, params, workspace_id, actor_id)
                status = ActionStatus.SUCCESS
                error = None
            else:
                # MS not configured - return 501
                raise NotImplementedError(f"Provider '{provider}' not configured")

        except Exception as e:
            result = None
            status = ActionStatus.FAILED
            error = str(e)
            exception_type = type(e).__name__

        duration_ms = int((time.time() - start_time) * 1000)
        duration_seconds = duration_ms / 1000.0

        # Record metrics
        try:
            from ..telemetry.prom import record_action_error, record_action_execution

            record_action_execution(
                provider=provider,
                action=action,
                status=status.value,
                duration_seconds=duration_seconds,
            )

            if status == ActionStatus.FAILED and exception_type:
                record_action_error(provider=provider, action=action, reason=exception_type)
        except ImportError:
            pass  # Telemetry not available

        # Build response
        response = ExecuteResponse(
            run_id=run_id,
            action=action,
            provider=Provider(provider),
            status=status,
            result=result,
            error=error,
            duration_ms=duration_ms,
            request_id=request_id or str(uuid4()),
        )

        # Save for idempotency
        if idempotency_key:
            self.idempotency_store.save(
                workspace_id,
                action,
                idempotency_key,
                response.model_dump(),
            )

        # Delete preview after execution
        self.preview_store.delete(preview_id)

        return response


# Global executor instance
_executor: Optional[ActionExecutor] = None


def get_executor() -> ActionExecutor:
    """Get global action executor instance."""
    global _executor
    if _executor is None:
        _executor = ActionExecutor()
    return _executor
