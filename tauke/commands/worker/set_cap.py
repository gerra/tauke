"""tauke worker set-cap <tokens> — set daily token cap."""

import typer
from rich.console import Console
from tauke.lib.config import identity, save_identity

console = Console()


def set_cap(tokens: int = typer.Argument(..., help="Daily token cap (e.g. 80000)")):
    """Set your daily token cap for worker mode."""
    if tokens < 1000:
        console.print("[red]Cap must be at least 1,000 tokens.[/red]")
        raise typer.Exit(1)

    data = identity()
    data.setdefault("worker", {})["daily_cap"] = tokens
    save_identity(data)
    console.print(f"[green]Daily cap set to {tokens:,} tokens.[/green]")
