"""
Reads actual Claude Code token usage from ~/.claude/stats-cache.json.
This is the same data shown by /usage in Claude Code — no manual tracking needed.
"""

import json
from datetime import date
from pathlib import Path

from tauke.lib.config import identity, DEFAULT_WORKER_CAP

STATS_CACHE = Path.home() / ".claude" / "stats-cache.json"


def today_tokens() -> int:
    """
    Read today's total token count across all models from Claude Code's
    local stats cache. Returns 0 if the file doesn't exist or has no
    entry for today.
    """
    if not STATS_CACHE.exists():
        return 0
    try:
        data = json.loads(STATS_CACHE.read_text())
    except (json.JSONDecodeError, OSError):
        return 0

    today = str(date.today())
    for entry in data.get("dailyModelTokens", []):
        if entry.get("date") == today:
            return sum(entry.get("tokensByModel", {}).values())
    return 0


def snapshot() -> int:
    """Return current today's token total (use before/after a claude run to diff)."""
    return today_tokens()


def get_usage() -> tuple[int, int]:
    """Returns (tokens_used_today, daily_cap)."""
    cap = identity().get("worker", {}).get("daily_cap", DEFAULT_WORKER_CAP)
    return today_tokens(), cap


def remaining() -> int:
    used, cap = get_usage()
    return max(0, cap - used)
