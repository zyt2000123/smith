from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import HTTPException

from engine.execution.agent_loop import (
    reply_events_with_runtime as engine_reply_events_with_runtime,
    reply_with_runtime as engine_reply_with_runtime,
)
from engine.execution.runtime import EngineRequest

from ..schemas.session import SessionOut, MessageOut
from ..infrastructure.repositories.session_repo import SessionRepo
from ..infrastructure.repositories.agent_profile_repo import AgentProfileRepo
from .engine_runtime import build_engine_runtime

# Recent messages passed to the engine as short-term conversational context
_HISTORY_LIMIT = 10


class SessionService:

    def __init__(self, session_repo: SessionRepo, agent_profile_repo: AgentProfileRepo) -> None:
        self.session_repo = session_repo
        self.agent_profile_repo = agent_profile_repo

    async def list_sessions(self, agent_id: str) -> list[SessionOut]:
        rows = await self.session_repo.list_by_agent(agent_id)
        return [SessionOut(**r) for r in rows]

    async def create_session(self, agent_id: str, title: str) -> SessionOut:
        emp = await self.agent_profile_repo.get(agent_id)
        if emp is None:
            raise HTTPException(404, "Agent profile not found")
        row = await self.session_repo.create(agent_id, title or "新对话")
        return SessionOut(**row)

    async def _recent_history(self, session_id: str) -> list[dict]:
        """Last N messages as {"role","content"} dicts for engine short-term context."""
        rows = await self.session_repo.get_messages(session_id)
        return [
            {"role": r["role"], "content": r["content"]}
            for r in rows[-_HISTORY_LIMIT:]
        ]

    async def list_messages(self, session_id: str, limit: int = 0, offset: int = 0) -> list[MessageOut]:
        rows = await self.session_repo.get_messages(session_id, limit=limit, offset=offset)
        return [MessageOut(**r) for r in rows]

    async def send_message(
        self,
        agent_id: str,
        session_id: str,
        content: str,
        context: str | None = None,
        skill_name: str | None = None,
    ) -> MessageOut:
        if not await self.session_repo.exists(session_id, agent_id):
            raise HTTPException(404, "Session not found")

        emp = await self.agent_profile_repo.get(agent_id)
        emp_name = emp["name"] if emp else "Agent"

        # Fetch recent history BEFORE saving the new message (avoids duplication)
        history = await self._recent_history(session_id)

        # Save user message
        await self.session_repo.add_message(session_id, "user", content)

        # Call engine
        # context（工作目录/附件路径）由引擎侧拼接：LLM 可见，路由/记忆/落库均只用原文
        runtime, services = build_engine_runtime(agent_id, emp_name, session_id=session_id)
        result = await engine_reply_with_runtime(
            EngineRequest(
                message=content,
                history=history,
                context=context,
                forced_skill=skill_name,
            ),
            runtime,
            services,
        )
        reply_text = result.text

        # Save assistant message
        msg = await self.session_repo.add_message(session_id, "assistant", reply_text)
        return MessageOut(**msg)

    async def stream_message(
        self,
        agent_id: str,
        session_id: str,
        content: str,
        context: str | None = None,
        skill_name: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Yield SSE event dicts. Streams text chunks as they arrive from the engine."""
        if not await self.session_repo.exists(session_id, agent_id):
            raise HTTPException(404, "Session not found")

        emp = await self.agent_profile_repo.get(agent_id)
        emp_name = emp["name"] if emp else "Agent"

        # Fetch recent history BEFORE saving the new message (avoids duplication)
        history = await self._recent_history(session_id)

        # Save user message
        await self.session_repo.add_message(session_id, "user", content)

        # Stream structured events from engine
        def sse(event: str, data: dict) -> dict:
            return {"event": event, "data": json.dumps(data, ensure_ascii=False)}

        full_reply = []
        msg: dict | None = None
        runtime, services = build_engine_runtime(agent_id, emp_name, session_id=session_id)
        try:
            async for ev in engine_reply_events_with_runtime(
                EngineRequest(
                    message=content,
                    history=history,
                    context=context,
                    forced_skill=skill_name,
                ),
                runtime,
                services,
            ):
                t = ev.type.value
                if t == "text_delta":
                    chunk = ev.data.get("text", "")
                    full_reply.append(chunk)
                    yield sse("message", {"text": chunk})
                elif t == "thinking":
                    yield sse("thinking", {"text": ev.data.get("text", ""), "done": bool(ev.data.get("done"))})
                elif t == "tool_call_start":
                    args = ev.data.get("arguments") or {}
                    hint = args.get("path") or args.get("file_path") or args.get("query") or args.get("command", "")
                    yield sse("tool_call", {"id": ev.data.get("id", ""), "name": ev.data.get("name", ""), "hint": str(hint)[:120]})
                elif t == "tool_call_result":
                    yield sse("tool_result", {
                        "id": ev.data.get("id", ""),
                        "error": bool(ev.data.get("error") or ev.data.get("blocked")),
                        "blocked": bool(ev.data.get("blocked")),
                        "preflight": bool(ev.data.get("preflight")),
                        "summary": ev.data.get("reason") or ev.data.get("content", "")[:120],
                    })
                elif t in ("skill_start", "skill_end"):
                    yield sse("skill", {"name": ev.data.get("skill", ""), "status": "start" if t == "skill_start" else ev.data.get("status", "end")})
                elif t == "blocked":
                    yield sse("message", {"text": f"\n⛔ 已阻断：{ev.data.get('reason', '')}\n"})
                elif t == "token_usage":
                    yield sse("token_usage", {
                        "input_tokens": ev.data.get("input_tokens", 0),
                        "output_tokens": ev.data.get("output_tokens", 0),
                        "total_tokens": ev.data.get("total_tokens", 0),
                    })
                # route_decided / gate_result / backtrack / done：前端暂不展示，跳过
        finally:
            # 客户端断连/引擎异常时生成器在 yield 处被终止，async for 之后的代码不会执行；
            # 落库放 finally 并用 shield 保护，请求被取消也能保住已生成的部分回复。
            reply_text = "".join(full_reply)
            if reply_text:
                msg = await asyncio.shield(
                    self.session_repo.add_message(session_id, "assistant", reply_text)
                )

        yield {"event": "done", "data": json.dumps({"id": msg["id"] if msg else None}, ensure_ascii=False)}
