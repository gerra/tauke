"""
Invokes `claude -p "<prompt>" --output-format json` in the target workspace.
Token usage and response text come straight from the structured JSON output,
which contains the Anthropic API's own `usage` counts — no cache diffing.
"""

import json
import subprocess
from pathlib import Path

from tauke.lib.logger import get

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

    try:
        result = subprocess.run(
            [
                "claude", "-p", prompt,
                "--allowedTools", "Read,Write,Edit,Glob,Grep,Bash",
                "--output-format", "json",
            ],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        _log.error("claude timed out after %ds", timeout_seconds)
        return {
            "status": "error",
            "stdout": "",
            "stderr": f"Timed out after {timeout_seconds} seconds",
            "tokens_used": 0,
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

    stdout = result.stdout or ""
    stderr = result.stderr or ""
    _log.debug("claude exit code: %d", result.returncode)
    if stderr:
        _log.debug("claude stderr: %s", stderr[:500])

    tokens_used, summary, is_error_payload = _parse_json_output(stdout)

    if _is_rate_limited(stdout + stderr):
        _log.warning("claude returned a rate-limit signal")
        return {
            "status": "rate_limited",
            "stdout": stdout,
            "stderr": stderr,
            "tokens_used": tokens_used,
            "summary": "Rate limited — no tokens available",
        }

    status = "completed" if result.returncode == 0 and not is_error_payload else "error"
    _log.info(
        "claude finished: status=%s tokens=%d summary=%s",
        status, tokens_used, summary[:100],
    )

    return {
        "status": status,
        "stdout": stdout,
        "stderr": stderr,
        "tokens_used": tokens_used,
        "summary": summary,
    }


def _parse_json_output(stdout: str) -> tuple[int, str, bool]:
    """Extract (tokens_used, summary, is_error) from claude -p --output-format json.

    Falls back to (0, first line of stdout, False) if JSON parsing fails —
    tokens_used will simply be 0 in that case, which matches prior behavior.
    """
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        _log.warning("could not parse claude JSON output; stdout=%s", stdout[:300])
        first = next((l.strip() for l in stdout.splitlines() if l.strip()), "Task completed")
        return 0, first[:200], False

    usage = payload.get("usage") or {}
    tokens_used = sum(
        int(usage.get(k, 0) or 0)
        for k in (
            "input_tokens", "output_tokens",
            "cache_creation_input_tokens", "cache_read_input_tokens",
        )
    )
    summary = (payload.get("result") or "Task completed")[:200]
    is_error = bool(payload.get("is_error"))
    return tokens_used, summary, is_error


def _is_rate_limited(text: str) -> bool:
    signals = [
        "rate limit", "quota exceeded", "too many requests",
        "usage limit", "out of tokens", "insufficient_quota",
    ]
    lower = text.lower()
    return any(s in lower for s in signals)
