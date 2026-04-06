"""tauke worker allow <handle> — add a trusted orchestrator."""

import typer
from rich.console import Console
from tauke.lib.config import identity, save_identity

console = Console()


def allow(handle: str = typer.Argument(..., help="GitHub handle to trust (e.g. alice)")):
    """Allow a teammate to delegate tasks to your worker."""
    data = identity()
    worker = data.setdefault("worker", {})
    allowed = worker.setdefault("allowed_orchestrators", [])

    if handle in allowed:
        console.print(f"[yellow]{handle} is already in your allowlist.[/yellow]")
        return

    allowed.append(handle)
    save_identity(data)
    console.print(f"[green]{handle} added to your allowlist.[/green]")
    console.print(f"Current allowlist: {', '.join(allowed)}")
