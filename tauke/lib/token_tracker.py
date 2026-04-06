"""
Tracks token usage locally in ~/.tauke/identity.json.
Resets daily.
"""

from datetime import date
from tauke.lib.config import identity, save_identity


def get_usage() -> tuple[int, int]:
    """Returns (tokens_used_today, daily_cap)."""
    data = identity()
    worker = data.get("worker", {})
    today = str(date.today())
    if worker.get("reset_date") != today:
        worker["tokens_used_today"] = 0
        worker["reset_date"] = today
        data["worker"] = worker
        save_identity(data)
    return worker.get("tokens_used_today", 0), worker.get("daily_cap", 50_000)


def add_usage(tokens: int) -> int:
    """Add tokens used, reset if new day. Returns new total."""
    data = identity()
    worker = data.get("worker", {})
    today = str(date.today())
    if worker.get("reset_date") != today:
        worker["tokens_used_today"] = 0
        worker["reset_date"] = today
    worker["tokens_used_today"] = worker.get("tokens_used_today", 0) + tokens
    data["worker"] = worker
    save_identity(data)
    return worker["tokens_used_today"]


def remaining() -> int:
    used, cap = get_usage()
    return max(0, cap - used)
