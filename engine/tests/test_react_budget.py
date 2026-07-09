from __future__ import annotations

import asyncio

from engine.execution.agent_loop import _react_event_loop, _react_loop, _react_stream_loop
from engine.execution.events import EventType
from engine.llm.client import ChatResponse, ToolCallData
from engine.react_budget import MAX_FAILED_TOOL_RECOVERY_ITERS, TOOL_FAILURE_BUDGET_MESSAGE
from engine.skill.executor import execute_skill
from engine.skill.loader import SkillBody, SkillMeta
from engine.tool.registry import ToolRegistry


class FakeLLM:
    def __init__(
        self,
        responses: list[ChatResponse],
        stream_chunks: list[str] | None = None,
    ) -> None:
        self.responses = list(responses)
        self.stream_chunks = list(stream_chunks or [])
        self.chat_calls: list[dict] = []
        self.stream_calls: list[list[dict]] = []

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        prefix_cache_key: str | None = None,
    ) -> ChatResponse:
        self.chat_calls.append({"messages": messages, "tools": tools})
        if not self.responses:
            return ChatResponse(text="final fallback")
        return self.responses.pop(0)

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ):
        self.stream_calls.append(messages)
        for chunk in self.stream_chunks:
            yield chunk


def _tool_call(name: str = "fail", call_id: str = "call-1") -> ToolCallData:
    return ToolCallData(id=call_id, name=name, arguments={})


def _registry() -> ToolRegistry:
    registry = ToolRegistry()

    async def fail():
        return "Error: boom"

    async def ok():
        return "OK"

    registry.register("fail", "Always fails", {}, fail)
    registry.register("ok", "Succeeds", {}, ok)
    return registry


def test_react_loop_failed_tool_round_does_not_consume_main_budget():
    async def run():
        llm = FakeLLM([
            ChatResponse(tool_calls=[_tool_call()]),
            ChatResponse(text="recovered"),
        ])
        return await _react_loop(
            llm,
            [{"role": "user", "content": "try a tool"}],
            _registry(),
            max_iters=1,
        )

    assert asyncio.run(run()) == "recovered"


def test_react_event_loop_failed_tool_round_can_still_stream_final_text():
    async def run():
        llm = FakeLLM(
            [
                ChatResponse(tool_calls=[_tool_call()]),
                ChatResponse(text="recovered"),
            ],
            stream_chunks=["recovered"],
        )
        events = []
        async for event in _react_event_loop(
            llm,
            [{"role": "user", "content": "try a tool"}],
            _registry(),
            max_iters=1,
        ):
            events.append(event)
        return events

    events = asyncio.run(run())
    text = "".join(
        event.data.get("text", "")
        for event in events
        if event.type == EventType.TEXT_DELTA
    )
    assert text == "recovered"


def test_react_event_loop_uses_decision_response_as_final_text():
    async def run():
        llm = FakeLLM(
            [ChatResponse(text="decision final")],
            stream_chunks=["different stream text"],
        )
        events = []
        async for event in _react_event_loop(
            llm,
            [{"role": "user", "content": "answer directly"}],
            _registry(),
            max_iters=1,
        ):
            events.append(event)
        return events, llm

    events, llm = asyncio.run(run())
    text = "".join(
        event.data.get("text", "")
        for event in events
        if event.type == EventType.TEXT_DELTA
    )
    assert text == "decision final"
    assert llm.stream_calls == []


def test_react_loop_collects_decision_response_from_canonical_events():
    async def run():
        llm = FakeLLM(
            [ChatResponse(text="decision final")],
            stream_chunks=["different stream text"],
        )
        output = await _react_loop(
            llm,
            [{"role": "user", "content": "answer directly"}],
            _registry(),
            max_iters=1,
        )
        return output, llm

    output, llm = asyncio.run(run())
    assert output == "decision final"
    assert llm.stream_calls == []


def test_react_stream_loop_collects_decision_response_from_canonical_events():
    async def run():
        llm = FakeLLM(
            [ChatResponse(text="stream decision")],
            stream_chunks=["different stream text"],
        )
        chunks: list[str] = []
        async for chunk in _react_stream_loop(
            llm,
            [{"role": "user", "content": "answer directly"}],
            _registry(),
            max_iters=1,
        ):
            chunks.append(chunk)
        return chunks, llm

    chunks, llm = asyncio.run(run())
    assert chunks == ["stream decision"]
    assert llm.stream_calls == []


def test_react_event_loop_repairs_incomplete_final_after_tool_success():
    async def run():
        llm = FakeLLM([
            ChatResponse(text="Searching first.", tool_calls=[_tool_call("ok", "search-1")]),
            ChatResponse(text="让我抓取一个排行榜页面获取更详细的信息。"),
            ChatResponse(text="Fetching details.", tool_calls=[_tool_call("ok", "fetch-1")]),
            ChatResponse(text="最终答案：目前没有单一绝对最好的大模型，需要按场景比较。"),
        ])
        events = []
        async for event in _react_event_loop(
            llm,
            [{"role": "user", "content": "现在最好的大语言模型是哪个？"}],
            _registry(),
            max_iters=5,
        ):
            events.append(event)
        return events, llm

    events, llm = asyncio.run(run())
    tool_starts = [
        event
        for event in events
        if event.type == EventType.TOOL_CALL_START
    ]
    text = "".join(
        event.data.get("text", "")
        for event in events
        if event.type == EventType.TEXT_DELTA
    )

    assert [event.data["id"] for event in tool_starts] == ["search-1", "fetch-1"]
    assert "最终答案" in text
    assert len(llm.chat_calls) == 4


def test_react_event_loop_emits_token_usage():
    async def run():
        llm = FakeLLM(
            [
                ChatResponse(
                    text="done",
                    usage={"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
                ),
            ],
            stream_chunks=["done"],
        )
        events = []
        async for event in _react_event_loop(
            llm,
            [{"role": "user", "content": "hello"}],
            _registry(),
            max_iters=1,
        ):
            events.append(event)
        return events

    events = asyncio.run(run())
    usage_events = [event for event in events if event.type == EventType.TOKEN_USAGE]
    assert len(usage_events) == 1
    assert usage_events[0].data == {
        "input_tokens": 11,
        "output_tokens": 7,
        "total_tokens": 18,
    }


def test_react_event_loop_compacts_large_conversation_before_answering():
    async def run():
        llm = FakeLLM(
            [
                ChatResponse(text="compact summary"),
                ChatResponse(text="done"),
            ],
            stream_chunks=["done"],
        )
        events = []
        async for event in _react_event_loop(
            llm,
            [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "x" * 300_000},
            ],
            _registry(),
            max_iters=1,
        ):
            events.append(event)
        return events, llm

    events, llm = asyncio.run(run())

    assert len(llm.chat_calls) >= 2
    assert "Summarize our conversation above" in llm.chat_calls[0]["messages"][-1]["content"]
    text = "".join(
        event.data.get("text", "")
        for event in events
        if event.type == EventType.TEXT_DELTA
    )
    assert text == "done"


def test_execute_skill_failed_tool_round_does_not_consume_main_budget():
    async def run():
        skill = SkillBody(meta=SkillMeta(name="sample"), content="Use tools if needed.")
        llm = FakeLLM([
            ChatResponse(tool_calls=[_tool_call()]),
            ChatResponse(text="skill recovered"),
        ])
        return await execute_skill(
            skill,
            llm,
            _registry(),
            [{"role": "user", "content": "try a tool"}],
            {"user_message": "try a tool"},
            max_iters=1,
        )

    assert asyncio.run(run()) == "skill recovered"


def test_react_loop_failed_tool_recovery_budget_forces_text_finalization():
    async def run():
        failures = [
            ChatResponse(tool_calls=[_tool_call(call_id=f"call-{idx}")])
            for idx in range(MAX_FAILED_TOOL_RECOVERY_ITERS)
        ]
        llm = FakeLLM([*failures, ChatResponse(text="unused no-tool final")])
        output = await _react_loop(
            llm,
            [{"role": "user", "content": "keep trying"}],
            _registry(),
            max_iters=1,
        )
        return output, llm

    output, llm = asyncio.run(run())

    assert output.startswith(TOOL_FAILURE_BUDGET_MESSAGE)
    assert llm.chat_calls[-1]["tools"] is not None
    assert llm.stream_calls == []


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    raise SystemExit(1 if failures else 0)
