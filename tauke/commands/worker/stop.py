"""tauke worker stop — stop the daemon."""

import os
import signal
import typer
from rich.console import Console
from tauke.lib.config import WORKER_PID_FILE

console = Console()


def stop():
    """Stop the worker daemon."""
    if not WORKER_PID_FILE.exists():
        console.print("[dim]Worker daemon is not running.[/dim]")
        return

    pid_str = WORKER_PID_FILE.read_text().strip()
    try:
        pid = int(pid_str)
        os.kill(pid, signal.SIGTERM)
        WORKER_PID_FILE.unlink(missing_ok=True)
        console.print(f"[green]Worker daemon stopped (PID {pid}).[/green]")
    except ProcessLookupError:
        WORKER_PID_FILE.unlink(missing_ok=True)
        console.print("[dim]Daemon was not running (stale PID file removed).[/dim]")
    except ValueError:
        console.print(f"[red]Invalid PID in {WORKER_PID_FILE}[/red]")
