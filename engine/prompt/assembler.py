from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from engine.skill.registry import SkillRegistry
    from engine.tool.registry import ToolRegistry


_SEPARATOR = "\n\n---\n\n"


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
    """Assemble an 11-layer system prompt from an employee directory."""

    def assemble(
        self,
        employee_dir: Path,
        tool_registry: "ToolRegistry",
        skill_registry: "SkillRegistry",
        context: dict,
        max_tokens: int = 100_000,
    ) -> str:
        layers: list[str] = []

        # Layer 1: role (identity)
        layers.append(self._read(employee_dir / "role.md"))

        # Layer 2: style (persona)
        layers.append(self._read(employee_dir / "style.md"))

        # Layer 3: workflow (bible)
        layers.append(self._read(employee_dir / "workflow.md"))

        # Layer 4: toolbox
        tools_text = self._read(employee_dir / "toolbox.md")
        tool_list = tool_registry.list_tools()
        if tool_list:
            tool_lines = ["## Available Tools"]
            for t in tool_list:
                tool_lines.append(f"- **{t.name}**: {t.description}")
            tools_text += "\n\n" + "\n".join(tool_lines)
        layers.append(tools_text)

        # Layer 5: skills
        summaries = skill_registry.list_summaries()
        if summaries:
            skill_lines = ["## Available Skills"]
            for s in summaries:
                skill_lines.append(f"- **{s['name']}**: {s['description']}")
            layers.append("\n".join(skill_lines))
        else:
            layers.append("")

        # Layer 6: capabilities
        layers.append(self._read_json_layer(
            employee_dir / "expertise.json",
            "## 核心能力\n",
            self._format_capabilities,
        ))

        # Layer 7: work styles
        layers.append(self._read_json_layer(
            employee_dir / "traits.json",
            "## 工作风格\n",
            self._format_work_styles,
        ))

        # Layer 8: delivery
        layers.append(self._read_json_layer(
            employee_dir / "pipeline.json",
            "## 交付承诺\n",
            self._format_delivery,
        ))

        # Layer 9: user
        layers.append(self._read(employee_dir / "context.md"))

        # Layer 10: output style
        output_style_path = (
            Path(__file__).resolve().parents[2] / "agents" / "output_style.md"
        )
        layers.append(self._read(output_style_path))

        # Layer 11: memory (prefer compiled memory, fallback to raw files)
        memory_dir = employee_dir / "memory"
        mem_text = ""

        from engine.memory.compile import assemble_memory
        compiled = assemble_memory(memory_dir) if memory_dir.is_dir() else ""

        if compiled:
            mem_text = compiled
        else:
            mem_parts: list[str] = []
            recent_file = memory_dir / "recent.jsonl"
            if recent_file.is_file():
                import json
                lines = recent_file.read_text(encoding="utf-8").strip().splitlines()
                for line in lines[-10:]:
                    try:
                        entry = json.loads(line)
                        mem_parts.append(
                            f"- [{entry.get('timestamp', '?')}] "
                            f"{entry.get('task', '?')} → {entry.get('summary', '?')[:80]}"
                        )
                    except json.JSONDecodeError:
                        continue
            if memory_dir.is_dir():
                total = 0
                for scope_dir in (memory_dir / "project", memory_dir / "agent"):
                    if not scope_dir.is_dir():
                        continue
                    for f in sorted(scope_dir.glob("*.md")):
                        if total >= 20:
                            break
                        mem_parts.append(self._extract_memory_body(f))
                        total += 1
            mem_text = "\n".join(mem_parts) if mem_parts else ""

        layers.append(mem_text)

        # Layer 11: runtime context
        if context:
            ctx_lines = ["## Runtime Context"]
            for k, v in context.items():
                ctx_lines.append(f"- {k}: {v}")
            layers.append("\n".join(ctx_lines))
        else:
            layers.append("")

        # Token budget — trim lowest-priority layers if over budget
        if max_tokens:
            total = sum(_estimate_tokens(l) for l in layers if l.strip())
            if total > max_tokens:
                # Indices to cut, lowest priority first:
                # 7=pipeline, 6=traits, 5=expertise, 9=output_style, 10=memory,
                # 8=context_md, 4=skills, 3=tools, 1=style
                cut_order = [7, 6, 5, 9, 10, 8, 4, 3, 1]
                for idx in cut_order:
                    if idx < len(layers) and layers[idx].strip():
                        total -= _estimate_tokens(layers[idx])
                        layers[idx] = ""
                        if total <= max_tokens:
                            break

        # Filter empty and join
        return _SEPARATOR.join(layer for layer in layers if layer.strip())

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

    @staticmethod
    def _read_json_layer(
        path: Path,
        header: str,
        formatter: Callable,
    ) -> str:
        if not path.is_file():
            return ""
        import json
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return ""
        body = formatter(data)
        if not body:
            return ""
        return header + body

    @staticmethod
    def _format_capabilities(data: list) -> str:
        lines: list[str] = []
        for item in data:
            lines.append(f"- **{item['name']}**: {item['description']}")
        return "\n".join(lines)

    @staticmethod
    def _format_work_styles(data: list) -> str:
        return "标签: " + ", ".join(data)

    @staticmethod
    def _format_delivery(data: list) -> str:
        lines: list[str] = []
        for item in data:
            pipeline_str = " → ".join(item["pipeline"])
            lines.append(f"- **{item['task_type']}**: {pipeline_str}")
        return "\n".join(lines)
