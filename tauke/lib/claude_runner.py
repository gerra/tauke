"""
Invokes `claude -p "<prompt>"` in the target workspace directory.
Token usage is measured by diffing ~/.claude/stats-cache.json before and after.
"""

import re
import subprocess
from pathlib import Path

from tauke.lib.token_tracker import snapshot


def run_claude(prompt: str, cwd: Path, timeout_seconds: int = 900) -> dict:
    """
    Run `claude -p "<prompt>"` in the given directory.
    Returns:
        {
            "status": "completed" | "rate_limited" | "error",
            "stdout": str,
            "stderr": str,
            "tokens_used": int,
            "summary": str,
        }
    """
    tokens_before = snapshot()

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "stdout": "",
            "stderr": f"Timed out after {timeout_seconds} seconds",
            "tokens_used": max(0, snapshot() - tokens_before),
            "summary": "Task timed out",
        }
    except FileNotFoundError:
        return {
            "status": "error",
            "stdout": "",
            "stderr": "claude CLI not found. Is Claude Code installed?",
            "tokens_used": 0,
            "summary": "claude CLI not found",
        }

    tokens_used = max(0, snapshot() - tokens_before)

    stdout = result.stdout or ""
    stderr = result.stderr or ""

    if _is_rate_limited(stdout + stderr):
        return {
            "status": "rate_limited",
            "stdout": stdout,
            "stderr": stderr,
            "tokens_used": 0,
            "summary": "Rate limited — no tokens available",
        }

    return {
        "status": "completed" if result.returncode == 0 else "error",
        "stdout": stdout,
        "stderr": stderr,
        "tokens_used": tokens_used,
        "summary": _extract_summary(stdout),
    }


def _is_rate_limited(text: str) -> bool:
    signals = [
        "rate limit", "quota exceeded", "too many requests",
        "usage limit", "out of tokens", "insufficient_quota",
    ]
    lower = text.lower()
    return any(s in lower for s in signals)


def _extract_summary(stdout: str) -> str:
    lines = [l.strip() for l in stdout.splitlines() if l.strip()]
    content_lines = [
        l for l in lines
        if not re.search(r"tokens?|cost|\$\d", l, re.IGNORECASE)
    ]
    return content_lines[-1][:200] if content_lines else "Task completed"
