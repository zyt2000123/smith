from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from common.yaml_utils import YamlConfigError
from engine.llm.adapters.anthropic import AnthropicAdapter
from engine.llm.adapters._retry import MAX_RETRY_AFTER_SECONDS, retry_after_seconds
from engine.llm.client import ProviderClient
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


def test_explicit_output_limit_is_forwarded_without_changing_openai_default() -> None:
    client = build_llm_client({
        "provider": "openai",
        "api_key": "key",
        "base_url": "https://openai.test/v1",
        "model": "model",
        "max_output_tokens": 123,
    })
    captured: dict[str, object] = {}

    async def fake_post(url, json, *, timeout):
        captured["body"] = json
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://openai.test/v1/chat/completions"),
            json={"choices": [{"message": {"content": "ok"}}]},
        )

    client.adapter._http.post = fake_post  # type: ignore[attr-defined, assignment]
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

    async def fake_post(url, json, *, timeout):
        captured["body"] = json
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://openai.test/v1/chat/completions"),
            json={"choices": [{"message": {"content": "ok"}}]},
        )

    client.adapter._http.post = fake_post  # type: ignore[attr-defined, assignment]
    try:
        response = asyncio.run(client.chat([{"role": "user", "content": "hello"}]))
    finally:
        asyncio.run(client.close())

    assert response.text == "ok"
    assert "max_tokens" not in captured["body"]


def test_anthropic_adapter_translates_tools_conversation_and_response() -> None:
    adapter = AnthropicAdapter(_anthropic_config())
    captured: dict[str, object] = {}

    async def fake_post(url, json, *, timeout):
        captured["url"] = url
        captured["body"] = json
        captured["timeout"] = timeout
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://anthropic.test/v1/messages"),
            json={
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
            },
        )

    adapter._http.post = fake_post  # type: ignore[assignment]
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
