"""AgentScope runtime — wraps Agent + Model + Toolkit for employee task execution."""
import os
import asyncio
from typing import AsyncGenerator

from agentscope.agent import Agent, ReActConfig
from agentscope.model import OpenAIChatModel
from agentscope.credential import OpenAICredential
from agentscope.tool import Toolkit, FunctionTool, ToolChunk
from agentscope.message import UserMsg, Msg
from agentscope.event import AgentEvent

_agents: dict[str, Agent] = {}


def _extract_text(msg: Msg) -> str:
    """Extract plain text from Msg whose content is list[TextBlock]."""
    if isinstance(msg.content, str):
        return msg.content
    if isinstance(msg.content, list):
        return "\n".join(getattr(b, "text", str(b)) for b in msg.content if getattr(b, "text", None))
    return str(msg.content)


def _build_model() -> OpenAIChatModel | None:
    """Build LLM model from env vars. Returns None if no API key configured."""
    api_key = os.environ.get("AGENTSMITH_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    base_url = os.environ.get("AGENTSMITH_LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    model_name = os.environ.get("AGENTSMITH_LLM_MODEL", "gpt-4o-mini")

    cred = OpenAICredential(id="default", api_key=api_key, base_url=base_url)
    return OpenAIChatModel(credential=cred, model=model_name, stream=True)


# ponytail: one mock tool for now, real tools (file read, shell, browser) added when needed
async def _search_knowledge(query: str) -> ToolChunk:
    """搜索团队知识库中的相关信息。"""
    return ToolChunk(
        text=f"[知识库 mock] 未找到与「{query}」相关的结果。请连接 Hub 后重试。",
        is_final=True,
    )

async def _read_file(path: str) -> ToolChunk:
    """读取指定路径的文件内容。"""
    from pathlib import Path
    p = Path(path).expanduser()
    if not p.exists():
        return ToolChunk(text=f"文件不存在: {path}", is_final=True)
    if not p.is_file():
        return ToolChunk(text=f"不是文件: {path}", is_final=True)
    content = p.read_text(encoding="utf-8", errors="replace")[:10000]
    return ToolChunk(text=content, is_final=True)


def _build_toolkit() -> Toolkit:
    tools = [
        FunctionTool(func=_search_knowledge, name="search_knowledge",
                     description="搜索团队知识库", is_read_only=True),
        FunctionTool(func=_read_file, name="read_file",
                     description="读取本地文件内容", is_read_only=True),
    ]
    return Toolkit(tools=tools)


def get_or_create_agent(employee_id: str, name: str, system_prompt: str) -> Agent | None:
    """Get cached agent or create a new one. Returns None if no LLM configured."""
    if employee_id in _agents:
        return _agents[employee_id]

    model = _build_model()
    if model is None:
        return None

    agent = Agent(
        name=name,
        system_prompt=system_prompt,
        model=model,
        toolkit=_build_toolkit(),
        react_config=ReActConfig(max_iters=10),
    )
    _agents[employee_id] = agent
    return agent


async def run_agent_reply(employee_id: str, name: str, system_prompt: str,
                          user_message: str) -> str:
    """Run agent and return final reply text. Falls back to mock if no LLM."""
    agent = get_or_create_agent(employee_id, name, system_prompt)
    if agent is None:
        return (f"收到任务：「{user_message}」。\n\n"
                "⚠️ 当前未配置 LLM API Key，使用 mock 回复。\n"
                "请设置环境变量 AGENTSMITH_LLM_API_KEY 后重启服务。")

    user_msg = UserMsg(name="user", content=user_message)
    reply: Msg = await agent.reply(user_msg)
    return _extract_text(reply)


async def stream_agent_reply(employee_id: str, name: str, system_prompt: str,
                             user_message: str) -> AsyncGenerator[str, None]:
    """Stream agent reply via _reply generator. Falls back to mock if no LLM."""
    agent = get_or_create_agent(employee_id, name, system_prompt)
    if agent is None:
        yield (f"收到任务：「{user_message}」。\n\n"
               "⚠️ 当前未配置 LLM API Key，使用 mock 回复。\n"
               "请设置环境变量 AGENTSMITH_LLM_API_KEY 后重启服务。")
        return

    user_msg = UserMsg(name="user", content=user_message)
    async for evt_or_msg in agent._reply(user_msg):
        if isinstance(evt_or_msg, Msg):
            yield _extract_text(evt_or_msg)
        elif isinstance(evt_or_msg, AgentEvent):
            # ponytail: yield event type as SSE metadata when SSE is wired up
            pass


def clear_agent(employee_id: str):
    """Remove cached agent (e.g. when employee config changes)."""
    _agents.pop(employee_id, None)
