"""
Invokes `claude -p "<prompt>"` in the target workspace directory.
Captures output, parses token usage from Claude's output.
"""

import re
import subprocess
from pathlib import Path
from typing import Optional


# Claude Code outputs token usage in a line like:
#   Tokens: 1,234 input · 5,678 output (6,912 total) · $0.02
_TOKEN_PATTERN = re.compile(
    r"Tokens?:.*?(\d[\d,]*)\s+total", re.IGNORECASE
)
# Alternative format: "Cost: ... | Tokens: X in, Y out"
_TOKEN_ALT_PATTERN = re.compile(
    r"(\d[\d,]+)\s+(?:tokens?\s+)?(?:total|used)", re.IGNORECASE
)


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
            "stderr": "Timed out after {} seconds".format(timeout_seconds),
            "tokens_used": 0,
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

    stdout = result.stdout or ""
    stderr = result.stderr or ""
    combined = stdout + "\n" + stderr

    # Detect rate limit
    if _is_rate_limited(combined):
        return {
            "status": "rate_limited",
            "stdout": stdout,
            "stderr": stderr,
            "tokens_used": 0,
            "summary": "Rate limited — no tokens available",
        }

    tokens = _parse_tokens(combined)
    summary = _extract_summary(stdout)

    return {
        "status": "completed" if result.returncode == 0 else "error",
        "stdout": stdout,
        "stderr": stderr,
        "tokens_used": tokens,
        "summary": summary,
    }


def _is_rate_limited(text: str) -> bool:
    signals = [
        "rate limit",
        "quota exceeded",
        "too many requests",
        "usage limit",
        "out of tokens",
        "insufficient_quota",
    ]
    lower = text.lower()
    return any(s in lower for s in signals)


def _parse_tokens(text: str) -> int:
    for pattern in (_TOKEN_PATTERN, _TOKEN_ALT_PATTERN):
        match = pattern.search(text)
        if match:
            raw = match.group(1).replace(",", "")
            try:
                return int(raw)
            except ValueError:
                pass
    return 0


def _extract_summary(stdout: str) -> str:
    """Take the last non-empty, non-token-stats line as a summary."""
    lines = [l.strip() for l in stdout.splitlines() if l.strip()]
    # Filter out lines that look like token stats
    content_lines = [l for l in lines if not re.search(r"tokens?|cost|\$\d", l, re.IGNORECASE)]
    if content_lines:
        # Return last meaningful line, truncated
        return content_lines[-1][:200]
    return "Task completed"
