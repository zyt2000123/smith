from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import main  # noqa: E402
from app.infrastructure import auth  # noqa: E402


def test_server_lifespan_materializes_local_auth_token_before_shell_requests(
    monkeypatch,
    tmp_path: Path,
) -> None:
    token_path = tmp_path / "auth_token"
    monkeypatch.setattr(auth, "_TOKEN_PATH", token_path)
    monkeypatch.setattr(auth, "_cached_token", None)

    async def fake_get_app_db():
        return None

    async def fake_close_db() -> None:
        return None

    async def fake_close_clients() -> None:
        return None

    async def fake_scheduler() -> None:
        await asyncio.sleep(3600)

    class FakeTokenStatsService:
        async def sync_from_traces(self) -> int:
            return 0

    monkeypatch.setattr(main, "get_app_db", fake_get_app_db)
    monkeypatch.setattr(main, "close_db", fake_close_db)
    monkeypatch.setattr(main, "close_shared_llm_clients", fake_close_clients)
    monkeypatch.setattr(main, "run_scheduler", fake_scheduler)
    monkeypatch.setattr(main, "load_runtime_identity_catalog", lambda force=False: None)
    monkeypatch.setattr(main, "TokenStatsService", FakeTokenStatsService)

    with TestClient(main.app):
        assert token_path.is_file()
        assert token_path.read_text(encoding="utf-8").strip()


def test_server_lifespan_syncs_token_stats_before_serving_requests(
    monkeypatch,
) -> None:
    calls: list[str] = []

    class FakeTokenStatsService:
        async def sync_from_traces(self) -> int:
            calls.append("sync")
            return 0

    async def fake_get_app_db():
        return None

    async def fake_close_db() -> None:
        return None

    async def fake_close_clients() -> None:
        return None

    async def fake_scheduler() -> None:
        await asyncio.sleep(3600)

    monkeypatch.setattr(main, "get_local_token", lambda: "test-token")
    monkeypatch.setattr(main, "get_app_db", fake_get_app_db)
    monkeypatch.setattr(main, "close_db", fake_close_db)
    monkeypatch.setattr(main, "close_shared_llm_clients", fake_close_clients)
    monkeypatch.setattr(main, "run_scheduler", fake_scheduler)
    monkeypatch.setattr(main, "load_runtime_identity_catalog", lambda force=False: None)
    monkeypatch.setattr(main, "TokenStatsService", FakeTokenStatsService)

    with TestClient(main.app):
        assert calls == ["sync"]
