"""
Task lifecycle: creation, routing, polling.
"""

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tauke.lib import coord_repo, git_helpers as git
from tauke.lib.logger import get

_log = get("task")


def create_task(
    prompt: str,
    orchestrator: str,
    repo_url: str,
    branch: str,
    commit: str,
    context_files: Optional[list[str]] = None,
) -> dict:
    task = {
        "id": str(uuid.uuid4()),
        "orchestrator": orchestrator,
        "repo": repo_url,
        "branch": branch,
        "commit": commit,
        "prompt": prompt,
        "context_files": context_files or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
    }
    _log.info(
        "created task %s for repo=%s branch=%s commit=%s",
        task['id'][:8], repo_url, branch, commit[:8],
    )
    return task


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
    _log.info("submitting task %s and waiting (timeout=%ds)", task['id'][:8], timeout)
    coord_repo.write_task(coord_local, task)

    start = time.time()
    poll_count = 0
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            _log.warning(
                "timed out waiting for task %s after %.0fs",
                task['id'][:8], elapsed,
            )
            return None

        time.sleep(poll_interval)
        poll_count += 1

        try:
            git.pull(coord_local)
        except OSError as e:
            _log.debug("pull failed during poll %d: %s", poll_count, e)

        result = coord_repo.read_result(coord_local, task["id"])
        if result:
            _log.info(
                "task %s completed after %.0fs (%d polls)",
                task['id'][:8], elapsed, poll_count,
            )
            return result

        if poll_count % 6 == 0:  # log every ~minute
            _log.debug("still waiting for task %s (%.0fs elapsed)", task['id'][:8], elapsed)

        if on_waiting:
            on_waiting(elapsed)
