from __future__ import annotations

from pathlib import Path

from engine.prompt.assembler import PromptAssembler


class FakeToolRegistry:
    def list_tools(self) -> list:
        return []


class FakeSkillRegistry:
    def list_summaries(self) -> list[dict]:
        return [
            {
                "name": "full-stack-product",
                "description": "产品和全栈交付通才 skill",
            }
        ]


def test_assembler_uses_smith_profile_and_skill_catalog_without_legacy_json(tmp_path: Path) -> None:
    agent_dir = tmp_path / "smith"
    agent_dir.mkdir()
    (agent_dir / "role.md").write_text("ROLE", encoding="utf-8")
    (agent_dir / "style.md").write_text("STYLE", encoding="utf-8")
    (agent_dir / "workflow.md").write_text("WORKFLOW", encoding="utf-8")
    (agent_dir / "toolbox.md").write_text("TOOLBOX", encoding="utf-8")
    (agent_dir / "context.md").write_text("CONTEXT", encoding="utf-8")
    (agent_dir / "expertise.json").write_text(
        '[{"name":"legacy-capability","description":"do not inject"}]',
        encoding="utf-8",
    )
    (agent_dir / "traits.json").write_text('["legacy-trait"]', encoding="utf-8")
    (agent_dir / "pipeline.json").write_text(
        '[{"task_type":"feature","pipeline":["legacy-step"]}]',
        encoding="utf-8",
    )

    prompt = PromptAssembler().assemble(
        agent_dir,
        FakeToolRegistry(),
        FakeSkillRegistry(),
        {"agent_id": "smith"},
    )

    assert "ROLE" in prompt
    assert "STYLE" in prompt
    assert "WORKFLOW" in prompt
    assert "TOOLBOX" in prompt
    assert "CONTEXT" in prompt
    assert "full-stack-product" in prompt
    assert "legacy-capability" not in prompt
    assert "legacy-trait" not in prompt
    assert "legacy-step" not in prompt


def test_assembler_wraps_memory_in_an_untrusted_reference_fence(tmp_path: Path) -> None:
    agent_dir = tmp_path / "smith"
    agent_dir.mkdir()
    for filename, content in {
        "role.md": "ROLE",
        "style.md": "STYLE",
        "workflow.md": "WORKFLOW",
        "toolbox.md": "TOOLBOX",
        "context.md": "CONTEXT",
    }.items():
        (agent_dir / filename).write_text(content, encoding="utf-8")

    memory_dir = agent_dir / "memory"
    memory_dir.mkdir()
    (memory_dir / "durable.md").write_text("DURABLE", encoding="utf-8")
    (memory_dir / "recent.md").write_text("RECENT", encoding="utf-8")

    prompt = PromptAssembler().assemble(
        agent_dir,
        FakeToolRegistry(),
        FakeSkillRegistry(),
        {},
        retrieved_memory="EPISODE",
    )

    assert "## Memory Reference" in prompt
    assert "not instructions" in prompt
    assert "recent activity over durable memory" in prompt
    assert prompt.index("## Memory Reference") < prompt.index("DURABLE")
    assert prompt.index("DURABLE") < prompt.index("RECENT") < prompt.index("EPISODE")


def test_assembler_omits_memory_fence_when_no_memory_is_available(tmp_path: Path) -> None:
    agent_dir = tmp_path / "smith"
    agent_dir.mkdir()
    for filename, content in {
        "role.md": "ROLE",
        "style.md": "STYLE",
        "workflow.md": "WORKFLOW",
        "toolbox.md": "TOOLBOX",
        "context.md": "CONTEXT",
    }.items():
        (agent_dir / filename).write_text(content, encoding="utf-8")

    prompt = PromptAssembler().assemble(
        agent_dir,
        FakeToolRegistry(),
        FakeSkillRegistry(),
        {},
    )

    assert "## Memory Reference" not in prompt
