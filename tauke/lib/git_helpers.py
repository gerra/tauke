"""
Low-level git helpers — all operations shell out to the git CLI.
"""

import subprocess
from pathlib import Path
from typing import Optional

from tauke.lib.logger import get

_log = get("git")


def run(
    args: list[str],
    cwd: Optional[Path] = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    cmd = ["git"] + args
    _log.debug("run %s  cwd=%s", " ".join(args), cwd)
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        if check:
            _log.error(
                "git %s failed (rc=%d): %s",
                " ".join(args), result.returncode,
                (result.stderr or result.stdout).strip()[:300],
            )
            raise subprocess.CalledProcessError(
                result.returncode, cmd, result.stdout, result.stderr
            )
        else:
            _log.debug(
                "git %s rc=%d stderr=%s",
                " ".join(args), result.returncode,
                result.stderr.strip()[:200],
            )
    return result


def clone(remote_url: str, dest: Path) -> None:
    _log.info("clone %s -> %s", remote_url, dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "clone", remote_url, str(dest)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _log.error("clone failed: %s", result.stderr.strip()[:300])
        raise subprocess.CalledProcessError(
            result.returncode, ["git", "clone"], result.stdout, result.stderr
        )
    _log.debug("clone ok")


def pull(repo: Path) -> None:
    _log.debug("pull %s", repo)
    result = run(["pull", "--rebase"], cwd=repo, check=False)
    if result.returncode != 0:
        _log.warning("pull failed in %s: %s", repo, result.stderr.strip()[:200])
        raise OSError(f"git pull failed: {result.stderr.strip()[:200]}")


def add_all(repo: Path) -> None:
    _log.debug("add -A %s", repo)
    run(["add", "-A"], cwd=repo)


def commit(repo: Path, message: str) -> None:
    _log.debug("commit %s: %s", repo, message)
    run(["commit", "-m", message], cwd=repo)


def push(
    repo: Path,
    remote: str = "origin",
    branch: Optional[str] = None,
) -> subprocess.CompletedProcess:
    args = ["push", remote]
    if branch:
        args += [f"HEAD:{branch}"]
    _log.debug("push %s %s", repo, " ".join(args[1:]))
    result = run(args, cwd=repo, check=False)
    if result.returncode != 0:
        _log.warning("push failed: %s", result.stderr.strip()[:200])
    else:
        _log.debug("push ok")
    return result


def push_new_branch(repo: Path, branch: str) -> subprocess.CompletedProcess:
    _log.info("push new branch %s from %s", branch, repo)
    result = run(["push", "-u", "origin", branch], cwd=repo, check=False)
    if result.returncode != 0:
        _log.error("push new branch failed: %s", result.stderr.strip()[:200])
    else:
        _log.info("pushed branch %s ok", branch)
    return result


def create_branch(repo: Path, branch: str) -> None:
    _log.debug("create branch %s in %s", branch, repo)
    run(["checkout", "-b", branch], cwd=repo)


def fetch(repo: Path, remote: str = "origin") -> None:
    _log.debug("fetch %s %s", repo, remote)
    run(["fetch", remote], cwd=repo)


def checkout(repo: Path, ref: str) -> None:
    _log.debug("checkout %s in %s", ref, repo)
    run(["checkout", ref], cwd=repo)


def current_remote_url(cwd: Optional[Path] = None) -> str:
    result = run(["remote", "get-url", "origin"], cwd=cwd)
    return result.stdout.strip()


def current_commit(cwd: Optional[Path] = None) -> str:
    result = run(["rev-parse", "HEAD"], cwd=cwd)
    return result.stdout.strip()


def current_branch(cwd: Optional[Path] = None) -> str:
    result = run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
    return result.stdout.strip()


def has_changes(repo: Path) -> bool:
    result = run(["status", "--porcelain"], cwd=repo)
    return bool(result.stdout.strip())


def uncommitted_files(cwd: Optional[Path] = None) -> list[str]:
    """Return `git status --porcelain` lines (empty list if tree is clean)."""
    result = run(["status", "--porcelain"], cwd=cwd, check=False)
    return [line for line in result.stdout.splitlines() if line.strip()]


def unpushed_commits(cwd: Optional[Path] = None, branch: Optional[str] = None) -> int:
    """Count local commits ahead of origin/<branch>.

    Returns -1 if the remote-tracking branch doesn't exist (branch was
    never pushed). Returns 0 if HEAD matches origin, or a positive count
    of unpushed commits. Never raises — failures return 0.
    """
    ref = branch or current_branch(cwd)
    probe = run(
        ["rev-parse", "--verify", "--quiet", f"origin/{ref}"],
        cwd=cwd, check=False,
    )
    if probe.returncode != 0:
        return -1
    result = run(
        ["rev-list", "--count", f"origin/{ref}..HEAD"],
        cwd=cwd, check=False,
    )
    if result.returncode != 0:
        return 0
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0


def init_bare_local(path: Path) -> None:
    import os
    path.mkdir(parents=True, exist_ok=True)
    _log.info("init local repo at %s", path)
    subprocess.run(["git", "init"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "tauke: init coordination repo"],
        cwd=str(path),
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "tauke",
            "GIT_AUTHOR_EMAIL": "tauke@local",
            "GIT_COMMITTER_NAME": "tauke",
            "GIT_COMMITTER_EMAIL": "tauke@local",
        },
    )
