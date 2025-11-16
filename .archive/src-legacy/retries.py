"""Retry mechanisms with exponential backoff and jitter for API calls."""

import asyncio
import logging
import random
import time
from functools import wraps
from typing import Any, Callable

# Configure logging
logger = logging.getLogger(__name__)


class RetryExhaustedError(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, message: str, last_exception: Exception, attempt_count: int):
        super().__init__(message)
        self.last_exception = last_exception
        self.attempt_count = attempt_count


def exponential_backoff_with_jitter(
    attempt: int, base_delay: float = 1.0, max_delay: float = 60.0, jitter_factor: float = 0.1
) -> float:
    """
    Calculate delay for exponential backoff with jitter.

    Args:
        attempt: Current attempt number (0-based)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        jitter_factor: Jitter factor (0.0-1.0) for randomization

    Returns:
        Delay in seconds
    """
    # Exponential backoff: base_delay * 2^attempt
    delay = base_delay * (2**attempt)

    # Cap at max_delay
    delay = min(delay, max_delay)

    # Add jitter to prevent thundering herd
    jitter = delay * jitter_factor * (2 * random.random() - 1)  # Random between -jitter and +jitter
    delay += jitter

    # Ensure non-negative
    return max(0, delay)


def is_retryable_error(exception: Exception) -> bool:
    """
    Determine if an exception is retryable.

    Args:
        exception: Exception to check

    Returns:
        True if the exception is retryable
    """
    # Common retryable error patterns
    error_msg = str(exception).lower()

    retryable_patterns = [
        "timeout",
        "connection",
        "network",
        "temporary",
        "rate limit",
        "too many requests",
        "server error",
        "503",
        "502",
        "504",
        "429",  # Rate limit
        "500",  # Internal server error
        "connectionerror",
        "httperror",
    ]

    for pattern in retryable_patterns:
        if pattern in error_msg:
            return True

    # Check specific exception types
    if hasattr(exception, "__class__"):
        class_name = exception.__class__.__name__.lower()
        retryable_classes = ["timeout", "connectionerror", "httperror", "requestsexception", "ratelimiterror"]

        for retryable_class in retryable_classes:
            if retryable_class in class_name:
                return True

    return False


def format_retry_reason(exception: Exception, attempt: int, max_attempts: int) -> str:
    """
    Format a clear reason for retry failures.

    Args:
        exception: The exception that caused the failure
        attempt: Current attempt number
        max_attempts: Maximum number of attempts

    Returns:
        Formatted reason string
    """
    exception_name = exception.__class__.__name__
    exception_msg = str(exception)

    if attempt >= max_attempts:
        return f"API call failed after {max_attempts} attempts. Last error: {exception_name}: {exception_msg}"
    else:
        return f"Temporary API error on attempt {attempt + 1}/{max_attempts}: {exception_name}: {exception_msg}"


def retry_with_backoff(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter_factor: float = 0.1,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    max_total_time: float = 300.0,  # 5 minutes max total time
):
    """
    Decorator for retrying functions with exponential backoff and jitter.

    Args:
        max_attempts: Maximum number of attempts
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        jitter_factor: Jitter factor for randomization
        retryable_exceptions: Tuple of exception types to retry on
        max_total_time: Maximum total time to spend retrying

    Returns:
        Decorated function
    """

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs) -> Any:
                start_time = time.time()

                for attempt in range(max_attempts):
                    try:
                        return await func(*args, **kwargs)

                    except Exception as e:
                        # Check if we should retry this exception
                        if not isinstance(e, retryable_exceptions) or not is_retryable_error(e):
                            logger.error(f"Non-retryable error in {func.__name__}: {e}")
                            raise

                        # Check if we've exceeded total time limit
                        elapsed_time = time.time() - start_time
                        if elapsed_time >= max_total_time:
                            logger.error(f"Total retry time limit exceeded for {func.__name__}")
                            raise RetryExhaustedError(format_retry_reason(e, attempt, max_attempts), e, attempt + 1)

                        # Last attempt - don't wait, just raise
                        if attempt == max_attempts - 1:
                            logger.error(f"Final attempt failed for {func.__name__}: {e}")
                            raise RetryExhaustedError(format_retry_reason(e, attempt, max_attempts), e, attempt + 1)

                        # Calculate delay and wait
                        delay = exponential_backoff_with_jitter(attempt, base_delay, max_delay, jitter_factor)

                        logger.warning(
                            f"Attempt {attempt + 1}/{max_attempts} failed for {func.__name__}: {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )

                        await asyncio.sleep(delay)

                # This should never be reached, but just in case
                raise RuntimeError("Unexpected end of retry loop")

            return async_wrapper

        else:

            @wraps(func)
            def sync_wrapper(*args, **kwargs) -> Any:
                start_time = time.time()

                for attempt in range(max_attempts):
                    try:
                        return func(*args, **kwargs)

                    except Exception as e:
                        # Check if we should retry this exception
                        if not isinstance(e, retryable_exceptions) or not is_retryable_error(e):
                            logger.error(f"Non-retryable error in {func.__name__}: {e}")
                            raise

                        # Check if we've exceeded total time limit
                        elapsed_time = time.time() - start_time
                        if elapsed_time >= max_total_time:
                            logger.error(f"Total retry time limit exceeded for {func.__name__}")
                            raise RetryExhaustedError(format_retry_reason(e, attempt, max_attempts), e, attempt + 1)

                        # Last attempt - don't wait, just raise
                        if attempt == max_attempts - 1:
                            logger.error(f"Final attempt failed for {func.__name__}: {e}")
                            raise RetryExhaustedError(format_retry_reason(e, attempt, max_attempts), e, attempt + 1)

                        # Calculate delay and wait
                        delay = exponential_backoff_with_jitter(attempt, base_delay, max_delay, jitter_factor)

                        logger.warning(
                            f"Attempt {attempt + 1}/{max_attempts} failed for {func.__name__}: {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )

                        time.sleep(delay)

                # This should never be reached, but just in case
                raise RuntimeError("Unexpected end of retry loop")

            return sync_wrapper

    return decorator


# Convenience decorators for common retry patterns
def api_retry(func: Callable) -> Callable:
    """Standard API retry decorator with sensible defaults."""
    return retry_with_backoff(
        max_attempts=3, base_delay=1.0, max_delay=30.0, jitter_factor=0.1, max_total_time=120.0  # 2 minutes
    )(func)


def heavy_api_retry(func: Callable) -> Callable:
    """Heavy API retry decorator for expensive operations."""
    return retry_with_backoff(
        max_attempts=5, base_delay=2.0, max_delay=60.0, jitter_factor=0.2, max_total_time=300.0  # 5 minutes
    )(func)


def light_api_retry(func: Callable) -> Callable:
    """Light API retry decorator for fast operations."""
    return retry_with_backoff(
        max_attempts=2, base_delay=0.5, max_delay=10.0, jitter_factor=0.05, max_total_time=30.0  # 30 seconds
    )(func)


# Test functions for demonstration
if __name__ == "__main__":
    import asyncio

    @api_retry
    async def test_async_function(fail_times: int = 0):
        """Test async function that fails a specified number of times."""
        if not hasattr(test_async_function, "call_count"):
            test_async_function.call_count = 0

        test_async_function.call_count += 1

        if test_async_function.call_count <= fail_times:
            raise ConnectionError(f"Simulated connection error (attempt {test_async_function.call_count})")

        return f"Success after {test_async_function.call_count} attempts"

    @api_retry
    def test_sync_function(fail_times: int = 0):
        """Test sync function that fails a specified number of times."""
        if not hasattr(test_sync_function, "call_count"):
            test_sync_function.call_count = 0

        test_sync_function.call_count += 1

        if test_sync_function.call_count <= fail_times:
            raise TimeoutError(f"Simulated timeout (attempt {test_sync_function.call_count})")

        return f"Success after {test_sync_function.call_count} attempts"

    async def test_retries():
        """Test the retry mechanisms."""
        print("Testing retry mechanisms...")

        # Test successful retry (async)
        print("\n1. Testing async retry with 2 failures:")
        try:
            result = await test_async_function(fail_times=2)
            print(f"Result: {result}")
        except Exception as e:
            print(f"Failed: {e}")

        # Reset counter
        test_async_function.call_count = 0

        # Test sync retry
        print("\n2. Testing sync retry with 1 failure:")
        try:
            result = test_sync_function(fail_times=1)
            print(f"Result: {result}")
        except Exception as e:
            print(f"Failed: {e}")

        # Reset counter
        test_sync_function.call_count = 0

        # Test exhausted retries
        print("\n3. Testing exhausted retries (async):")
        try:
            result = await test_async_function(fail_times=5)  # More failures than max attempts
            print(f"Result: {result}")
        except RetryExhaustedError as e:
            print(f"Retry exhausted as expected: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

    # Run tests
    asyncio.run(test_retries())
