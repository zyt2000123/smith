"""Shared transient HTTP failure handling for provider adapters."""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx


MAX_RETRIES = 3
MAX_RETRY_AFTER_SECONDS = 60.0


def is_retryable_status(status: int) -> bool:
    return status == 429 or status >= 500


def retry_after_seconds(response: httpx.Response) -> float | None:
    """Return a bounded provider retry delay, accepting seconds or HTTP dates."""
    retry_after = response.headers.get("Retry-After")
    if not retry_after:
        return None

    try:
        delay = float(retry_after)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(retry_after)
        except (TypeError, ValueError, IndexError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        delay = (retry_at - datetime.now(timezone.utc)).total_seconds()

    if not math.isfinite(delay) or delay < 0:
        return None
    return min(delay, MAX_RETRY_AFTER_SECONDS)


async def wait_for_retry(attempt: int, retry_after: float | None = None) -> None:
    delay = retry_after if retry_after is not None else float(2**attempt)
    await asyncio.sleep(delay)
