"""
Worker daemon: polls all registered coordination repos, claims tasks,
runs claude -p, pushes results.
"""

import os
import shutil
import signal
import sys
import time
from datetime import datetime, timezone

from tauke.lib import coord_repo, git_helpers as git
from tauke.lib.claude_runner import run_claude
from tauke.lib.config import WORKSPACES_DIR, WORKER_PID_FILE, identity, projects
from tauke.lib.logger import get
from tauke.lib import token_tracker
from tauke.lib.token_tracker import get_usage, remaining

_log = get("worker")

POLL_INTERVAL = 30  # seconds


def start_daemon():
    """Start the worker daemon in the foreground."""
    WORKER_PID_FILE.write_text(str(os.getpid()))
    _log.info("daemon starting — PID %d, poll interval %ds", os.getpid(), POLL_INTERVAL)

    def _cleanup(_sig, _frame):
        _log.info("daemon shutting down (PID %d)", os.getpid())
        WORKER_PID_FILE.unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _cleanup)
    signal.signal(signal.SIGINT, _cleanup)

    print(
        f"[tauke worker] PID {os.getpid()} — polling every {POLL_INTERVAL}s  "
        f"(log: {_log.root.handlers[0].baseFilename if _log.root.handlers else 'N/A'})",
        flush=True,
    )

    try:
        _daemon_loop()
    finally:
        WORKER_PID_FILE.unlink(missing_ok=True)
        _log.info("daemon stopped")


def _daemon_loop():
    while True:
        try:
            _poll_all_projects()
        except Exception as e:
            _log.error("unhandled error in poll cycle: %s", e, exc_info=True)
        time.sleep(POLL_INTERVAL)


def _poll_all_projects():
    ident = identity()
    handle = ident["handle"]
    worker_cfg = ident.get("worker", {})
    allowed = worker_cfg.get("allowed_orchestrators", [])
    daily_cap = worker_cfg.get("daily_cap", 50_000)

    proj_list = projects()
    if not proj_list:
        _log.debug("no projects registered, nothing to poll")
        return

    used, _ = get_usage()
    _log.debug(
        "poll cycle — handle=%s cap=%d used=%d remaining=%d projects=%d",
        handle, daily_cap, used, remaining(), len(proj_list),
    )

    for proj in proj_list:
        remote_url = proj["remote_url"]
        coord_branch = proj.get("coord_branch", "tauke-coord")
        _log.debug("polling %s (branch=%s)", remote_url, coord_branch)

        try:
            coord_local = coord_repo.ensure_coord(remote_url, coord_branch)
        except Exception as e:
            _log.error("cannot reach coordination repo %s: %s", remote_url, e)
            continue

        try:
            coord_repo.write_worker_heartbeat(coord_local, handle, daily_cap, used)
        except Exception as e:
            _log.error("heartbeat failed for %s: %s", remote_url, e)

        if remaining() < 5_000:
            _log.warning(
                "only %d tokens remaining today — skipping task pickup", remaining()
            )
            continue

        if not allowed:
            _log.debug("allowlist is empty — not picking up any tasks")
            continue

        pending = coord_repo.list_pending_tasks(coord_local, allowed)
        if not pending:
            _log.debug("no pending tasks for %s", remote_url)
            continue

        task = pending[0]
        _log.info(
            "found task %s from %s: %s",
            task['id'][:8], task['orchestrator'], task['prompt'][:80],
        )

        claimed = coord_repo.try_claim(coord_local, task["id"], handle)
        if not claimed:
            _log.info("task %s was claimed by another worker", task['id'][:8])
            continue

        result = _execute_task(task, handle)

        try:
            coord_repo.write_result(coord_local, result)
        except Exception as e:
            _log.error("failed to write result for task %s: %s", task['id'][:8], e)

        used = get_usage()[0]
        _log.info(
            "task %s done — status=%s tokens=%d (total today: %d)",
            task['id'][:8], result['status'], result['tokens_used'], used,
        )


def _execute_task(task: dict, handle: str) -> dict:
    task_id = task["id"]
    workspace = WORKSPACES_DIR / task_id
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)

    _log.info(
        "executing task %s — repo=%s commit=%s",
        task_id[:8], task.get('repo'), task.get('commit', 'HEAD')[:8],
    )

    try:
        repo_url = task["repo"]
        commit = task.get("commit")

        _log.info("cloning %s into workspace %s", repo_url, workspace)
        git.clone(repo_url, workspace)

        if commit:
            try:
                git.checkout(workspace, commit)
                _log.debug("checked out commit %s", commit[:8])
            except Exception as e:
                _log.warning(
                    "could not checkout commit %s (%s), staying on default branch",
                    commit[:8], e,
                )

        prompt = task["prompt"]
        context_files = task.get("context_files", [])
        if context_files:
            _log.debug("adding %d context file hints to prompt", len(context_files))
            file_list = "\n".join(f"- {f}" for f in context_files)
            prompt += "\n\nPlease pay particular attention to these files:\n" + file_list

        _log.info("running claude -p (task %s)", task_id[:8])
        run_result = run_claude(prompt, workspace)
        token_tracker.add(run_result.get("tokens_used", 0))
        _log.info(
            "claude finished task %s: status=%s tokens=%d",
            task_id[:8], run_result['status'], run_result['tokens_used'],
        )
        if run_result.get("stderr"):
            _log.debug("claude stderr for task %s: %s", task_id[:8], run_result['stderr'][:500])

        if run_result["status"] == "rate_limited":
            _log.warning("rate limited while executing task %s", task_id[:8])
            return _result(
                task_id, handle, "rate_limited", None, 0, "Worker hit rate limit", None
            )

        result_branch = f"tauke/result-{task_id}"
        pushed_branch = None

        if git.has_changes(workspace):
            _log.info("changes detected — creating result branch %s", result_branch)
            git.create_branch(workspace, result_branch)
            git.add_all(workspace)
            git.commit(workspace, f"tauke: {run_result['summary'][:72]}")
            push_result = git.push_new_branch(workspace, result_branch)
            if push_result.returncode == 0:
                pushed_branch = result_branch
                _log.info("pushed result branch %s", result_branch)
            else:
                _log.error(
                    "failed to push result branch %s: %s",
                    result_branch, push_result.stderr.strip()[:300],
                )
        else:
            _log.info("claude made no file changes for task %s", task_id[:8])

        error = run_result["stderr"][:500] if run_result["status"] == "error" else None
        return _result(
            task_id, handle, run_result["status"],
            pushed_branch, run_result["tokens_used"], run_result["summary"], error,
        )

    except Exception as e:
        _log.error("task %s failed with exception: %s", task_id[:8], e, exc_info=True)
        detail = _error_detail(e)
        return _result(task_id, handle, "error", None, 0, detail[:200], detail)
    finally:
        if workspace.exists():
            _log.debug("cleaning up workspace %s", workspace)
            shutil.rmtree(workspace, ignore_errors=True)


def _error_detail(e: Exception) -> str:
    """Best-effort extraction of useful info from an exception.

    CalledProcessError's str() is just "Command X returned exit status N",
    which hides git's actual stderr. If the exception carries a `stderr`
    attribute (subprocess errors do), include it.
    """
    msg = str(e)
    stderr = getattr(e, "stderr", None)
    if stderr:
        stderr_str = stderr.decode() if isinstance(stderr, bytes) else stderr
        stderr_str = stderr_str.strip()
        if stderr_str:
            return f"{msg}: {stderr_str}"
    return msg


def _result(
    task_id: str, worker: str, status: str,
    branch, tokens: int, summary: str, error,
) -> dict:
    return {
        "task_id": task_id,
        "worker": worker,
        "status": status,
        "result_branch": branch,
        "tokens_used": tokens,
        "summary": summary,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "error": error,
    }
