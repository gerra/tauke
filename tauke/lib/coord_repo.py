"""
Operations on the coordination git repo:
- ensure local clone exists and is up to date
- read/write task, claim, result, worker JSON files
- atomic push with conflict detection
"""

import json
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from tauke.lib import git_helpers as git
from tauke.lib.config import COORD_REPOS_DIR
from tauke.lib.logger import get

_log = get("coord_repo")


def _local_clone_path(remote_url: str) -> Path:
    repo_name = remote_url.rstrip("/").split("/")[-1].removesuffix(".git")
    return COORD_REPOS_DIR / repo_name


def ensure_coord(remote_url: str, coord_branch: str = "tauke-coord") -> Path:
    """
    Ensure a local clone of the project repo exists with the coord branch
    checked out. Pulls latest on each call.
    """
    dest = _local_clone_path(remote_url)
    _log.debug("ensure_coord %s branch=%s dest=%s", remote_url, coord_branch, dest)
    if not dest.exists():
        _log.info("cloning %s for coord branch %s", remote_url, coord_branch)
        git.clone(remote_url, dest)
        _checkout_coord_branch(dest, coord_branch)
    else:
        try:
            git.pull(dest)
        except OSError as e:
            _log.warning("pull failed, continuing with local state: %s", e)
    return dest


def _checkout_coord_branch(repo: Path, branch: str) -> None:
    """Switch to the coord branch. Create as orphan if it doesn't exist yet."""
    _log.info("checking out coord branch '%s' in %s", branch, repo)
    result = git.run(
        ["checkout", "-b", branch, f"origin/{branch}"],
        cwd=repo,
        check=False,
    )
    if result.returncode == 0:
        _log.debug("checked out existing remote branch %s", branch)
        return

    _log.info("branch '%s' not on remote — creating orphan", branch)
    git.run(["checkout", "--orphan", branch], cwd=repo)
    subprocess.run(
        ["git", "rm", "-rf", "."],
        cwd=str(repo),
        capture_output=True,
    )
    _ensure_structure(repo)


def _ensure_structure(repo: Path) -> None:
    """Create the required directories and push."""
    _log.debug("ensuring coord repo structure in %s", repo)
    for subdir in ("tasks", "claims", "results"):
        (repo / subdir).mkdir(parents=True, exist_ok=True)
        gitkeep = repo / subdir / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()
    if git.has_changes(repo):
        git.add_all(repo)
        git.commit(repo, "tauke: initialize coord branch")
        branch = _current_branch(repo)
        _log.info("pushing new coord branch '%s'", branch)
        git.push_new_branch(repo, branch)


def _current_branch(repo: Path) -> str:
    result = git.run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
    return result.stdout.strip()


# ── Tasks ────────────────────────────────────────────────────────────────────

def write_task(repo: Path, task: dict) -> None:
    _log.info("writing task %s (orchestrator=%s)", task['id'][:8], task.get('orchestrator'))
    path = repo / "tasks" / f"{task['id']}.json"
    path.write_text(json.dumps(task, indent=2))
    git.add_all(repo)
    git.commit(repo, f"tauke: submit task {task['id'][:8]}")
    git.push(repo)
    _log.info("task %s pushed to coord branch", task['id'][:8])


def list_pending_tasks(repo: Path, allowed_orchestrators: list[str]) -> list[dict]:
    tasks_dir = repo / "tasks"
    claims_dir = repo / "claims"
    results_dir = repo / "results"
    pending = []
    for f in sorted(tasks_dir.glob("*.json")):
        if f.name == ".gitkeep":
            continue
        try:
            task = json.loads(f.read_text())
        except json.JSONDecodeError as e:
            _log.warning("could not parse task file %s: %s", f, e)
            continue
        task_id = task.get("id", f.stem)
        if (claims_dir / f"{task_id}.json").exists():
            _log.debug("task %s already claimed, skipping", task_id[:8])
            continue
        if (results_dir / f"{task_id}.json").exists():
            _log.debug("task %s already has result, skipping", task_id[:8])
            continue
        if task.get("orchestrator") in allowed_orchestrators:
            pending.append(task)
        else:
            _log.debug(
                "task %s orchestrator '%s' not in allowlist %s",
                task_id[:8], task.get('orchestrator'), allowed_orchestrators,
            )
    _log.debug("found %d pending tasks", len(pending))
    return pending


def read_result(repo: Path, task_id: str) -> Optional[dict]:
    path = repo / "results" / f"{task_id}.json"
    if path.exists():
        _log.debug("result ready for task %s", task_id[:8])
        return json.loads(path.read_text())
    return None


# ── Claims ───────────────────────────────────────────────────────────────────

def try_claim(repo: Path, task_id: str, handle: str) -> bool:
    """
    Attempt to atomically claim a task via optimistic git push.
    Returns True on success, False if another worker claimed it first.
    """
    _log.info("attempting to claim task %s as %s", task_id[:8], handle)
    git.pull(repo)

    claim_path = repo / "claims" / f"{task_id}.json"
    if claim_path.exists():
        _log.info("task %s already claimed after pull", task_id[:8])
        return False

    claim = {"task_id": task_id, "worker": handle, "claimed_at": _now()}
    claim_path.write_text(json.dumps(claim, indent=2))
    git.add_all(repo)
    git.commit(repo, f"tauke: claim task {task_id[:8]} by {handle}")
    result = git.push(repo)

    if result.returncode != 0:
        _log.warning(
            "claim push rejected for task %s (race condition) — rolling back",
            task_id[:8],
        )
        git.run(
            ["checkout", "--", str(claim_path.relative_to(repo))],
            cwd=repo,
        )
        git.pull(repo)
        return False

    _log.info("claimed task %s successfully", task_id[:8])
    return True


# ── Results ──────────────────────────────────────────────────────────────────

def write_result(repo: Path, result: dict) -> None:
    task_id = result['task_id']
    _log.info(
        "writing result for task %s: status=%s tokens=%s",
        task_id[:8], result.get('status'), result.get('tokens_used'),
    )
    path = repo / "results" / f"{task_id}.json"
    path.write_text(json.dumps(result, indent=2))
    git.add_all(repo)
    git.commit(repo, f"tauke: result for task {task_id[:8]} ({result['status']})")
    git.push(repo)
    _log.info("result for task %s pushed", task_id[:8])


# ── Workers ──────────────────────────────────────────────────────────────────
#
# Each worker owns a dedicated orphan branch `tauke-hb/<handle>` containing a
# single `worker.json`. Heartbeats are written via `commit --amend` + force
# push, so the branch stays at exactly one commit forever (no history growth).
# Because only one writer ever touches `tauke-hb/<handle>`, force-pushes don't
# race with anyone else.

def _hb_branch(handle: str) -> str:
    return f"tauke-hb/{handle}"


def _hb_repo_path(remote_url: str, handle: str) -> Path:
    repo_name = remote_url.rstrip("/").split("/")[-1].removesuffix(".git")
    return COORD_REPOS_DIR / f"{repo_name}-hb-{handle}"


def _ensure_hb_repo(remote_url: str, handle: str) -> Path:
    """Local clone dedicated to this worker's heartbeat branch."""
    dest = _hb_repo_path(remote_url, handle)
    branch = _hb_branch(handle)
    if not dest.exists():
        _log.info("cloning %s for heartbeat branch %s", remote_url, branch)
        git.clone(remote_url, dest)
        result = git.run(
            ["checkout", "-b", branch, f"origin/{branch}"],
            cwd=dest, check=False,
        )
        if result.returncode != 0:
            _log.info("branch %s not on remote — creating orphan", branch)
            git.run(["checkout", "--orphan", branch], cwd=dest)
            subprocess.run(
                ["git", "rm", "-rf", "."], cwd=str(dest), capture_output=True,
            )
    return dest


def write_worker_heartbeat(
    repo: Path, handle: str, daily_cap: int, tokens_used: int
) -> None:
    """Push a heartbeat to the worker's dedicated tauke-hb/<handle> branch.

    `repo` is the coord_local clone — we derive the remote URL from it so
    callers don't need to pass extra arguments.
    """
    remote_url = git.current_remote_url(repo)
    hb_local = _ensure_hb_repo(remote_url, handle)
    branch = _hb_branch(handle)
    path = hb_local / "worker.json"

    today = str(date.today())
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    if existing.get("reset_date") != today:
        _log.info("daily reset for worker %s", handle)
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
    git.add_all(hb_local)

    has_head = git.run(
        ["rev-parse", "--verify", "HEAD"], cwd=hb_local, check=False,
    ).returncode == 0
    if has_head:
        git.run(["commit", "--amend", "--no-edit"], cwd=hb_local)
    else:
        git.run(["commit", "-m", f"tauke: heartbeat {handle}"], cwd=hb_local)

    push = git.run(["push", "-f", "origin", branch], cwd=hb_local, check=False)
    if push.returncode != 0:
        _log.warning(
            "heartbeat force-push failed for %s: %s",
            handle, push.stderr.strip()[:200],
        )
    else:
        _log.debug(
            "heartbeat pushed for %s (%d/%d tokens used today)",
            handle, tokens_used, daily_cap,
        )


def list_all_workers(repo: Path) -> list[dict]:
    """Fetch every tauke-hb/* ref and return each worker's raw heartbeat data,
    with no availability/freshness filtering. Used by `tauke status` which
    wants to show offline workers too.
    """
    git.run(
        [
            "fetch", "--prune", "origin",
            "+refs/heads/tauke-hb/*:refs/remotes/origin/tauke-hb/*",
        ],
        cwd=repo, check=False,
    )
    refs_result = git.run(
        [
            "for-each-ref", "--format=%(refname:short)",
            "refs/remotes/origin/tauke-hb/",
        ],
        cwd=repo, check=False,
    )
    refs = [r.strip() for r in refs_result.stdout.splitlines() if r.strip()]
    _log.debug("found %d heartbeat refs", len(refs))

    workers = []
    for ref in refs:
        show = git.run(["show", f"{ref}:worker.json"], cwd=repo, check=False)
        if show.returncode != 0:
            _log.debug("ref %s has no worker.json, skipping", ref)
            continue
        try:
            workers.append(json.loads(show.stdout))
        except json.JSONDecodeError:
            _log.debug("ref %s has unparseable worker.json", ref)
    return workers


def list_available_workers(repo: Path, min_tokens: int = 5_000) -> list[dict]:
    """Return workers considered routable right now: heartbeat within 2min,
    marked available, and enough remaining tokens.
    """
    now = datetime.now(timezone.utc)
    available = []
    for worker in list_all_workers(repo):
        if not worker.get("available"):
            _log.debug("worker %s marked unavailable", worker.get("handle"))
            continue
        last_seen_str = worker.get("last_seen")
        if last_seen_str:
            last_seen = datetime.fromisoformat(last_seen_str)
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            age = (now - last_seen).total_seconds()
            if age > 120:
                _log.debug(
                    "worker %s stale (last seen %.0fs ago)",
                    worker.get("handle"), age,
                )
                continue
        remaining = worker.get("daily_cap", 0) - worker.get("tokens_used_today", 0)
        if remaining >= min_tokens:
            available.append({**worker, "remaining_tokens": remaining})
        else:
            _log.debug(
                "worker %s has only %d tokens remaining (min %d)",
                worker.get("handle"), remaining, min_tokens,
            )
    _log.debug("found %d available worker(s)", len(available))
    return sorted(available, key=lambda w: w["remaining_tokens"], reverse=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
