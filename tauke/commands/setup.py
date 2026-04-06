"""tauke setup <handle> — initialize machine-local identity."""

import typer
from rich.console import Console
from tauke.lib.config import IDENTITY_FILE, DEFAULT_WORKER_CAP, save_identity

console = Console()


def setup(handle: str = typer.Argument(..., help="Your GitHub handle (e.g. alice)")):
    """Set up your machine-local tauke identity."""
    if IDENTITY_FILE.exists():
        existing = __import__("json").loads(IDENTITY_FILE.read_text())
        current_handle = existing.get("handle", "")
        if not typer.confirm(
            f"Identity already set up as '{current_handle}'. Overwrite?", default=False
        ):
            raise typer.Abort()

    data = {
        "handle": handle,
        "worker": {
            "daily_cap": DEFAULT_WORKER_CAP,
            "tokens_used_today": 0,
            "reset_date": str(__import__("datetime").date.today()),
            "allowed_orchestrators": [],
        },
    }
    save_identity(data)
    console.print(f"[green]Identity saved:[/green] {IDENTITY_FILE}")
    console.print(f"  Handle    : [bold]{handle}[/bold]")
    console.print(f"  Daily cap : [bold]{DEFAULT_WORKER_CAP:,}[/bold] tokens (change with [cyan]tauke worker set-cap[/cyan])")
    console.print()
    console.print("Next: run [cyan]tauke init[/cyan] inside a project to set up delegation.")
