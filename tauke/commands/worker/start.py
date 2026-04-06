"""tauke worker start — register current project and start the daemon."""

import os
import subprocess
import sys
import typer
from rich.console import Console

from tauke.lib.config import WORKER_PID_FILE, identity, coord_info, register_project

console = Console()


def start(
    foreground: bool = typer.Option(
        False, "--fg", "--foreground", help="Run in foreground (for debugging)"
    ),
):
    """Register this project and start the worker daemon."""
    identity()  # ensure set up; raises with a clear message if not

    # Register current project's coord branch
    try:
        remote_url, coord_branch = coord_info()
        register_project(remote_url, coord_branch)
        console.print(
            f"Registered project: [dim]{remote_url}[/dim] (branch: {coord_branch})"
        )
    except RuntimeError:
        console.print("[yellow]No .tauke/config.json found in this project.[/yellow]")
        console.print(
            "Run [cyan]tauke init[/cyan] first, "
            "or start the worker from a project directory."
        )

    # Check if already running
    if WORKER_PID_FILE.exists():
        pid = WORKER_PID_FILE.read_text().strip()
        if _pid_is_alive(pid):
            console.print(
                f"[yellow]Worker daemon already running (PID {pid}).[/yellow]"
            )
            console.print(
                "It will pick up the newly registered project on next poll cycle."
            )
            return
        WORKER_PID_FILE.unlink(missing_ok=True)

    if foreground:
        console.print("[green]Starting worker daemon in foreground...[/green] (Ctrl+C to stop)")
        from tauke.lib.worker import start_daemon
        start_daemon()
    else:
        log = _log_file()
        proc = subprocess.Popen(
            [sys.executable, "-m", "tauke._daemon"],
            stdout=open(str(log), "a"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        console.print(f"[green]Worker daemon started[/green] (PID {proc.pid})")
        console.print(f"  Log : [dim]{log}[/dim]")
        console.print("  Stop: [cyan]tauke worker stop[/cyan]")


def _pid_is_alive(pid_str: str) -> bool:
    try:
        pid = int(pid_str)
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        return False


def _log_file():
    from tauke.lib.config import TAUKE_DIR
    return TAUKE_DIR / "worker.log"
