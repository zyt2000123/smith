from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from common.yaml_utils import YamlConfigError
from engine.llm.adapters.anthropic import AnthropicAdapter
from engine.llm.adapters._retry import MAX_RETRY_AFTER_SECONDS, retry_after_seconds
from engine.llm.client import LLMClient, ProviderClient
from engine.llm.contracts import LLMProviderConfig, LLMRequest
from engine.llm.events import ProviderEventType
from engine.llm.factory import create_llm_client, normalize_provider_name, supported_provider_names
from engine.llm.model_config import build_llm_client
from engine.llm.port import LLMPort


class _SseStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def __aiter__(self):
        for chunk in self._chunks:
            yield chunk

    async def aclose(self) -> None:
        return None


def _anthropic_config(**overrides: object) -> LLMProviderConfig:
    values: dict[str, object] = {
        "provider": "anthropic",
        "api_key": "anthropic-key",
        "base_url": "https://anthropic.test",
        "model": "claude-test",
        "max_output_tokens": 321,
    }
    values.update(overrides)
    return LLMProviderConfig(**values)  # type: ignore[arg-type]


def test_factory_selects_real_adapters_and_preserves_openai_alias() -> None:
    anthropic = create_llm_client(_anthropic_config())
    openai = create_llm_client(_anthropic_config(
        provider="openai",
        base_url="https://openai.test/v1",
    ))
    try:
        assert isinstance(anthropic, LLMPort)
        assert anthropic.provider == "anthropic"
        assert type(anthropic.adapter).__name__ == "AnthropicAdapter"
        assert openai.provider == "openai_compatible"
        assert type(openai.adapter).__name__ == "OpenAICompatibleAdapter"
        assert normalize_provider_name("openai") == "openai_compatible"
        assert supported_provider_names() == ("anthropic", "openai", "openai_compatible")
    finally:
        asyncio.run(anthropic.close())
        asyncio.run(openai.close())


def test_build_llm_client_rejects_unknown_provider() -> None:
    with pytest.raises(YamlConfigError, match="Unsupported LLM provider"):
        build_llm_client({
            "provider": "not-a-provider",
            "api_key": "key",
            "base_url": "https://example.test",
            "model": "model",
        })


def test_provider_retry_after_is_bounded() -> None:
    response = httpx.Response(
        429,
        headers={"Retry-After": "999"},
        request=httpx.Request("POST", "https://provider.test/messages"),
    )
    assert retry_after_seconds(response) == MAX_RETRY_AFTER_SECONDS


def _openai_fake_send(captured: dict[str, object]):
    """Return a fake send that captures the request body and returns a valid response."""
    async def fake_send(request, *, stream: bool = False):
        captured["body"] = json.loads(request.content)
        body = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()
        return httpx.Response(200, request=request, stream=_SseStream([body]))
    return fake_send


def test_explicit_output_limit_is_forwarded_without_changing_openai_default() -> None:
    client = build_llm_client({
        "provider": "openai",
        "api_key": "key",
        "base_url": "https://openai.test/v1",
        "model": "model",
        "max_output_tokens": 123,
    })
    captured: dict[str, object] = {}
    client.adapter._http.send = _openai_fake_send(captured)  # type: ignore[attr-defined, assignment]
    try:
        response = asyncio.run(client.chat([{"role": "user", "content": "hello"}]))
    finally:
        asyncio.run(client.close())

    assert response.text == "ok"
    assert captured["body"]["max_tokens"] == 123


def test_openai_adapter_omits_output_limit_when_not_configured() -> None:
    client = build_llm_client({
        "provider": "openai",
        "api_key": "key",
        "base_url": "https://openai.test/v1",
        "model": "model",
    })
    captured: dict[str, object] = {}
    client.adapter._http.send = _openai_fake_send(captured)  # type: ignore[attr-defined, assignment]
    try:
        response = asyncio.run(client.chat([{"role": "user", "content": "hello"}]))
    finally:
        asyncio.run(client.close())

    assert response.text == "ok"
    assert "max_tokens" not in captured["body"]


def test_anthropic_adapter_translates_tools_conversation_and_response() -> None:
    adapter = AnthropicAdapter(_anthropic_config())
    captured: dict[str, object] = {}

    response_json = json.dumps({
        "content": [
            {"type": "thinking", "thinking": "check the tool result"},
            {"type": "text", "text": "I will look it up."},
            {
                "type": "tool_use",
                "id": "toolu-2",
                "name": "read_file",
                "input": {"path": "README.md"},
            },
        ],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 11, "output_tokens": 7},
    }).encode()

    async def fake_send(request, *, stream: bool = False):
        captured["url"] = str(request.url.raw_path, "ascii")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, request=request, stream=_SseStream([response_json]))

    adapter._http.send = fake_send  # type: ignore[assignment]
    try:
        response = asyncio.run(adapter.complete(LLMRequest(
            messages=[
                {"role": "system", "content": "Stay concise."},
                {"role": "user", "content": "Find the answer."},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "lookup",
                            "arguments": '{"query":"status"}',
                        },
                    }],
                },
                {"role": "tool", "tool_call_id": "call-1", "content": "green"},
                {"role": "user", "content": "Now answer."},
            ],
            tools=[{
                "type": "function",
                "function": {
                    "name": "lookup",
                    "description": "Look up a status.",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
                },
            }],
        )))
    finally:
        asyncio.run(adapter.close())

    body = captured["body"]
    assert captured["url"] == "/v1/messages"
    assert isinstance(body, dict)
    assert body["system"] == "Stay concise."
    assert body["max_tokens"] == 321
    assert body["messages"][0] == {"role": "user", "content": "Find the answer."}
    assert body["messages"][1]["content"] == [{
        "type": "tool_use",
        "id": "call-1",
        "name": "lookup",
        "input": {"query": "status"},
    }]
    assert body["messages"][2]["content"] == [
        {"type": "tool_result", "tool_use_id": "call-1", "content": "green"},
        {"type": "text", "text": "Now answer."},
    ]
    assert body["tools"] == [{
        "name": "lookup",
        "description": "Look up a status.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
    }]
    assert response.text == "I will look it up."
    assert response.reasoning == "check the tool result"
    assert response.finish_reason == "tool_calls"
    assert response.tool_calls[0].arguments == {"path": "README.md"}
    assert response.usage == {"input_tokens": 11, "output_tokens": 7}


def test_anthropic_stream_normalizes_text_tools_usage_and_completion() -> None:
    adapter = AnthropicAdapter(_anthropic_config(max_output_tokens=128))
    client = ProviderClient(adapter)
    captured: dict[str, object] = {}

    async def fake_send(request, *, stream: bool):
        captured["request"] = request
        captured["stream"] = stream
        return httpx.Response(
            200,
            request=request,
            stream=_SseStream([
                b'event: message_start\ndata: {"type":"message_start","message":{"usage":{"input_tokens":4}}}\n\n',
                b'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello "}}\n\n',
                b'event: content_block_start\ndata: {"type":"content_block_start","index":1,"content_block":{"type":"tool_use","id":"toolu-1","name":"lookup","input":{}}}\n\n',
                b'event: content_block_delta\ndata: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"{\\"query\\":\\""}}\n\n',
                b'event: content_block_delta\ndata: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"status\\"}"}}\n\n',
                b'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"tool_use"},"usage":{"output_tokens":9}}\n\n',
                b'event: message_stop\ndata: {"type":"message_stop"}\n\n',
            ]),
        )

    adapter._http.send = fake_send  # type: ignore[assignment]

    async def collect():
        return [
            event
            async for event in client.chat_events([{"role": "user", "content": "hello"}])
        ]

    try:
        events = asyncio.run(collect())
    finally:
        asyncio.run(client.close())

    request = captured["request"]
    assert captured["stream"] is True
    assert request.url.path == "/v1/messages"
    assert request.headers["x-api-key"] == "anthropic-key"
    assert request.headers["anthropic-version"] == "2023-06-01"
    assert json.loads(request.content)["max_tokens"] == 128
    assert [event.type for event in events] == [
        ProviderEventType.RESPONSE_CREATED,
        ProviderEventType.OUTPUT_TEXT_DELTA,
        ProviderEventType.FUNCTION_CALL_ARGUMENTS_DELTA,
        ProviderEventType.FUNCTION_CALL_ARGUMENTS_DELTA,
        ProviderEventType.FUNCTION_CALL_ARGUMENTS_DELTA,
        ProviderEventType.USAGE,
        ProviderEventType.RESPONSE_COMPLETED,
    ]
    assert events[1].data == {"delta": "Hello "}
    assert events[2].data == {"index": 1, "id": "toolu-1", "name": "lookup"}
    assert events[3].data["arguments_delta"] == '{"query":"'
    assert events[4].data["arguments_delta"] == 'status"}'
    assert events[5].data == {"usage": {"input_tokens": 4, "output_tokens": 9}}
    assert events[-1].data == {"finish_reason": "tool_calls", "raw_finish_reason": "tool_use"}


def test_anthropic_moves_late_system_instruction_into_ordered_user_turn() -> None:
    system, messages = AnthropicAdapter._translate_messages([
        {"role": "system", "content": "Initial guidance."},
        {"role": "user", "content": "Start."},
        {"role": "assistant", "content": "Partial."},
        {"role": "system", "content": "Continue exactly."},
    ])

    assert system == "Initial guidance."
    assert messages == [
        {"role": "user", "content": "Start."},
        {"role": "assistant", "content": "Partial."},
        {"role": "user", "content": "Continue exactly."},
    ]


# ── New validation coverage ──────────────────────────────────────────────


def test_openai_response_size_cap_aborts_before_full_parse() -> None:
    from engine.llm.adapters.openai_compatible import _MAX_RESPONSE_BYTES, OpenAICompatibleAdapter
    from engine.llm.contracts import LLMResponseError as _Err

    adapter = OpenAICompatibleAdapter(LLMProviderConfig(
        provider="openai_compatible", api_key="k",
        base_url="https://openai.test/v1", model="m",
    ))
    oversized = b"x" * (_MAX_RESPONSE_BYTES + 1)

    async def fake_send(request, *, stream: bool = False):
        return httpx.Response(200, request=request, stream=_SseStream([oversized]))

    adapter._http.send = fake_send  # type: ignore[assignment]
    with pytest.raises(_Err, match="exceeds"):
        asyncio.run(adapter.complete(LLMRequest(
            messages=[{"role": "user", "content": "hi"}],
        )))
    asyncio.run(adapter.close())


def test_anthropic_response_size_cap() -> None:
    from engine.llm.adapters.anthropic import _MAX_RESPONSE_BYTES
    from engine.llm.contracts import LLMResponseError as _Err

    adapter = AnthropicAdapter(_anthropic_config())
    oversized = b"x" * (_MAX_RESPONSE_BYTES + 1)

    async def fake_send(request, *, stream: bool = False):
        return httpx.Response(200, request=request, stream=_SseStream([oversized]))

    adapter._http.send = fake_send  # type: ignore[assignment]
    with pytest.raises(_Err, match="exceeds"):
        asyncio.run(adapter.complete(LLMRequest(
            messages=[{"role": "user", "content": "hi"}],
        )))
    asyncio.run(adapter.close())


def test_openai_non_string_content_raises() -> None:
    from engine.llm.contracts import LLMResponseError as _Err

    client = LLMClient(api_key="k", base_url="http://llm.test", model="m")
    body = json.dumps({"choices": [{"message": {"content": 42}}]}).encode()

    async def fake_send(request, *, stream: bool = False):
        return httpx.Response(200, request=request, stream=_SseStream([body]))

    client._http.send = fake_send  # type: ignore[assignment]
    with pytest.raises(_Err, match="content must be a string"):
        asyncio.run(client.chat([{"role": "user", "content": "hi"}]))
    asyncio.run(client.close())


def test_openai_stream_malformed_delta_raises() -> None:
    from engine.llm.contracts import LLMResponseError as _Err

    client = LLMClient(api_key="k", base_url="http://llm.test", model="m")

    async def fake_send(request, *, stream: bool):
        return httpx.Response(200, request=request, stream=_SseStream([
            b'data: {"choices":[{"delta":"not-a-dict"}]}\n\n',
            b"data: [DONE]\n\n",
        ]))

    client._http.send = fake_send  # type: ignore[assignment]
    with pytest.raises(_Err, match="delta must be an object"):
        asyncio.run(_collect_events_generic(client))
    asyncio.run(client.close())


def test_anthropic_stream_malformed_delta_raises() -> None:
    from engine.llm.contracts import LLMResponseError as _Err

    adapter = AnthropicAdapter(_anthropic_config())
    client = ProviderClient(adapter)

    async def fake_send(request, *, stream: bool):
        return httpx.Response(200, request=request, stream=_SseStream([
            b'event: message_start\ndata: {"type":"message_start","message":{}}\n\n',
            b'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":"bad"}\n\n',
        ]))

    adapter._http.send = fake_send  # type: ignore[assignment]
    with pytest.raises(_Err, match="content_block_delta must be an object"):
        asyncio.run(_collect_events_generic(client))
    asyncio.run(client.close())


def test_anthropic_stream_tool_use_missing_id_raises() -> None:
    from engine.llm.contracts import LLMResponseError as _Err

    adapter = AnthropicAdapter(_anthropic_config())
    client = ProviderClient(adapter)

    async def fake_send(request, *, stream: bool):
        return httpx.Response(200, request=request, stream=_SseStream([
            b'event: message_start\ndata: {"type":"message_start","message":{}}\n\n',
            b'event: content_block_start\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"tool_use","name":"lookup"}}\n\n',
        ]))

    adapter._http.send = fake_send  # type: ignore[assignment]
    with pytest.raises(_Err, match="missing id or name"):
        asyncio.run(_collect_events_generic(client))
    asyncio.run(client.close())


def test_openai_stream_failure_raises_llm_response_error() -> None:
    """Streaming HTTP failures are wrapped as LLMResponseError, not raw httpx."""
    from engine.llm.contracts import LLMResponseError as _Err

    client = LLMClient(api_key="k", base_url="http://llm.test", model="m")

    async def fake_send(request, *, stream: bool):
        return httpx.Response(401, request=request, stream=_SseStream([b"unauthorized"]))

    client._http.send = fake_send  # type: ignore[assignment]
    with pytest.raises(_Err, match="HTTP 401"):
        asyncio.run(_collect_events_generic(client))
    asyncio.run(client.close())


def test_api_key_hidden_from_config_repr() -> None:
    config = LLMProviderConfig(
        provider="openai_compatible", api_key="sk-secret-key",
        base_url="https://api.test", model="m",
    )
    assert "sk-secret-key" not in repr(config)


async def _collect_events_generic(client):
    return [event async for event in client.chat_events([{"role": "user", "content": "hi"}])]
