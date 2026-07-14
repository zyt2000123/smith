from __future__ import annotations

from pydantic import BaseModel


class TokenDayOut(BaseModel):
    date: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    sessions: int


class TokenModelOut(BaseModel):
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    sessions: int


class TokenStatsOut(BaseModel):
    year: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    session_count: int
    active_days: int
    current_streak: int
    longest_streak: int
    favorite_model: str | None
    peak_hour: int | None
    daily: list[TokenDayOut]
    models: list[TokenModelOut]
    estimated: bool = False
