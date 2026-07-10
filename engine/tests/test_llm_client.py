from __future__ import annotations

import asyncio

import httpx

from engine.llm.client import LLMClient


def _client_with_post(post_fn) -> LLMClient:
    client = LLMClient(api_key="k", base_url="http://llm.test", model="m")
    client._http.post = post_fn  # type: ignore[assignment]
    return client


def _run_request(client: LLMClient) -> None:
    try:
        asyncio.run(client._request({"model": "m", "messages": []}))
    except RuntimeError:
        pass
    finally:
        asyncio.run(client.close())


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


def test_request_retries_on_500() -> None:
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
