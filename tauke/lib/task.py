"""
Task lifecycle: creation, routing, polling.
"""

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tauke.lib import coord_repo, git_helpers as git


def create_task(
    prompt: str,
    orchestrator: str,
    repo_url: str,
    branch: str,
    commit: str,
    context_files: Optional[list[str]] = None,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "orchestrator": orchestrator,
        "repo": repo_url,
        "branch": branch,
        "commit": commit,
        "prompt": prompt,
        "context_files": context_files or [],
        "created_at": _now(),
        "status": "pending",
    }


def submit_and_wait(
    task: dict,
    coord_local: Path,
    poll_interval: int = 10,
    timeout: int = 900,
    on_waiting=None,
) -> Optional[dict]:
    """
    Write the task to the coordination repo, then poll for a result.
    Returns the result dict or None on timeout.
    on_waiting: optional callback called each poll cycle with elapsed seconds.
    """
    coord_repo.write_task(coord_local, task)

    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            return None

        time.sleep(poll_interval)

        try:
            git.pull(coord_local)
        except Exception:
            pass

        result = coord_repo.read_result(coord_local, task["id"])
        if result:
            return result

        if on_waiting:
            on_waiting(elapsed)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
