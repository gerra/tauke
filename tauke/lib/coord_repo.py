"""
Operations on the coordination git repo:
- ensure local clone exists and is up to date
- read/write task, claim, result, worker JSON files
- atomic push with conflict detection
"""

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from tauke.lib import git_helpers as git
from tauke.lib.config import COORD_REPOS_DIR


def _local_clone_path(remote_url: str) -> Path:
    repo_name = remote_url.rstrip("/").split("/")[-1].removesuffix(".git")
    return COORD_REPOS_DIR / repo_name


def ensure_coord(remote_url: str, coord_branch: str = "tauke-coord") -> Path:
    """
    Ensure a local clone of the project repo exists with the coord branch checked out.
    Pulls latest on each call.
    """
    dest = _local_clone_path(remote_url)
    if not dest.exists():
        # Clone and switch to the coord branch
        git.clone(remote_url, dest)
        _checkout_coord_branch(dest, coord_branch)
    else:
        try:
            git.pull(dest)
        except Exception:
            pass  # offline or conflict — work with what we have
    return dest


def _checkout_coord_branch(repo: Path, branch: str) -> None:
    """Switch to the coord branch. If it doesn't exist remotely, create it as orphan."""
    import subprocess
    # Try to checkout the existing remote branch
    result = git.run(["checkout", "-b", branch, f"origin/{branch}"], cwd=repo, check=False)
    if result.returncode == 0:
        return

    # Branch doesn't exist yet — create orphan (no history from main)
    git.run(["checkout", "--orphan", branch], cwd=repo)
    # Remove everything from the index (orphan inherits index from current branch)
    subprocess.run(["git", "rm", "-rf", "."], cwd=str(repo), capture_output=True)
    _ensure_structure(repo)


def _ensure_structure(repo: Path) -> None:
    """Create the required directories and push."""
    for subdir in ("tasks", "claims", "results", "workers"):
        (repo / subdir).mkdir(parents=True, exist_ok=True)
        gitkeep = repo / subdir / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()
    if git.has_changes(repo):
        git.add_all(repo)
        git.commit(repo, "tauke: initialize coord branch")
        git.push_new_branch(repo, _current_branch(repo))


def _current_branch(repo: Path) -> str:
    result = git.run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
    return result.stdout.strip()


# ── Tasks ────────────────────────────────────────────────────────────────────

def write_task(repo: Path, task: dict) -> None:
    path = repo / "tasks" / f"{task['id']}.json"
    path.write_text(json.dumps(task, indent=2))
    git.add_all(repo)
    git.commit(repo, f"tauke: submit task {task['id'][:8]}")
    git.push(repo)


def list_pending_tasks(repo: Path, allowed_orchestrators: list[str]) -> list[dict]:
    tasks_dir = repo / "tasks"
    claims_dir = repo / "claims"
    results_dir = repo / "results"
    pending = []
    for f in sorted(tasks_dir.glob("*.json")):
        if f.name == ".gitkeep":
            continue
        task = json.loads(f.read_text())
        task_id = task.get("id", f.stem)
        # skip if claimed or already has result
        if (claims_dir / f"{task_id}.json").exists():
            continue
        if (results_dir / f"{task_id}.json").exists():
            continue
        if task.get("orchestrator") in allowed_orchestrators:
            pending.append(task)
    return pending


def read_result(repo: Path, task_id: str) -> Optional[dict]:
    path = repo / "results" / f"{task_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


# ── Claims ───────────────────────────────────────────────────────────────────

def try_claim(repo: Path, task_id: str, handle: str) -> bool:
    """
    Attempt to atomically claim a task. Returns True on success.
    If another worker claimed it first (push rejected), returns False.
    """
    git.pull(repo)
    # Double-check it's still unclaimed after pull
    claim_path = repo / "claims" / f"{task_id}.json"
    if claim_path.exists():
        return False

    claim = {
        "task_id": task_id,
        "worker": handle,
        "claimed_at": _now(),
    }
    claim_path.write_text(json.dumps(claim, indent=2))
    git.add_all(repo)
    git.commit(repo, f"tauke: claim task {task_id[:8]} by {handle}")
    result = git.push(repo)
    if result.returncode != 0:
        # Push rejected — someone else claimed first
        git.run(["checkout", "--", str(claim_path.relative_to(repo))], cwd=repo)
        git.pull(repo)
        return False
    return True


# ── Results ──────────────────────────────────────────────────────────────────

def write_result(repo: Path, result: dict) -> None:
    path = repo / "results" / f"{result['task_id']}.json"
    path.write_text(json.dumps(result, indent=2))
    git.add_all(repo)
    git.commit(repo, f"tauke: result for task {result['task_id'][:8]} ({result['status']})")
    git.push(repo)


# ── Workers ──────────────────────────────────────────────────────────────────

def write_worker_heartbeat(repo: Path, handle: str, daily_cap: int, tokens_used: int) -> None:
    path = repo / "workers" / f"{handle}.json"
    today = str(date.today())
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except Exception:
            pass
    # Reset if date changed
    if existing.get("reset_date") != today:
        tokens_used = 0

    data = {
        "handle": handle,
        "daily_cap": daily_cap,
        "tokens_used_today": tokens_used,
        "reset_date": today,
        "last_seen": _now(),
        "available": True,
    }
    path.write_text(json.dumps(data, indent=2))
    if git.has_changes(repo):
        git.add_all(repo)
        git.commit(repo, f"tauke: heartbeat {handle}")
        git.push(repo)


def list_available_workers(repo: Path, min_tokens: int = 5_000) -> list[dict]:
    from datetime import timedelta
    workers_dir = repo / "workers"
    available = []
    now = datetime.now(timezone.utc)
    for f in workers_dir.glob("*.json"):
        if f.name == ".gitkeep":
            continue
        worker = json.loads(f.read_text())
        if not worker.get("available"):
            continue
        last_seen_str = worker.get("last_seen")
        if last_seen_str:
            last_seen = datetime.fromisoformat(last_seen_str)
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            if (now - last_seen) > timedelta(minutes=2):
                continue  # stale
        remaining = worker.get("daily_cap", 0) - worker.get("tokens_used_today", 0)
        if remaining >= min_tokens:
            available.append({**worker, "remaining_tokens": remaining})
    return sorted(available, key=lambda w: w["remaining_tokens"], reverse=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
