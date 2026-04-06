"""
tauke init — set up the tauke-coord branch in the current project's repo.

No new repo is created. The coordination data lives on a separate orphan
branch (tauke-coord) in the project's existing remote.
"""

import typer
from rich.console import Console

from tauke.lib.config import (
    identity,
    save_project_config,
    register_project,
    _find_git_root,
)
from tauke.lib import git_helpers as git
from tauke.lib.coord_repo import ensure_coord

console = Console()

COORD_BRANCH = "tauke-coord"


def init():
    """Initialize tauke for the current project."""
    ident = identity()
    handle = ident["handle"]

    git_root = _find_git_root()
    proj_config_path = git_root / ".tauke" / "config.json"

    if proj_config_path.exists():
        console.print("[yellow]This project already has .tauke/config.json.[/yellow]")
        if not typer.confirm("Reinitialize?", default=False):
            raise typer.Abort()

    # Read the project's remote
    try:
        remote_url = git.current_remote_url(git_root)
    except Exception:
        console.print(
            "[red]No git remote found.[/red] "
            "Push your project to a remote (e.g. GitHub) first."
        )
        raise typer.Exit(1)

    console.print(f"Project remote : [cyan]{remote_url}[/cyan]")
    console.print(f"Coord branch   : [cyan]{COORD_BRANCH}[/cyan]")
    console.print()
    console.print("Setting up coordination branch...")

    ensure_coord(remote_url, COORD_BRANCH)
    register_project(remote_url, COORD_BRANCH)

    # Write minimal .tauke/config.json
    config_file = save_project_config({"coord_branch": COORD_BRANCH}, git_root)

    console.print(f"[green]Done![/green] Coordination branch ready: [cyan]{COORD_BRANCH}[/cyan]")
    console.print(f"Project config : [dim]{config_file.relative_to(git_root)}[/dim]")
    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print(
        "  1. [cyan]git add .tauke/config.json"
        " && git commit -m 'add tauke' && git push[/cyan]"
    )
    console.print("  2. [cyan]tauke install-skill[/cyan]  — add the /tauke slash command")
    console.print(
        f"  3. Teammates: [cyan]git pull"
        f" && tauke worker allow {handle}"
        " && tauke worker start[/cyan]"
    )
