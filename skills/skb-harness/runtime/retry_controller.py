"""Retry decision logic.

SPEC: skb-harness-SPEC §11. Retry-safe domain is exit 64-79 (skill→harness).
"""

from __future__ import annotations

RETRY_SAFE_LOW = 64
RETRY_SAFE_HIGH = 79


def is_retry_safe(exit_code: int) -> bool:
    return RETRY_SAFE_LOW <= exit_code <= RETRY_SAFE_HIGH


def should_retry(exit_code: int, attempt: int, max_retry: int) -> bool:
    """Return True if harness should retry the step.

    `max_retry` is the number of retries *after* the initial attempt, so the
    total attempt count when retries are exhausted is `max_retry + 1`.
    """
    if exit_code == 0:
        return False
    if not is_retry_safe(exit_code):
        return False
    return attempt <= max_retry
