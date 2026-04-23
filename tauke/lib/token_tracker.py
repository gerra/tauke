"""
Track tokens consumed today by this worker.

Persists to ~/.tauke/usage.json. The daily counter resets automatically
the first time it's read after the date changes. Source of truth is the
tokens_used returned by each claude -p invocation (from the Anthropic
API response), added here via `add()`.

Prior versions of this file read ~/.claude/stats-cache.json, but that
cache only refreshes during interactive /usage actions — not during
claude -p runs — so before/after diffs were always zero. We now track
usage ourselves.
"""

import json
from datetime import date
from pathlib import Path

from tauke.lib.config import TAUKE_DIR, identity, DEFAULT_WORKER_CAP
from tauke.lib.logger import get

_log = get("token_tracker")

USAGE_FILE = TAUKE_DIR / "usage.json"


def _load() -> dict:
    if not USAGE_FILE.exists():
        return {"date": "", "tokens": 0}
    try:
        return json.loads(USAGE_FILE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        _log.warning("could not read usage.json: %s", e)
        return {"date": "", "tokens": 0}


def _save(data: dict) -> None:
    TAUKE_DIR.mkdir(parents=True, exist_ok=True)
    USAGE_FILE.write_text(json.dumps(data, indent=2))


def today_tokens() -> int:
    data = _load()
    today = str(date.today())
    if data.get("date") != today:
        return 0
    return int(data.get("tokens", 0))


def add(tokens: int) -> int:
    """Record token usage for a completed task. Returns the new daily total."""
    if tokens <= 0:
        return today_tokens()
    today = str(date.today())
    data = _load()
    if data.get("date") != today:
        _log.info("daily token counter reset (was %s, now %s)", data.get("date"), today)
        data = {"date": today, "tokens": 0}
    data["tokens"] = int(data.get("tokens", 0)) + int(tokens)
    _save(data)
    _log.debug("usage: +%d tokens (today total: %d)", tokens, data["tokens"])
    return data["tokens"]


def get_usage() -> tuple[int, int]:
    """Returns (tokens_used_today, daily_cap)."""
    cap = identity().get("worker", {}).get("daily_cap", DEFAULT_WORKER_CAP)
    used = today_tokens()
    _log.debug("get_usage: used=%d cap=%d remaining=%d", used, cap, max(0, cap - used))
    return used, cap


def remaining() -> int:
    used, cap = get_usage()
    return max(0, cap - used)
