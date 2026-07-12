"""Local bearer-token authentication for the Agent-Smith API.

The server generates a random token on first startup and persists it to
~/.agent-smith/auth_token (mode 0600).  Every /api/* request must carry
``Authorization: Bearer <token>``.  The health endpoint is exempt.

The shell (or any local client) reads that file to authenticate.
"""
from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from common.config import DATA_DIR
from common.paths import PRIVATE_FILE_MODE

_TOKEN_PATH = Path(DATA_DIR) / "auth_token"
_bearer_scheme = HTTPBearer(auto_error=False)

_cached_token: str | None = None


def _read_or_create_token() -> str:
    global _cached_token
    if _cached_token is not None:
        return _cached_token

    if _TOKEN_PATH.is_file():
        token = _TOKEN_PATH.read_text().strip()
        if token:
            _cached_token = token
            return token

    token = secrets.token_urlsafe(32)
    _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_PATH.write_text(token)
    _TOKEN_PATH.chmod(PRIVATE_FILE_MODE)
    _cached_token = token
    return token


def get_local_token() -> str:
    return _read_or_create_token()


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    if credentials is None or credentials.credentials != get_local_token():
        raise HTTPException(401, "Invalid or missing auth token")
