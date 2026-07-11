from __future__ import annotations

import asyncio

import httpx
import pytest

from engine.llm.client import LLMClient, LLMResponseError, LLMTimeouts
from engine.llm.events import ProviderEventType


class _SseStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def __aiter__(self):
        for chunk in self._chunks:
            yield chunk

    async def aclose(self) -> None:
        return None


class _InterruptedSseStream(httpx.AsyncByteStream):
    def __init__(self, first_chunk: bytes) -> None:
        self._first_chunk = first_chunk

    async def __aiter__(self):
        yield self._first_chunk
        raise httpx.ReadError("stream interrupted")

    async def aclose(self) -> None:
        return None


def _client_with_post(post_fn) -> LLMClient:
    client = LLMClient(api_key="k", base_url="http://llm.test", model="m")

    async def wrapped_post(url, json, **_kwargs):
        return await post_fn(url, json)

    client._http.post = wrapped_post  # type: ignore[assignment]
    return client


def _client_with_send(send_fn) -> LLMClient:
    client = LLMClient(api_key="k", base_url="http://llm.test", model="m")
    client._http.send = send_fn  # type: ignore[assignment]
    return client


def _successful_stream_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        request=request,
        stream=_SseStream([
            b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n',
            b"data: [DONE]\n\n",
        ]),
    )


def _run_request(client: LLMClient) -> None:
    try:
        asyncio.run(client._request({"model": "m", "messages": []}))
    except RuntimeError:
        pass
    finally:
        asyncio.run(client.close())


def _capture_retry_delays(monkeypatch) -> list[float]:
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("engine.llm.adapters._retry.asyncio.sleep", fake_sleep)
    return delays


def test_request_does_not_retry_on_400() -> None:
    calls = {"n": 0}

    async def fake_post(url, json):
        calls["n"] += 1
        return httpx.Response(
            400,
            request=httpx.Request("POST", "http://llm.test/chat/completions"),
            text="bad request",
        )

    _run_request(_client_with_post(fake_post))

    assert calls["n"] == 1   # 400 是确定性错误，重试无意义


def test_request_retries_on_500(monkeypatch) -> None:
    _capture_retry_delays(monkeypatch)
    calls = {"n": 0}

    async def fake_post(url, json):
        calls["n"] += 1
        return httpx.Response(
            500,
            request=httpx.Request("POST", "http://llm.test/chat/completions"),
            text="server error",
        )

    _run_request(_client_with_post(fake_post))

    assert calls["n"] == 3   # 5xx 仍重试到上限（回归保护）


def test_request_uses_exponential_backoff_for_429(monkeypatch) -> None:
    retry_delays = _capture_retry_delays(monkeypatch)
    calls = {"n": 0}

    async def fake_post(url, json):
        calls["n"] += 1
        return httpx.Response(
            429,
            request=httpx.Request("POST", "http://llm.test/chat/completions"),
            text="rate limited",
        )

    _run_request(_client_with_post(fake_post))

    assert calls["n"] == 3
    assert retry_delays == [1, 2]


def test_request_honors_retry_after_header(monkeypatch) -> None:
    retry_delays = _capture_retry_delays(monkeypatch)
    calls = {"n": 0}

    async def fake_post(url, json):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "7"},
                request=httpx.Request("POST", "http://llm.test/chat/completions"),
            )
        return httpx.Response(
            200,
            request=httpx.Request("POST", "http://llm.test/chat/completions"),
            json={"choices": [{"message": {}}]},
        )

    client = _client_with_post(fake_post)
    try:
        asyncio.run(client.chat([{"role": "user", "content": "hello"}]))
    finally:
        asyncio.run(client.close())

    assert calls["n"] == 2
    assert retry_delays == [7.0]


def test_chat_reports_malformed_tool_arguments_as_provider_error() -> None:
    async def fake_post(url, json):
        return httpx.Response(
            200,
            request=httpx.Request("POST", "http://llm.test/chat/completions"),
            json={
                "choices": [{
                    "message": {
                        "tool_calls": [{
                            "id": "call-1",
                            "function": {"name": "read_file", "arguments": "{"},
                        }],
                    },
                }],
            },
        )

    client = _client_with_post(fake_post)
    try:
        with pytest.raises(LLMResponseError, match="invalid JSON tool-call arguments"):
            asyncio.run(client.chat([{"role": "user", "content": "hello"}]))
    finally:
        asyncio.run(client.close())


def test_chat_preserves_provider_finish_reason() -> None:
    async def fake_post(url, json):
        return httpx.Response(
            200,
            request=httpx.Request("POST", "http://llm.test/chat/completions"),
            json={
                "choices": [{
                    "message": {"content": "partial answer"},
                    "finish_reason": "length",
                }],
            },
        )

    client = _client_with_post(fake_post)
    try:
        response = asyncio.run(client.chat([{"role": "user", "content": "hello"}]))
    finally:
        asyncio.run(client.close())

    assert response.text == "partial answer"
    assert response.finish_reason == "length"


def test_client_uses_distinct_non_stream_and_stream_timeouts() -> None:
    selected_timeouts = LLMTimeouts(
        connect=1.0,
        read=2.0,
        stream_read=3.0,
        write=4.0,
        pool=5.0,
    )
    captured: dict[str, httpx.Timeout] = {}

    async def fake_post(url, json, *, timeout):
        captured["timeout"] = timeout
        return httpx.Response(
            200,
            request=httpx.Request("POST", "http://llm.test/chat/completions"),
            json={"choices": [{"message": {}}]},
        )

    client = LLMClient(
        api_key="k",
        base_url="http://llm.test",
        model="m",
        timeouts=selected_timeouts,
    )
    client._http.post = fake_post  # type: ignore[assignment]
    try:
        asyncio.run(client.chat([{"role": "user", "content": "hello"}]))
    finally:
        asyncio.run(client.close())

    non_stream_timeout = captured["timeout"]
    assert (non_stream_timeout.connect, non_stream_timeout.read) == (1.0, 2.0)
    assert (non_stream_timeout.write, non_stream_timeout.pool) == (4.0, 5.0)
    assert client._http.timeout.read == 3.0


def test_chat_events_exposes_typed_provider_deltas_and_completion() -> None:
    async def fake_send(request, *, stream: bool):
        return httpx.Response(
            200,
            request=request,
            stream=_SseStream([
                b'data:{"choices":[{"delta":{"content":"Hello "}}]}\n\n',
                (
                    b'data: {"choices":[{"delta":{"tool_calls":[{'
                    b'"index":0,"id":"call-1","function":{'
                    b'"name":"read_file","arguments":"{\\"path\\":\\""}}]}}]}\n\n'
                ),
                (
                    b'data: {"choices":[{"delta":{"tool_calls":[{'
                    b'"index":0,"function":{"arguments":"README.md\\"}"}}]}}]}\n\n'
                ),
                b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n',
                b"data: [DONE]\n\n",
            ]),
        )

    client = LLMClient(api_key="k", base_url="http://llm.test", model="m")
    client._http.send = fake_send  # type: ignore[assignment]
    try:
        events = asyncio.run(_collect_events(client))
    finally:
        asyncio.run(client.close())

    assert [event.type for event in events] == [
        ProviderEventType.RESPONSE_CREATED,
        ProviderEventType.OUTPUT_TEXT_DELTA,
        ProviderEventType.FUNCTION_CALL_ARGUMENTS_DELTA,
        ProviderEventType.FUNCTION_CALL_ARGUMENTS_DELTA,
        ProviderEventType.RESPONSE_COMPLETED,
    ]
    assert events[1].data == {"delta": "Hello "}
    assert events[2].data["name"] == "read_file"
    assert events[2].data["arguments_delta"] == '{"path":"'
    assert events[3].data["arguments_delta"] == 'README.md"}'
    assert events[-1].data == {
        "finish_reason": "tool_calls",
        "raw_finish_reason": "tool_calls",
    }


def test_chat_events_retries_429_before_content(monkeypatch) -> None:
    retry_delays = _capture_retry_delays(monkeypatch)
    calls = {"n": 0}

    async def fake_send(request, *, stream: bool):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, request=request, text="rate limited")
        return _successful_stream_response(request)

    client = _client_with_send(fake_send)
    try:
        events = asyncio.run(_collect_events(client))
    finally:
        asyncio.run(client.close())

    assert calls["n"] == 2
    assert retry_delays == [1]
    assert [event.type for event in events] == [
        ProviderEventType.RESPONSE_CREATED,
        ProviderEventType.OUTPUT_TEXT_DELTA,
        ProviderEventType.RESPONSE_COMPLETED,
    ]


def test_chat_events_honors_retry_after_before_content(monkeypatch) -> None:
    retry_delays = _capture_retry_delays(monkeypatch)
    calls = {"n": 0}

    async def fake_send(request, *, stream: bool):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "4"}, request=request)
        return _successful_stream_response(request)

    client = _client_with_send(fake_send)
    try:
        events = asyncio.run(_collect_events(client))
    finally:
        asyncio.run(client.close())

    assert calls["n"] == 2
    assert retry_delays == [4.0]
    assert events[-1].type == ProviderEventType.RESPONSE_COMPLETED


def test_chat_events_retries_transport_error_before_content(monkeypatch) -> None:
    retry_delays = _capture_retry_delays(monkeypatch)
    calls = {"n": 0}

    async def fake_send(request, *, stream: bool):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("connection failed", request=request)
        return _successful_stream_response(request)

    client = _client_with_send(fake_send)
    try:
        events = asyncio.run(_collect_events(client))
    finally:
        asyncio.run(client.close())

    assert calls["n"] == 2
    assert retry_delays == [1]
    assert events[-1].type == ProviderEventType.RESPONSE_COMPLETED


@pytest.mark.parametrize(
    "first_chunk",
    [
        b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n',
        (
            b'data: {"choices":[{"delta":{"tool_calls":[{'
            b'"index":0,"id":"call-1","function":{'
            b'"name":"read_file","arguments":"{}"}}]}}]}\n\n'
        ),
        b'data: {"choices":[{"delta":{"reasoning_content":"thinking..."}}]}\n\n',
    ],
)
def test_chat_events_does_not_retry_after_content_delta(monkeypatch, first_chunk: bytes) -> None:
    retry_delays = _capture_retry_delays(monkeypatch)
    calls = {"n": 0}

    async def fake_send(request, *, stream: bool):
        calls["n"] += 1
        return httpx.Response(
            200,
            request=request,
            stream=_InterruptedSseStream(first_chunk),
        )

    client = _client_with_send(fake_send)
    try:
        with pytest.raises(httpx.ReadError):
            asyncio.run(_collect_events(client))
    finally:
        asyncio.run(client.close())

    assert calls["n"] == 1
    assert retry_delays == []


async def _collect_events(client: LLMClient):
    return [event async for event in client.chat_events([{"role": "user", "content": "hello"}])]
