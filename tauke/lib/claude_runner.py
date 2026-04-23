"""
Invokes `claude -p "<prompt>"` in the target workspace directory.
Token usage is measured by diffing ~/.claude/stats-cache.json before and after.
"""

import re
import subprocess
from pathlib import Path

from tauke.lib.logger import get
from tauke.lib.token_tracker import snapshot

_log = get("claude_runner")


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
    _log.info("starting claude -p in %s (timeout=%ds)", cwd, timeout_seconds)
    _log.debug("prompt (first 200 chars): %s", prompt[:200])
    tokens_before = snapshot()
    _log.debug("token snapshot before: %d", tokens_before)

    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--allowedTools", "Read,Write,Edit,Glob,Grep,Bash"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        tokens_used = max(0, snapshot() - tokens_before)
        _log.error("claude timed out after %ds (tokens so far: %d)", timeout_seconds, tokens_used)
        return {
            "status": "error",
            "stdout": "",
            "stderr": f"Timed out after {timeout_seconds} seconds",
            "tokens_used": tokens_used,
            "summary": "Task timed out",
        }
    except FileNotFoundError:
        _log.error("claude CLI not found — is Claude Code installed?")
        return {
            "status": "error",
            "stdout": "",
            "stderr": "claude CLI not found. Is Claude Code installed?",
            "tokens_used": 0,
            "summary": "claude CLI not found",
        }

    tokens_after = snapshot()
    tokens_used = max(0, tokens_after - tokens_before)
    _log.debug("token snapshot after: %d (delta: %d)", tokens_after, tokens_used)

    stdout = result.stdout or ""
    stderr = result.stderr or ""

    _log.debug("claude exit code: %d", result.returncode)
    if stderr:
        _log.debug("claude stderr: %s", stderr[:500])

    if _is_rate_limited(stdout + stderr):
        _log.warning("claude returned a rate-limit signal")
        return {
            "status": "rate_limited",
            "stdout": stdout,
            "stderr": stderr,
            "tokens_used": 0,
            "summary": "Rate limited — no tokens available",
        }

    status = "completed" if result.returncode == 0 else "error"
    summary = _extract_summary(stdout)
    _log.info("claude finished: status=%s tokens=%d summary=%s", status, tokens_used, summary[:100])

    return {
        "status": status,
        "stdout": stdout,
        "stderr": stderr,
        "tokens_used": tokens_used,
        "summary": summary,
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
