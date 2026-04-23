"""
Config loading: merges machine-local identity (~/.tauke/identity.json)
with optional project config (.tauke/config.json, found by walking up from cwd).
"""

import json
import os
from pathlib import Path
from typing import Optional


TAUKE_DIR = Path.home() / ".tauke"
IDENTITY_FILE = TAUKE_DIR / "identity.json"
PROJECTS_FILE = TAUKE_DIR / "projects.json"
WORKER_PID_FILE = TAUKE_DIR / "worker.pid"
WORKSPACES_DIR = TAUKE_DIR / "workspaces"
COORD_REPOS_DIR = TAUKE_DIR / "coord-repos"

DEFAULT_WORKER_CAP = 1_000_000


def identity() -> dict:
    """Load machine-local identity. Raises if not set up."""
    if not IDENTITY_FILE.exists():
        raise RuntimeError(
            "Tauke is not set up on this machine. Run: tauke setup <your-github-handle>"
        )
    return json.loads(IDENTITY_FILE.read_text())


def save_identity(data: dict) -> None:
    TAUKE_DIR.mkdir(parents=True, exist_ok=True)
    IDENTITY_FILE.write_text(json.dumps(data, indent=2))


def project_config(start: Optional[Path] = None) -> dict:
    """
    Walk up from start (default: cwd) looking for .tauke/config.json.
    Returns empty dict if not found (global-only mode).
    """
    path = Path(start or os.getcwd())
    for directory in [path, *path.parents]:
        candidate = directory / ".tauke" / "config.json"
        if candidate.exists():
            return json.loads(candidate.read_text())
        # Stop at git root
        if (directory / ".git").exists():
            break
    return {}


def save_project_config(data: dict, project_root: Optional[Path] = None) -> Path:
    root = project_root or _find_git_root()
    config_dir = root / ".tauke"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.json"
    config_file.write_text(json.dumps(data, indent=2))
    return config_file


def coord_info(start: Optional[Path] = None) -> tuple[str, str]:
    """
    Return (project_remote_url, coord_branch) for the current project.
    The remote URL is read from `git remote get-url origin`.
    The branch name comes from .tauke/config.json (defaults to 'tauke-coord').
    Raises if not inside a git repo or tauke is not initialized.
    """
    import subprocess
    proj = project_config(start)
    if not proj and not ((_find_git_root(start) / ".tauke" / "config.json").exists()):
        raise RuntimeError(
            "No .tauke/config.json found. Run `tauke init` in your project directory first."
        )
    branch = proj.get("coord_branch", "tauke-coord")
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True, text=True,
        cwd=str(start or os.getcwd()),
    )
    if result.returncode != 0:
        raise RuntimeError("Could not read git remote URL. Are you inside a git repository?")
    remote_url = result.stdout.strip()
    return remote_url, branch


def projects() -> list:
    """Load the list of registered project coordination repos."""
    if not PROJECTS_FILE.exists():
        return []
    return json.loads(PROJECTS_FILE.read_text())


def save_projects(data: list) -> None:
    TAUKE_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_FILE.write_text(json.dumps(data, indent=2))


def register_project(remote_url: str, coord_branch: str = "tauke-coord") -> None:
    """Add a project to the worker's polling list if not already present."""
    proj_list = projects()
    repo_name = remote_url.rstrip("/").split("/")[-1].removesuffix(".git")
    local_clone = str(COORD_REPOS_DIR / repo_name)
    for entry in proj_list:
        if entry["remote_url"] == remote_url:
            return  # already registered
    proj_list.append({
        "remote_url": remote_url,
        "coord_branch": coord_branch,
        "local_clone": local_clone,
    })
    save_projects(proj_list)


def _find_git_root(start: Optional[Path] = None) -> Path:
    path = Path(start or os.getcwd())
    for directory in [path, *path.parents]:
        if (directory / ".git").exists():
            return directory
    return path
