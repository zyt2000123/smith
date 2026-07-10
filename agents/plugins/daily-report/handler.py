"""Daily report plugin — 每日工作报告自动生成。

每天 18:00 触发，从当日对话记忆中汇总生成结构化日报。
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)


async def handle(event: dict) -> None:
    """Entry point called by the plugin trigger.

    ``event`` must contain ``agent_dir`` (Path or str) pointing to the
    agent's data directory (the on-disk agent profile dir).
    """
    agent_dir = Path(event.get("agent_dir", ""))
    if not agent_dir.is_dir():
        log.warning("daily-report: agent_dir not found: %s", agent_dir)
        return

    today = date.today().isoformat()
    recent_file = agent_dir / "memory" / "recent.jsonl"
    if not recent_file.exists():
        log.info("daily-report: no recent.jsonl, skipping")
        return

    # 收集今日记忆条目
    entries: list[dict] = []
    for line in recent_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = entry.get("timestamp", "")
        if ts.startswith(today):
            entries.append(entry)

    if not entries:
        log.info("daily-report: no entries for %s", today)
        return

    # 汇总
    tasks = [e.get("summary", e.get("user_message", "")) for e in entries]
    tools = sorted({t for e in entries for t in e.get("tools_used", [])})
    decisions = [e.get("decision", "") for e in entries if e.get("decision")]
    blockers = [e.get("blocker", "") for e in entries if e.get("blocker")]

    # 生成报告
    lines = [
        f"# Daily Report — {today}",
        "",
        "## Tasks Completed",
        *[f"- {t}" for t in tasks if t],
        "",
        "## Tools Used",
        *([f"- {t}" for t in tools] if tools else ["- (none)"]),
        "",
        "## Decisions Made",
        *([f"- {d}" for d in decisions] if decisions else ["- (none)"]),
        "",
        "## Blockers",
        *([f"- {b}" for b in blockers] if blockers else ["- (none)"]),
    ]

    report_dir = agent_dir / "memory" / "agent"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"daily-report-{today}.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("daily-report: saved %s", report_path)
