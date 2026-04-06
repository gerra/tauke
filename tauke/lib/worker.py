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
from tauke.lib.config import (
    WORKSPACES_DIR,
    WORKER_PID_FILE,
    identity,
    projects,
)
from tauke.lib.token_tracker import get_usage, remaining


POLL_INTERVAL = 30  # seconds


def start_daemon():
    """
    Start the worker daemon in the foreground.
    Writes PID to ~/.tauke/worker.pid.
    """
    WORKER_PID_FILE.write_text(str(os.getpid()))

    def _cleanup(_sig, _frame):
        WORKER_PID_FILE.unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _cleanup)
    signal.signal(signal.SIGINT, _cleanup)

    print(
        f"[tauke worker] PID {os.getpid()} — polling every {POLL_INTERVAL}s",
        flush=True,
    )

    try:
        _daemon_loop()
    finally:
        WORKER_PID_FILE.unlink(missing_ok=True)


def _daemon_loop():
    while True:
        try:
            _poll_all_projects()
        except OSError as e:
            print(f"[tauke worker] Error in poll cycle: {e}", flush=True)
        time.sleep(POLL_INTERVAL)


def _poll_all_projects():
    ident = identity()
    handle = ident["handle"]
    worker_cfg = ident.get("worker", {})
    allowed = worker_cfg.get("allowed_orchestrators", [])
    daily_cap = worker_cfg.get("daily_cap", 50_000)

    proj_list = projects()
    if not proj_list:
        return

    used, _ = get_usage()

    for proj in proj_list:
        remote_url = proj["remote_url"]
        coord_branch = proj.get("coord_branch", "tauke-coord")
        try:
            coord_local = coord_repo.ensure_coord(remote_url, coord_branch)
        except OSError as e:
            print(f"[tauke worker] Cannot reach {remote_url}: {e}", flush=True)
            continue

        try:
            coord_repo.write_worker_heartbeat(coord_local, handle, daily_cap, used)
        except OSError as e:
            print(f"[tauke worker] Heartbeat failed for {remote_url}: {e}", flush=True)

        if remaining() < 5_000:
            print(
                f"[tauke worker] Skipping — only {remaining():,} tokens left today",
                flush=True,
            )
            continue

        if not allowed:
            continue

        pending = coord_repo.list_pending_tasks(coord_local, allowed)
        if not pending:
            continue

        task = pending[0]
        print(
            f"[tauke worker] Found task {task['id'][:8]} from {task['orchestrator']}",
            flush=True,
        )

        claimed = coord_repo.try_claim(coord_local, task["id"], handle)
        if not claimed:
            print(
                f"[tauke worker] Task {task['id'][:8]} claimed by someone else",
                flush=True,
            )
            continue

        result = _execute_task(task, handle)
        try:
            coord_repo.write_result(coord_local, result)
        except OSError as e:
            print(f"[tauke worker] Failed to write result: {e}", flush=True)

        # stats-cache.json updates automatically — just re-read it
        used = get_usage()[0]


def _execute_task(task: dict, handle: str) -> dict:
    task_id = task["id"]
    workspace = WORKSPACES_DIR / task_id
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)

    print(
        f"[tauke worker] Executing {task_id[:8]}: {task['prompt'][:60]}",
        flush=True,
    )

    try:
        repo_url = task["repo"]
        commit = task.get("commit")
        print(f"[tauke worker] Cloning {repo_url}...", flush=True)
        git.clone(repo_url, workspace)

        if commit:
            try:
                git.checkout(workspace, commit)
            except OSError:
                pass  # stay on default branch if checkout fails

        prompt = task["prompt"]
        context_files = task.get("context_files", [])
        if context_files:
            file_list = "\n".join(f"- {f}" for f in context_files)
            prompt += (
                "\n\nPlease pay particular attention to these files:\n" + file_list
            )

        print("[tauke worker] Running claude...", flush=True)
        run_result = run_claude(prompt, workspace)
        print(
            f"[tauke worker] Done: {run_result['status']}, "
            f"{run_result['tokens_used']:,} tokens",
            flush=True,
        )

        if run_result["status"] == "rate_limited":
            return _result(task_id, handle, "rate_limited", None, 0, "Worker hit rate limit", None)

        result_branch = f"tauke/result-{task_id}"
        pushed_branch = None

        if git.has_changes(workspace):
            git.create_branch(workspace, result_branch)
            git.add_all(workspace)
            git.commit(workspace, f"tauke: {run_result['summary'][:72]}")
            push_result = git.push_new_branch(workspace, result_branch)
            if push_result.returncode == 0:
                pushed_branch = result_branch
                print(f"[tauke worker] Pushed branch {result_branch}", flush=True)
            else:
                print(f"[tauke worker] Push failed: {push_result.stderr}", flush=True)
        else:
            print("[tauke worker] No file changes to push", flush=True)

        error = run_result["stderr"][:500] if run_result["status"] == "error" else None
        return _result(
            task_id, handle, run_result["status"],
            pushed_branch, run_result["tokens_used"], run_result["summary"], error,
        )

    except OSError as e:
        print(f"[tauke worker] Task {task_id[:8]} failed: {e}", flush=True)
        return _result(task_id, handle, "error", None, 0, str(e)[:200], str(e))
    finally:
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)


def _result(
    task_id: str, worker: str, status: str,
    branch, tokens: int, summary: str, error
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
