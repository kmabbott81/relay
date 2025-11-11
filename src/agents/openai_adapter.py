"""Production-ready OpenAI adapter with retry, timeout, and cost tracking.

Provides unified interface for OpenAI API calls with:
- Exponential backoff retry
- Configurable timeouts
- Cost tracking to JSONL
- Typed exceptions
- Mock-friendly interface for testing
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from openai import OpenAI
from openai import OpenAIError, APITimeoutError, RateLimitError

from relay_ai.retries import retry_with_backoff


# Configure logging
logger = logging.getLogger(__name__)


class OpenAIAdapterError(Exception):
    """Base exception for OpenAI adapter errors."""

    pass


class OpenAITimeoutError(OpenAIAdapterError):
    """Raised when OpenAI API call times out."""

    pass


class OpenAIQuotaError(OpenAIAdapterError):
    """Raised when OpenAI API quota is exceeded."""

    pass


class CostTracker:
    """Track OpenAI API costs to JSONL log."""

    # Approximate pricing per 1M tokens (as of 2025)
    PRICING = {
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4-turbo": {"input": 10.00, "output": 30.00},
        "gpt-4": {"input": 30.00, "output": 60.00},
        "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    }

    def __init__(self, log_path: Path):
        """
        Initialize cost tracker.

        Args:
            log_path: Path to cost events JSONL file
        """
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def estimate_cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """
        Estimate cost for a request.

        Args:
            model: Model name (e.g., 'gpt-4o')
            tokens_in: Input tokens
            tokens_out: Output tokens

        Returns:
            Estimated cost in USD
        """
        # Normalize model name
        model_key = model.lower()
        for known_model in self.PRICING:
            if known_model in model_key:
                pricing = self.PRICING[known_model]
                cost = (tokens_in * pricing["input"] + tokens_out * pricing["output"]) / 1_000_000
                return round(cost, 6)

        # Unknown model - return 0
        logger.warning(f"Unknown model for cost estimation: {model}")
        return 0.0

    def log_event(
        self,
        tenant: str,
        workflow: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost_estimate: float,
    ):
        """
        Log a cost event.

        Args:
            tenant: Tenant identifier
            workflow: Workflow name
            model: Model name
            tokens_in: Input tokens
            tokens_out: Output tokens
            cost_estimate: Estimated cost in USD
        """
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "tenant": tenant,
            "workflow": workflow,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_estimate": cost_estimate,
        }

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")


class OpenAIAdapter:
    """Production-ready OpenAI adapter with retry and cost tracking."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        connect_timeout_ms: Optional[int] = None,
        read_timeout_ms: Optional[int] = None,
        tenant_id: Optional[str] = None,
        cost_log_path: Optional[Path] = None,
    ):
        """
        Initialize OpenAI adapter.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            base_url: OpenAI base URL (defaults to OPENAI_BASE_URL env var)
            model: Default model (defaults to OPENAI_MODEL env var)
            max_tokens: Default max tokens (defaults to OPENAI_MAX_TOKENS env var)
            temperature: Default temperature (defaults to OPENAI_TEMPERATURE env var)
            connect_timeout_ms: Connection timeout in ms (defaults to OPENAI_CONNECT_TIMEOUT_MS env var)
            read_timeout_ms: Read timeout in ms (defaults to OPENAI_READ_TIMEOUT_MS env var)
            tenant_id: Tenant identifier (defaults to TENANT_ID env var)
            cost_log_path: Path to cost log (defaults to logs/cost_events.jsonl)
        """
        # Load from environment
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o")
        self.max_tokens = max_tokens or int(os.getenv("OPENAI_MAX_TOKENS", "2000"))
        self.temperature = temperature or float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
        self.tenant_id = tenant_id or os.getenv("TENANT_ID", "default")

        # Timeouts in seconds
        connect_timeout_ms = connect_timeout_ms or int(os.getenv("OPENAI_CONNECT_TIMEOUT_MS", "30000"))
        read_timeout_ms = read_timeout_ms or int(os.getenv("OPENAI_READ_TIMEOUT_MS", "60000"))
        self.timeout = (connect_timeout_ms / 1000.0, read_timeout_ms / 1000.0)

        if not self.api_key:
            raise OpenAIAdapterError("OPENAI_API_KEY not set")

        # Initialize OpenAI client
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)

        # Initialize cost tracker
        if cost_log_path is None:
            project_root = Path(__file__).parent.parent.parent
            cost_log_path = project_root / "logs" / "cost_events.jsonl"
        self.cost_tracker = CostTracker(cost_log_path)

    @retry_with_backoff(
        max_attempts=3,
        base_delay=1.0,
        max_delay=30.0,
        jitter_factor=0.1,
        retryable_exceptions=(OpenAIError, APITimeoutError, RateLimitError),
    )
    def generate_text(
        self,
        prompt: str,
        workflow: str = "unknown",
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **opts: Any,
    ) -> str:
        """
        Generate text from a prompt.

        Args:
            prompt: Input prompt
            workflow: Workflow name (for cost tracking)
            model: Model to use (overrides default)
            max_tokens: Max tokens (overrides default)
            temperature: Temperature (overrides default)
            **opts: Additional options passed to OpenAI API

        Returns:
            Generated text

        Raises:
            OpenAIAdapterError: On API errors
            OpenAITimeoutError: On timeout
            OpenAIQuotaError: On quota exceeded
        """
        try:
            response = self.client.chat.completions.create(
                model=model or self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens or self.max_tokens,
                temperature=temperature if temperature is not None else self.temperature,
                **opts,
            )

            # Extract text and usage
            text = response.choices[0].message.content or ""
            tokens_in = response.usage.prompt_tokens if response.usage else 0
            tokens_out = response.usage.completion_tokens if response.usage else 0

            # Track cost
            cost = self.cost_tracker.estimate_cost(model or self.model, tokens_in, tokens_out)
            self.cost_tracker.log_event(self.tenant_id, workflow, model or self.model, tokens_in, tokens_out, cost)

            return text

        except APITimeoutError as e:
            logger.error(f"OpenAI API timeout: {e}")
            raise OpenAITimeoutError(f"Request timed out: {e}") from e
        except RateLimitError as e:
            logger.error(f"OpenAI rate limit exceeded: {e}")
            raise OpenAIQuotaError(f"Rate limit exceeded: {e}") from e
        except OpenAIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise OpenAIAdapterError(f"API error: {e}") from e

    @retry_with_backoff(
        max_attempts=3,
        base_delay=1.0,
        max_delay=30.0,
        jitter_factor=0.1,
        retryable_exceptions=(OpenAIError, APITimeoutError, RateLimitError),
    )
    def chat(
        self,
        messages: list[dict[str, str]],
        workflow: str = "unknown",
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **opts: Any,
    ) -> str:
        """
        Chat completion with conversation history.

        Args:
            messages: List of message dicts with 'role' and 'content'
            workflow: Workflow name (for cost tracking)
            model: Model to use (overrides default)
            max_tokens: Max tokens (overrides default)
            temperature: Temperature (overrides default)
            **opts: Additional options passed to OpenAI API

        Returns:
            Assistant response text

        Raises:
            OpenAIAdapterError: On API errors
            OpenAITimeoutError: On timeout
            OpenAIQuotaError: On quota exceeded
        """
        try:
            response = self.client.chat.completions.create(
                model=model or self.model,
                messages=messages,
                max_tokens=max_tokens or self.max_tokens,
                temperature=temperature if temperature is not None else self.temperature,
                **opts,
            )

            # Extract text and usage
            text = response.choices[0].message.content or ""
            tokens_in = response.usage.prompt_tokens if response.usage else 0
            tokens_out = response.usage.completion_tokens if response.usage else 0

            # Track cost
            cost = self.cost_tracker.estimate_cost(model or self.model, tokens_in, tokens_out)
            self.cost_tracker.log_event(self.tenant_id, workflow, model or self.model, tokens_in, tokens_out, cost)

            return text

        except APITimeoutError as e:
            logger.error(f"OpenAI API timeout: {e}")
            raise OpenAITimeoutError(f"Request timed out: {e}") from e
        except RateLimitError as e:
            logger.error(f"OpenAI rate limit exceeded: {e}")
            raise OpenAIQuotaError(f"Rate limit exceeded: {e}") from e
        except OpenAIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise OpenAIAdapterError(f"API error: {e}") from e


class MockOpenAIAdapter:
    """Mock adapter for testing (no actual API calls)."""

    def __init__(self, **kwargs):
        """Initialize mock adapter (accepts same args as OpenAIAdapter)."""
        self.tenant_id = kwargs.get("tenant_id", "test-tenant")
        self.model = kwargs.get("model", "gpt-4o-mock")

    def generate_text(self, prompt: str, workflow: str = "unknown", **opts: Any) -> str:
        """
        Mock text generation.

        Args:
            prompt: Input prompt
            workflow: Workflow name
            **opts: Additional options (ignored)

        Returns:
            Mock response
        """
        return f"[MOCK] Generated response for prompt: {prompt[:50]}..."

    def chat(self, messages: list[dict[str, str]], workflow: str = "unknown", **opts: Any) -> str:
        """
        Mock chat completion.

        Args:
            messages: Conversation messages
            workflow: Workflow name
            **opts: Additional options (ignored)

        Returns:
            Mock response
        """
        last_message = messages[-1]["content"] if messages else ""
        return f"[MOCK] Chat response for: {last_message[:50]}..."


# Factory function for easy testing
def create_adapter(use_mock: bool = False, **kwargs) -> OpenAIAdapter | MockOpenAIAdapter:
    """
    Create an OpenAI adapter (real or mock).

    Args:
        use_mock: If True, return MockOpenAIAdapter
        **kwargs: Arguments passed to adapter constructor

    Returns:
        OpenAI adapter instance
    """
    if use_mock:
        return MockOpenAIAdapter(**kwargs)
    return OpenAIAdapter(**kwargs)
