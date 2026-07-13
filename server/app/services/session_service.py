from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import HTTPException

from engine.execution.agent_loop import (
    run_stream_with_runtime as engine_run_stream_with_runtime,
    reply_with_runtime as engine_reply_with_runtime,
)
from engine.execution.runtime import EngineRequest
from engine.identity_catalog import IdentityCatalog, IdentityCatalogError

from ..schemas.session import SessionOut, MessageOut
from ..infrastructure.repositories.session_repo import SessionRepo
from ..infrastructure.repositories.agent_profile_repo import AgentProfileRepo
from .engine_runtime import build_engine_runtime

# Recent messages passed to the engine as short-term conversational context
_HISTORY_LIMIT = 10
logger = logging.getLogger(__name__)


class SessionService:

    def __init__(
        self,
        session_repo: SessionRepo,
        agent_profile_repo: AgentProfileRepo,
        *,
        identity_catalog: IdentityCatalog | None = None,
    ) -> None:
        self.session_repo = session_repo
        self.agent_profile_repo = agent_profile_repo
        self.identity_catalog = identity_catalog

    async def list_sessions(self, agent_id: str) -> list[SessionOut]:
        rows = await self.session_repo.list_by_agent(agent_id)
        return [SessionOut(**r) for r in rows]

    def _catalog(self) -> IdentityCatalog:
        if self.identity_catalog is not None:
            return self.identity_catalog
        from .engine_runtime import load_runtime_identity_catalog

        return load_runtime_identity_catalog()

    def _validate_identity(self, identity_id: str) -> None:
        try:
            self._catalog().get(identity_id)
        except IdentityCatalogError as exc:
            raise HTTPException(422, str(exc)) from exc

    async def create_session(
        self,
        agent_id: str,
        title: str,
        identity_id: str | None = None,
    ) -> SessionOut:
        profile = await self.agent_profile_repo.get(agent_id)
        if profile is None:
            raise HTTPException(404, "Agent profile not found")
        if identity_id is not None:
            self._validate_identity(identity_id)
        row = await self.session_repo.create(agent_id, title or "新对话", identity_id)
        return SessionOut(**row)

    async def _resolve_session_identity(
        self,
        agent_id: str,
        session_id: str,
        content: str,
        requested_identity_id: str | None,
    ) -> str:
        session = await self.session_repo.get_owned(session_id, agent_id)
        if session is None:
            raise HTTPException(404, "Session not found")

        pinned_identity_id = session.get("identity_id")
        if requested_identity_id is not None:
            self._validate_identity(requested_identity_id)
            if pinned_identity_id and pinned_identity_id != requested_identity_id:
                raise HTTPException(
                    409,
                    "This session is already bound to a different identity. Create a new session to switch identity.",
                )
            selected_identity_id = requested_identity_id
        elif pinned_identity_id:
            selected_identity_id = str(pinned_identity_id)
            self._validate_identity(selected_identity_id)
        else:
            selected_identity_id = self._catalog().resolve(content).identity_id

        if not pinned_identity_id:
            claimed = await self.session_repo.claim_identity(
                session_id,
                agent_id,
                selected_identity_id,
            )
            if not claimed:
                # A concurrent first message won the race; use its stable binding.
                concurrent_session = await self.session_repo.get_owned(session_id, agent_id)
                if concurrent_session is None or not concurrent_session.get("identity_id"):
                    raise HTTPException(409, "Unable to establish a stable session identity")
                selected_identity_id = str(concurrent_session["identity_id"])
                self._validate_identity(selected_identity_id)
                if requested_identity_id is not None and selected_identity_id != requested_identity_id:
                    raise HTTPException(
                        409,
                        "This session was bound to a different identity by another request.",
                    )

        return selected_identity_id

    async def _recent_history(self, session_id: str) -> list[dict]:
        """Last N messages as {"role","content"} dicts for engine short-term context."""
        rows = await self.session_repo.get_recent_messages(session_id, _HISTORY_LIMIT)
        return [
            {"role": r["role"], "content": r["content"]}
            for r in rows
        ]

    async def list_messages(self, session_id: str, limit: int = 0, offset: int = 0) -> list[MessageOut]:
        exists = await self.session_repo.exists_by_id(session_id)
        if not exists:
            raise HTTPException(404, "Session not found")
        rows = await self.session_repo.get_messages(session_id, limit=limit, offset=offset)
        return [MessageOut(**r) for r in rows]

    async def send_message(
        self,
        agent_id: str,
        session_id: str,
        content: str,
        context: str | None = None,
        skill_name: str | None = None,
        identity_id: str | None = None,
        working_dir: str | None = None,
    ) -> MessageOut:
        selected_identity_id = await self._resolve_session_identity(
            agent_id,
            session_id,
            content,
            identity_id,
        )

        profile = await self.agent_profile_repo.get(agent_id)
        profile_name = profile["name"] if profile else "Agent"

        # Fetch recent history BEFORE saving the new message (avoids duplication)
        history = await self._recent_history(session_id)

        # Save user message
        await self.session_repo.add_message(session_id, "user", content)

        try:
            runtime, services = build_engine_runtime(agent_id, profile_name, session_id=session_id)
            result = await engine_reply_with_runtime(
                EngineRequest(
                    message=content,
                    history=history,
                    context=context,
                    forced_skill=skill_name,
                    identity_id=selected_identity_id,
                    working_dir=working_dir,
                ),
                runtime,
                services,
            )
            reply_text = result.text
        except Exception:
            logger.exception("send_message engine call failed (session=%s)", session_id)
            reply_text = "执行失败（详情见服务端日志）"

        msg = await self.session_repo.add_message(session_id, "assistant", reply_text)
        return MessageOut(**msg)

    async def stream_message(
        self,
        agent_id: str,
        session_id: str,
        content: str,
        context: str | None = None,
        skill_name: str | None = None,
        identity_id: str | None = None,
        working_dir: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Yield SSE event dicts. Streams text chunks as they arrive from the engine."""
        selected_identity_id = await self._resolve_session_identity(
            agent_id,
            session_id,
            content,
            identity_id,
        )

        profile = await self.agent_profile_repo.get(agent_id)
        profile_name = profile["name"] if profile else "Agent"

        # Fetch recent history BEFORE saving the new message (avoids duplication)
        history = await self._recent_history(session_id)

        # Save user message
        await self.session_repo.add_message(session_id, "user", content)

        # Stream structured events from engine
        def sse(event: str, data: dict) -> dict:
            return {"event": event, "data": json.dumps(data, ensure_ascii=False)}

        full_reply: list[str] = []
        msg: dict | None = None
        run_id: str | None = None
        terminal_status = "completed"
        terminal_notice: str | None = None
        try:
            runtime, services = build_engine_runtime(agent_id, profile_name, session_id=session_id)
            run = engine_run_stream_with_runtime(
                EngineRequest(
                    message=content,
                    history=history,
                    context=context,
                    forced_skill=skill_name,
                    identity_id=selected_identity_id,
                    working_dir=working_dir,
                ),
                runtime,
                services,
            )
            run_id = getattr(run, "run_id", None)
            async for ev in run.stream_events():
                t = ev.type.value
                if t == "run_started":
                    run_id = str(ev.data.get("run_id") or run_id or "") or None
                    yield sse("run_started", {"run_id": run_id})
                elif t == "raw_response_event":
                    raw_type = ev.data.get("type")
                    raw_data = ev.data.get("data")
                    if (
                        raw_type == "response.output_text.delta"
                        and not ev.data.get("provision_id")
                        and isinstance(raw_data, dict)
                    ):
                        delta = raw_data.get("delta")
                        if isinstance(delta, str) and delta:
                            yield sse("message", {"text": delta})
                elif t == "provisional_text_delta":
                    provision_id = str(ev.data.get("provision_id", ""))
                    text = ev.data.get("text")
                    if provision_id and isinstance(text, str) and text:
                        yield sse("provisional_text_delta", {
                            "provision_id": provision_id,
                            "text": text,
                        })
                elif t == "provisional_commit":
                    provision_id = str(ev.data.get("provision_id", ""))
                    if provision_id:
                        yield sse("provisional_commit", {"provision_id": provision_id})
                elif t == "provisional_retract":
                    provision_id = str(ev.data.get("provision_id", ""))
                    if provision_id:
                        payload = {"provision_id": provision_id}
                        reason = ev.data.get("reason")
                        if isinstance(reason, str) and reason:
                            payload["reason"] = reason
                        yield sse("provisional_retract", payload)
                elif t == "text_delta":
                    chunk = ev.data.get("text", "")
                    full_reply.append(chunk)
                    if not ev.data.get("already_streamed"):
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
                elif t == "incomplete":
                    terminal_status = "incomplete"
                elif t == "failed":
                    terminal_status = "failed"
                elif t == "run_finished":
                    status = ev.data.get("status")
                    if status in ("completed", "incomplete", "failed"):
                        terminal_status = status
                # route_decided / gate_result / backtrack / done / run_started：前端暂不展示，跳过
        except Exception:
            logger.exception("agent SSE execution failed (session=%s)", session_id)
            terminal_status = "failed"
            terminal_notice = "执行失败（详情见服务端日志）"
        finally:
            # 客户端断连/引擎异常时生成器在 yield 处被终止，async for 之后的代码不会执行；
            # 落库放 finally 并用 shield 保护，请求被取消也能保住已生成的部分回复。
            reply_text = "".join(full_reply)
            if reply_text:
                try:
                    msg = await asyncio.shield(
                        self.session_repo.add_message(session_id, "assistant", reply_text)
                    )
                except Exception:
                    logger.exception("failed to persist streamed reply (session=%s)", session_id)
                    terminal_status = "failed"
                    terminal_notice = "回复保存失败（详情见服务端日志）"

        if terminal_notice:
            yield sse("message", {"text": f"\n⚠️ {terminal_notice}\n"})
        done_payload = {
            "id": msg["id"] if msg else None,
            "status": terminal_status,
        }
        if run_id is not None:
            done_payload["run_id"] = run_id
        yield sse("done", done_payload)
