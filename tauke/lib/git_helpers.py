"""
Low-level git helpers — all operations shell out to the git CLI.
"""

import subprocess
from pathlib import Path
from typing import Optional


def run(args: list[str], cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=check,
    )


def clone(remote_url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", remote_url, str(dest)],
        check=True,
        capture_output=True,
        text=True,
    )


def pull(repo: Path) -> None:
    run(["pull", "--rebase"], cwd=repo)


def add_all(repo: Path) -> None:
    run(["add", "-A"], cwd=repo)


def commit(repo: Path, message: str) -> None:
    run(["commit", "-m", message], cwd=repo)


def push(repo: Path, remote: str = "origin", branch: Optional[str] = None) -> subprocess.CompletedProcess:
    args = ["push", remote]
    if branch:
        args += [f"HEAD:{branch}"]
    return run(args, cwd=repo, check=False)


def push_new_branch(repo: Path, branch: str) -> subprocess.CompletedProcess:
    return run(["push", "-u", "origin", branch], cwd=repo, check=False)


def create_branch(repo: Path, branch: str) -> None:
    run(["checkout", "-b", branch], cwd=repo)


def fetch(repo: Path, remote: str = "origin") -> None:
    run(["fetch", remote], cwd=repo)


def checkout(repo: Path, ref: str) -> None:
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


def init_bare_local(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "tauke: init coordination repo"],
        cwd=str(path),
        check=True,
        capture_output=True,
        env={**__import__("os").environ, "GIT_AUTHOR_NAME": "tauke", "GIT_AUTHOR_EMAIL": "tauke@local", "GIT_COMMITTER_NAME": "tauke", "GIT_COMMITTER_EMAIL": "tauke@local"},
    )
