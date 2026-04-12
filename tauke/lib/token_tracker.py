"""
Reads actual Claude Code token usage from ~/.claude/stats-cache.json.
This is the same data shown by /usage in Claude Code — no manual tracking needed.
"""

import json
from datetime import date
from pathlib import Path

from tauke.lib.config import identity, DEFAULT_WORKER_CAP
from tauke.lib.logger import get

_log = get("token_tracker")

STATS_CACHE = Path.home() / ".claude" / "stats-cache.json"


def today_tokens() -> int:
    """
    Read today's total token count across all models from Claude Code's
    local stats cache. Returns 0 if the file doesn't exist or has no
    entry for today.
    """
    if not STATS_CACHE.exists():
        _log.debug("stats-cache.json not found at %s", STATS_CACHE)
        return 0
    try:
        data = json.loads(STATS_CACHE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        _log.warning("could not read stats-cache.json: %s", e)
        return 0

    today = str(date.today())
    for entry in data.get("dailyModelTokens", []):
        if entry.get("date") == today:
            total = sum(entry.get("tokensByModel", {}).values())
            _log.debug("today's token usage from stats-cache: %d", total)
            return total

    _log.debug("no entry for today (%s) in stats-cache", today)
    return 0


def snapshot() -> int:
    """Return current today's token total. Diff before/after a claude run to measure usage."""
    return today_tokens()


def get_usage() -> tuple[int, int]:
    """Returns (tokens_used_today, daily_cap)."""
    cap = identity().get("worker", {}).get("daily_cap", DEFAULT_WORKER_CAP)
    used = today_tokens()
    _log.debug("get_usage: used=%d cap=%d remaining=%d", used, cap, max(0, cap - used))
    return used, cap


def remaining() -> int:
    used, cap = get_usage()
    return max(0, cap - used)
