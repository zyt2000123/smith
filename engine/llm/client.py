from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import AsyncGenerator

import httpx


@dataclass
class ToolCallData:
    id: str
    name: str
    arguments: dict


@dataclass
class ChatResponse:
    text: str = ""
    reasoning: str = ""  # 思考模型的 reasoning_content（如 GLM/DeepSeek）
    tool_calls: list[ToolCallData] = field(default_factory=list)
    usage: dict | None = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class LLMClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        stream: bool = True,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.stream = stream
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(300.0, connect=10.0),
        )

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        prefix_cache_key: str | None = None,
    ) -> ChatResponse:
        body: dict = {"model": self.model, "messages": messages, "stream": False}
        if tools:
            body["tools"] = tools
        if prefix_cache_key:
            body["extra_body"] = {"prefix_cache_key": prefix_cache_key}

        data = await self._request(body)
        choice = data["choices"][0]["message"]

        tc_list: list[ToolCallData] = []
        for tc in choice.get("tool_calls") or []:
            args = tc["function"].get("arguments", "{}")
            tc_list.append(ToolCallData(
                id=tc["id"],
                name=tc["function"]["name"],
                arguments=json.loads(args) if isinstance(args, str) else args,
            ))

        return ChatResponse(
            text=choice.get("content") or "",
            reasoning=choice.get("reasoning_content") or "",
            tool_calls=tc_list,
            usage=data.get("usage"),
        )

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AsyncGenerator[str, None]:
        body: dict = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            body["tools"] = tools

        req = self._http.build_request("POST", "/chat/completions", json=body)
        resp = await self._http.send(req, stream=True)
        try:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    break
                chunk = json.loads(payload)
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                if text := delta.get("content"):
                    yield text
        finally:
            await resp.aclose()

    async def _request(self, body: dict, _attempt: int = 0) -> dict:
        max_retries = 3
        try:
            resp = await self._http.post("/chat/completions", json=body)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400:
                import logging
                logging.getLogger("llm").error("400 response: %s", exc.response.text[:500])
            if _attempt < max_retries - 1:
                return await self._request(body, _attempt + 1)
            raise RuntimeError(f"LLM request failed after {max_retries} attempts: {exc}") from exc
        except httpx.TransportError as exc:
            if _attempt < max_retries - 1:
                return await self._request(body, _attempt + 1)
            raise RuntimeError(f"LLM request failed after {max_retries} attempts: {exc}") from exc

    async def close(self) -> None:
        await self._http.aclose()
