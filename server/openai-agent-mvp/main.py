"""
OpenAI Agent SDK 最小 MVP 实战 —— 本地文件助手

演示核心机制：
  - Agent 定义（instructions + tools）
  - @function_tool 装饰器注册工具
  - Runner.run() 驱动 ReAct 循环
  - 工具调用 → 结果反馈 → 继续推理

使用方法：
  1. 设置 OPENAI_API_KEY 环境变量（或用 .env 文件）
  2. python main.py
  3. 输入自然语言问题，例如：
     - "帮我看看当前目录有哪些文件"
     - "读取 pyproject.toml 的内容并总结"
     - "在当前目录下搜索包含 'Agent' 的 Python 文件"
"""

import os
from pathlib import Path
from dotenv import load_dotenv

from agents import Agent, Runner, function_tool, RunConfig

load_dotenv()

# ── 工具定义 ──────────────────────────────────────────


@function_tool
def list_current_dir() -> str:
    """列出当前工作目录下的所有文件和子目录（仅名称）。"""
    cwd = Path.cwd()
    items = sorted(cwd.iterdir())
    lines = [f"  {'[DIR] ' if x.is_dir() else '[FILE]'} {x.name}" for x in items]
    return f"当前目录: {cwd}\n" + "\n".join(lines)


@function_tool
def read_file(path: str) -> str:
    """读取指定文件的内容。path 可以是相对路径或绝对路径。"""
    p = Path(path)
    if not p.exists():
        return f"错误：文件不存在 —— {p}"
    if p.is_dir():
        return f"错误：{p} 是目录，不是文件"
    try:
        content = p.read_text(encoding="utf-8")
        if len(content) > 4000:
            content = content[:4000] + "\n... [内容过长，已截断]"
        return content
    except Exception as e:
        return f"读取失败: {e}"


@function_tool
def search_in_files(pattern: str, directory: str = ".") -> str:
    """在指定目录下的所有文本文件中搜索匹配 pattern 的内容。
    返回匹配的文件名和行。"""
    import subprocess
    try:
        result = subprocess.run(
            ["grep", "-rn", "--include=*.py", "--include=*.toml",
             "--include=*.md", "--include=*.txt", "--include=*.yaml", "--include=*.yml",
             pattern, directory],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 1:
            return f"在 {directory} 下未找到匹配 '{pattern}' 的内容"
        output = result.stdout.strip()
        if len(output) > 3000:
            output = output[:3000] + "\n... [结果过多，已截断]"
        return output or "无匹配结果"
    except FileNotFoundError:
        return "grep 不可用"
    except Exception as e:
        return f"搜索出错: {e}"


# ── Agent 定义 ──────────────────────────────────────────

agent = Agent(
    name="本地文件助手",
    instructions=(
        "你是一个运行在本地的文件助手。你可以：\n"
        "1. 列出当前目录的文件 (list_current_dir)\n"
        "2. 读取文件内容 (read_file)\n"
        "3. 搜索文件内容 (search_in_files)\n\n"
        "回答规则：\n"
        "- 先用工具获取真实信息，再回答，不要凭空猜测。\n"
        "- 如果用户让你做你无法做到的事，诚实说明。\n"
        "- 回复简洁，用中文。"
    ),
    tools=[list_current_dir, read_file, search_in_files],
)


# ── 主入口 ──────────────────────────────────────────────

async def main():
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")

    # 自定义 provider 支持：显式配置 AsyncOpenAI 客户端
    if base_url:
        from openai import AsyncOpenAI
        from agents import set_default_openai_client
        client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or "not-needed",
        )
        set_default_openai_client(client)
        print(f"[配置] 使用自定义 API: {base_url}")
    elif not api_key:
        print("[警告] 未设置 OPENAI_API_KEY 和 OPENAI_BASE_URL，可能无法连接 API。")

    print("=" * 50)
    print("  OpenAI Agent SDK MVP — 本地文件助手")
    print("  输入问题，输入 'quit' 退出")
    print("=" * 50)

    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    run_config = RunConfig(model=model)
    print(f"[配置] 模型: {model}")

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n退出。")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("退出。")
            break

        print("思考中...", end="\r")
        try:
            result = await Runner.run(
                starting_agent=agent,
                input=user_input,
                run_config=run_config,
            )
            print(" " * 20, end="\r")  # 清除"思考中"
            print(result.final_output)
        except Exception as e:
            print(f"[错误] {e}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
