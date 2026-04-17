"""SkyMiner retry decorator for transient network and I/O failures."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

_logger = logging.getLogger(__name__)


def retry(
    max_attempts: int = 3,
    delay_seconds: float = 1.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable:
    """Decorator that retries a function on specified exception types.

    Args:
        max_attempts: Total number of call attempts (including the first).
                      Must be >= 1.
        delay_seconds: Fixed wait time in seconds between consecutive attempts.
        exceptions: Tuple of exception classes that should trigger a retry.
                    Exceptions *not* in this tuple propagate immediately.

    Returns:
        A decorator that wraps the target callable with retry logic.

    Example::

        @retry(max_attempts=3, delay_seconds=2.0, exceptions=(OSError, TimeoutError))
        def fetch_data(url: str) -> bytes:
            ...
    """

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt < max_attempts:
                        _logger.warning(
                            "retry: attempt %d/%d for %r failed with %s: %s — "
                            "retrying in %.1f s",
                            attempt,
                            max_attempts,
                            fn.__qualname__,
                            type(exc).__name__,
                            exc,
                            delay_seconds,
                        )
                        time.sleep(delay_seconds)
                    else:
                        _logger.warning(
                            "retry: attempt %d/%d for %r failed with %s: %s — "
                            "all attempts exhausted, re-raising",
                            attempt,
                            max_attempts,
                            fn.__qualname__,
                            type(exc).__name__,
                            exc,
                        )

            # Re-raise the last captured exception (always set when we reach here).
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator
