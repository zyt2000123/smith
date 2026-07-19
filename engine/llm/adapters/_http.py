"""Shared HTTP plumbing for provider adapters.

Provides the retry/backoff loop, the non-streaming JSON request cycle,
bounded response reading, and error-body extraction that every HTTP-based
adapter needs.  Adapters inherit from :class:`HTTPAdapterMixin` alongside
the ``ProviderAdapter`` protocol.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..contracts import LLMResponseError, LLMTimeouts
from ._retry import (
    MAX_RETRIES,
    is_retryable_status,
    retry_after_seconds,
    wait_for_retry,
)

logger = logging.getLogger(__name__)

MAX_RESPONSE_BYTES = 20 * 1024 * 1024  # 20 MiB cap on non-streaming responses
MAX_STREAM_TOTAL_BYTES = 20 * 1024 * 1024
MAX_STREAM_EVENT_BYTES = 1 * 1024 * 1024
MAX_STREAM_EVENTS = 10_000
MAX_STREAM_DURATION_SECONDS = 15 * 60


@dataclass
class SSEStreamLimiter:
    """Bound an untrusted provider SSE stream across every adapter."""

    total_bytes: int = 0
    event_bytes: int = 0
    events: int = 0
    started_at: float = field(default_factory=time.monotonic)

    def consume_line(self, line: str) -> None:
        line_bytes = len(line.encode("utf-8"))
        self.total_bytes += line_bytes
        self.event_bytes += line_bytes
        if self.total_bytes > MAX_STREAM_TOTAL_BYTES:
            raise LLMResponseError("Provider stream exceeds the total byte limit.")
        if self.event_bytes > MAX_STREAM_EVENT_BYTES:
            raise LLMResponseError("Provider stream event exceeds the byte limit.")
        if time.monotonic() - self.started_at > MAX_STREAM_DURATION_SECONDS:
            raise LLMResponseError("Provider stream exceeds the duration limit.")

    def finish_event(self) -> None:
        self.events += 1
        if self.events > MAX_STREAM_EVENTS:
            raise LLMResponseError("Provider stream exceeds the event limit.")
        self.event_bytes = 0


class HTTPAdapterMixin:
    """Reusable HTTP helpers mixed into concrete provider adapters.

    Expects the concrete class to provide ``_http``, ``timeouts``, and
    ``_completion_path``, and to override ``_error_label`` for its own
    diagnostics prefix.
    """

    _http: httpx.AsyncClient  # provided by the concrete adapter
    timeouts: LLMTimeouts  # provided by the concrete adapter
    _completion_path: str  # POST endpoint for completion requests
    _error_label: str = "LLM"  # prefix used in diagnostics and log lines

    async def _wait_for_retry(self, attempt: int, retry_after: float | None = None) -> None:
        await wait_for_retry(attempt, retry_after)

    async def _retry_with_backoff(
        self,
        body: dict[str, Any],
        attempt: int,
        *,
        retry_after: float | None = None,
    ) -> dict[str, Any]:
        await self._wait_for_retry(attempt, retry_after)
        return await self._request(body, attempt + 1)

    async def _request(self, body: dict[str, Any], attempt: int = 0) -> dict[str, Any]:
        """POST ``body`` to ``_completion_path``, retrying transient failures."""
        try:
            raw = await self._read_bounded(
                "POST", self._completion_path, body, self.timeouts.request_timeout(),
            )
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, RecursionError) as exc:
                raise LLMResponseError(
                    f"{self._error_label} response contains invalid JSON."
                ) from exc
            if not isinstance(payload, dict):
                raise LLMResponseError(
                    f"{self._error_label} response must be a JSON object."
                )
            return payload
        except httpx.HTTPStatusError as exc:
            if is_retryable_status(exc.response.status_code) and attempt < MAX_RETRIES - 1:
                logger.warning(
                    "%s request attempt %d failed (HTTP %d), retrying",
                    self._error_label, attempt + 1, exc.response.status_code,
                )
                return await self._retry_with_backoff(
                    body,
                    attempt,
                    retry_after=retry_after_seconds(exc.response),
                )
            raise LLMResponseError(
                f"{self._error_label} request failed (HTTP {exc.response.status_code}) "
                f"after {attempt + 1} attempt(s)."
            ) from exc
        except httpx.RequestError as exc:
            if attempt < MAX_RETRIES - 1:
                logger.warning(
                    "%s request attempt %d failed (%s), retrying",
                    self._error_label, attempt + 1, type(exc).__name__,
                )
                return await self._retry_with_backoff(body, attempt)
            raise LLMResponseError(
                f"{self._error_label} request failed after {MAX_RETRIES} attempts: {exc}"
            ) from exc

    async def _read_bounded(
        self,
        method: str,
        url: str,
        body: dict[str, Any],
        timeout: httpx.Timeout,
    ) -> bytes:
        """Stream-read with a hard byte cap -- aborts before buffering oversized bodies."""
        req = self._http.build_request(method, url, json=body, timeout=timeout)
        response = await self._http.send(req, stream=True)
        try:
            if not response.is_success:
                response.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise LLMResponseError(
                        f"Provider response exceeds {MAX_RESPONSE_BYTES} byte limit."
                    )
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            await response.aclose()
