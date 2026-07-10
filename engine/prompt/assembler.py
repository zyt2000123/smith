from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.skill.registry import SkillRegistry
    from engine.tool.registry import ToolRegistry


_SEPARATOR = "\n\n---\n\n"

# Cache: agent_dir -> (content_hash, assembled_prompt)
_prompt_cache: dict[str, tuple[str, str]] = {}


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English, ~2 for CJK."""
    return max(len(text) // 3, 1)


def build_team_context(
    group_name: str,
    members: list[str],
    recent_messages: list[dict],
) -> str:
    """Build a context block for team conversations."""
    lines: list[str] = [
        "## Team Context",
        f'You are in team group "{group_name}" with members: {", ".join(members)}.',
        "",
        "Recent conversation:",
    ]
    for msg in recent_messages:
        name = msg.get("sender_name") or msg.get("sender_id", "?")
        content = msg.get("content", "")
        lines.append(f"[{name}]: {content}")
    return "\n".join(lines)


class PromptAssembler:
    """Assemble Smith's system prompt from an agent profile directory."""

    def assemble(
        self,
        agent_dir: Path,
        tool_registry: "ToolRegistry",
        skill_registry: "SkillRegistry",
        context: dict,
        max_tokens: int = 100_000,
        retrieved_memory: str = "",
    ) -> str:
        layers: list[str] = []

        # Layer 1: role (identity)
        layers.append(self._read(agent_dir / "role.md"))

        # Layer 2: style (persona)
        layers.append(self._read(agent_dir / "style.md"))

        # Layer 3: workflow (bible)
        layers.append(self._read(agent_dir / "workflow.md"))

        # Layer 4: toolbox
        tools_text = self._read(agent_dir / "toolbox.md")
        tool_list = tool_registry.list_tools()
        if tool_list:
            tool_lines = ["## Available Tools"]
            for t in tool_list:
                tool_lines.append(f"- **{t.name}**: {t.description}")
            tools_text += "\n\n" + "\n".join(tool_lines)
        layers.append(tools_text)

        # Layer 5: skill catalog (metadata only; skill bodies load on demand)
        summaries = skill_registry.list_summaries()
        if summaries:
            skill_lines = ["## Available Skills"]
            for s in summaries:
                skill_lines.append(f"- **{s['name']}**: {s['description']}")
            layers.append("\n".join(skill_lines))
        else:
            layers.append("")

        # Layer 6: user context
        layers.append(self._read(agent_dir / "context.md"))

        # Layer 7: output style
        output_style_path = (
            Path(__file__).resolve().parents[2] / "agents" / "output_style.md"
        )
        layers.append(self._read(output_style_path))

        # Layer 8: memory (durable + recent compiled, plus query-time retrieval)
        memory_dir = agent_dir / "memory"

        from engine.memory.compile import assemble_memory
        mem_text = assemble_memory(memory_dir) if memory_dir.is_dir() else ""

        if retrieved_memory:
            mem_text = (mem_text + "\n\n" if mem_text else "") + retrieved_memory

        layers.append(mem_text)

        # Layer 9: runtime context
        if context:
            ctx_lines = ["## Runtime Context"]
            for k, v in context.items():
                ctx_lines.append(f"- {k}: {v}")
            layers.append("\n".join(ctx_lines))
        else:
            layers.append("")

        # Compute hash of stable layers (1-5: role, style, workflow, tools, skills)
        # These rarely change between calls for the same agent
        stable_content = _SEPARATOR.join(layers[:5])
        stable_hash = hashlib.md5(stable_content.encode()).hexdigest()
        cache_key = str(agent_dir)

        cached = _prompt_cache.get(cache_key)
        if cached and cached[0] == stable_hash:
            # Stable layers unchanged — rebuild only dynamic layers (6+)
            # But since we already have them in `layers`, just skip re-reading
            pass  # layers are already built, this validates cache coherence

        # Store for next call
        # The real win: when LLM providers support prefix caching,
        # we pass this hash as a cache hint
        _prompt_cache[cache_key] = (stable_hash, stable_content)

        # Token budget — trim lowest-priority layers if over budget
        if max_tokens:
            total = sum(_estimate_tokens(l) for l in layers if l.strip())
            if total > max_tokens:
                # Indices to cut, lowest priority first:
                # 6=output_style, 7=memory, 5=context_md, 4=skills, 3=tools, 1=style
                cut_order = [6, 7, 5, 4, 3, 1]
                for idx in cut_order:
                    if idx < len(layers) and layers[idx].strip():
                        total -= _estimate_tokens(layers[idx])
                        layers[idx] = ""
                        if total <= max_tokens:
                            break

        # Filter empty and join
        return _SEPARATOR.join(layer for layer in layers if layer.strip())

    @staticmethod
    def get_prefix_cache_key(agent_dir: Path) -> str | None:
        """Return the hash of stable prompt layers for LLM prefix caching."""
        cached = _prompt_cache.get(str(agent_dir))
        return cached[0] if cached else None

    @staticmethod
    def _extract_memory_body(f: Path) -> str:
        """Read a memory .md file and return a truncated body line."""
        content = f.read_text(encoding="utf-8").strip()
        if content.startswith("---"):
            parts = content.split("---", 2)
            body = parts[2].strip() if len(parts) >= 3 else content
        else:
            body = content
        if len(body) > 150:
            body = body[:150] + "..."
        return f"- {body}"

    @staticmethod
    def _read(path: Path) -> str:
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
        return ""
