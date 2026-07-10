from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from ..infrastructure.database import get_app_db


class StatsService:

    async def get_agent_stats(self, agent_id: str) -> dict:
        """Return work statistics for agent homepage."""
        db = await get_app_db()

        # Basic agent info (created_at for days_active)
        rows = await db.execute_fetchall(
            "SELECT created_at FROM agent_profiles WHERE id=?", (agent_id,)
        )
        if not rows:
            raise HTTPException(404, "Agent profile not found")
        created_at = rows[0]["created_at"]
        try:
            created_dt = datetime.fromisoformat(created_at)
        except ValueError:
            created_dt = datetime.now(timezone.utc)
        days_active = max((datetime.now(timezone.utc) - created_dt.replace(tzinfo=timezone.utc)).days, 0)

        # Total sessions
        rows = await db.execute_fetchall(
            "SELECT count(*) as cnt FROM sessions WHERE agent_id=?",
            (agent_id,),
        )
        total_sessions = rows[0]["cnt"]

        # Total messages (user role only) across all sessions of this agent
        rows = await db.execute_fetchall(
            "SELECT count(*) as cnt FROM messages "
            "WHERE role='user' AND session_id IN "
            "(SELECT id FROM sessions WHERE agent_id=?)",
            (agent_id,),
        )
        total_messages = rows[0]["cnt"]

        # Task counts
        rows = await db.execute_fetchall(
            "SELECT count(*) as cnt FROM tasks WHERE agent_id=?",
            (agent_id,),
        )
        total_tasks = rows[0]["cnt"]

        rows = await db.execute_fetchall(
            "SELECT count(*) as cnt FROM tasks WHERE agent_id=? AND status='completed'",
            (agent_id,),
        )
        completed_tasks = rows[0]["cnt"]

        rows = await db.execute_fetchall(
            "SELECT count(*) as cnt FROM tasks WHERE agent_id=? AND type='automation'",
            (agent_id,),
        )
        auto_tasks = rows[0]["cnt"]

        # Recent activity: last 10 sessions with title + last message preview + timestamp
        rows = await db.execute_fetchall(
            "SELECT s.id, s.title, s.created_at, "
            "  (SELECT content FROM messages m WHERE m.session_id=s.id ORDER BY m.created_at DESC LIMIT 1) as last_message_preview, "
            "  (SELECT created_at FROM messages m WHERE m.session_id=s.id ORDER BY m.created_at DESC LIMIT 1) as last_message_at, "
            "  (SELECT count(*) FROM messages m WHERE m.session_id=s.id) as message_count "
            "FROM sessions s WHERE s.agent_id=? "
            "ORDER BY s.created_at DESC LIMIT 10",
            (agent_id,),
        )
        recent_activity = []
        for r in rows:
            preview = r["last_message_preview"] or ""
            if len(preview) > 100:
                preview = preview[:100] + "..."
            recent_activity.append({
                "session_id": r["id"],
                "title": r["title"],
                "created_at": r["created_at"],
                "last_message_preview": preview,
                "last_message_at": r["last_message_at"],
                "message_count": r["message_count"],
            })

        # Activity heatmap: messages per day for last 30 days
        rows = await db.execute_fetchall(
            "SELECT date(m.created_at) as day, count(*) as count "
            "FROM messages m "
            "WHERE m.session_id IN (SELECT id FROM sessions WHERE agent_id=?) "
            "GROUP BY day ORDER BY day DESC LIMIT 30",
            (agent_id,),
        )
        activity_heatmap = {r["day"]: r["count"] for r in rows}

        # Tool usage: count messages containing tool-call markers
        rows = await db.execute_fetchall(
            "SELECT m.content FROM messages m "
            "WHERE m.role='assistant' "
            "AND m.session_id IN (SELECT id FROM sessions WHERE agent_id=?) "
            "AND (m.content LIKE '%tool_use%' OR m.content LIKE '%function_call%' "
            "     OR m.content LIKE '%\"tool\"%' OR m.content LIKE '%tool_calls%')",
            (agent_id,),
        )
        tool_usage: dict[str, int] = {}
        import json as _json
        for r in rows:
            content = r["content"]
            # Try to parse JSON tool call structures
            try:
                data = _json.loads(content)
                if isinstance(data, list):
                    for item in data:
                        name = item.get("name") or item.get("tool") or ""
                        if name:
                            tool_usage[name] = tool_usage.get(name, 0) + 1
                elif isinstance(data, dict):
                    name = data.get("name") or data.get("tool") or ""
                    if name:
                        tool_usage[name] = tool_usage.get(name, 0) + 1
            except (_json.JSONDecodeError, TypeError, AttributeError):
                pass

        return {
            "agent_id": agent_id,
            "days_active": days_active,
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "auto_tasks": auto_tasks,
            "recent_activity": recent_activity,
            "activity_heatmap": activity_heatmap,
            "tool_usage": tool_usage,
        }
