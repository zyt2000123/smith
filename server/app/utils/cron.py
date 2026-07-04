"""Minimal cron expression parser for common scheduling patterns.

Supports standard 5-field cron: minute hour day_of_month month day_of_week
Handles: literal values, */N steps, and * wildcards.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _parse_field(field: str, min_val: int, max_val: int) -> list[int]:
    """Parse a single cron field into a sorted list of valid values."""
    if field == "*":
        return list(range(min_val, max_val + 1))
    if field.startswith("*/"):
        step = int(field[2:])
        return list(range(min_val, max_val + 1, step))
    if "," in field:
        return sorted(int(v) for v in field.split(","))
    return [int(field)]


def next_cron_time(expression: str, after: datetime | None = None) -> datetime:
    """Calculate the next run time for a 5-field cron expression.

    Args:
        expression: "minute hour day month weekday" (e.g. "*/5 * * * *")
        after: start time (defaults to now UTC)

    Returns:
        Next datetime (UTC) when the cron should fire.
    """
    if after is None:
        after = datetime.now(timezone.utc)

    parts = expression.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Cron expression must have 5 fields, got {len(parts)}: {expression!r}")

    minutes = _parse_field(parts[0], 0, 59)
    hours = _parse_field(parts[1], 0, 23)
    days = _parse_field(parts[2], 1, 31)
    months = _parse_field(parts[3], 1, 12)
    weekdays = _parse_field(parts[4], 0, 6)  # 0=Monday in Python, but cron uses 0=Sunday

    # Convert cron weekday (0=Sun) to Python weekday (0=Mon)
    py_weekdays = [(d - 1) % 7 for d in weekdays] if parts[4] != "*" else None

    # Start searching from the next minute
    candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)

    # Search up to 366 days ahead to avoid infinite loops
    limit = after + timedelta(days=366)

    while candidate < limit:
        if candidate.month not in months:
            # Skip to first day of next valid month
            candidate = candidate.replace(day=1, hour=0, minute=0) + timedelta(days=32)
            candidate = candidate.replace(day=1, hour=0, minute=0)
            continue

        if candidate.day not in days:
            candidate = candidate.replace(hour=0, minute=0) + timedelta(days=1)
            continue

        if py_weekdays is not None and candidate.weekday() not in py_weekdays:
            candidate = candidate.replace(hour=0, minute=0) + timedelta(days=1)
            continue

        if candidate.hour not in hours:
            candidate = candidate.replace(minute=0) + timedelta(hours=1)
            continue

        if candidate.minute not in minutes:
            candidate += timedelta(minutes=1)
            continue

        return candidate

    raise ValueError(f"No valid next run time found within 366 days for: {expression!r}")


def next_interval_time(seconds: int, after: datetime | None = None) -> datetime:
    """Calculate the next run time for an interval-based trigger.

    Args:
        seconds: interval in seconds
        after: start time (defaults to now UTC)
    """
    if after is None:
        after = datetime.now(timezone.utc)
    if seconds <= 0:
        raise ValueError("Interval must be positive")
    return after + timedelta(seconds=seconds)
