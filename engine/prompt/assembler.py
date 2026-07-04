from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from engine.skill.registry import SkillRegistry
    from engine.tool.registry import ToolRegistry


_SEPARATOR = "\n\n---\n\n"


class PromptAssembler:
    """Assemble an 11-layer system prompt from an employee directory."""

    def assemble(
        self,
        employee_dir: Path,
        tool_registry: "ToolRegistry",
        skill_registry: "SkillRegistry",
        context: dict,
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

        # Layer 10: memory
        memory_dir = employee_dir / "memory"
        mem_parts: list[str] = []

        # Read recent conversation memory
        recent_file = memory_dir / "recent.jsonl"
        if recent_file.is_file():
            import json
            lines = recent_file.read_text(encoding="utf-8").strip().splitlines()
            recent_entries = lines[-10:]  # Last 10 entries
            if recent_entries:
                mem_parts.append("## Recent Conversations")
                for line in recent_entries:
                    try:
                        entry = json.loads(line)
                        mem_parts.append(
                            f"- [{entry.get('timestamp', '?')}] "
                            f"{entry.get('task', '?')} → {entry.get('summary', '?')[:80]}"
                        )
                    except json.JSONDecodeError:
                        continue

        # Read stored memory entries
        if memory_dir.is_dir():
            md_files = sorted(memory_dir.glob("*.md"))
            if md_files:
                mem_parts.append("## Stored Memories")
                for f in md_files[:20]:  # Cap at 20 entries
                    content = f.read_text(encoding="utf-8").strip()
                    # Extract body (skip YAML frontmatter)
                    if content.startswith("---"):
                        parts = content.split("---", 2)
                        body = parts[2].strip() if len(parts) >= 3 else content
                    else:
                        body = content
                    # Truncate long entries
                    if len(body) > 150:
                        body = body[:150] + "..."
                    mem_parts.append(f"- {body}")

        if mem_parts:
            layers.append("\n".join(mem_parts))
        else:
            layers.append("")

        # Layer 11: runtime context
        if context:
            ctx_lines = ["## Runtime Context"]
            for k, v in context.items():
                ctx_lines.append(f"- {k}: {v}")
            layers.append("\n".join(ctx_lines))
        else:
            layers.append("")

        # Filter empty and join
        return _SEPARATOR.join(layer for layer in layers if layer.strip())

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
