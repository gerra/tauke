"""tauke cancel <task-id> — remove a task (and its claim/result) from the queue."""

import json
import typer
from rich.console import Console

from tauke.lib.config import identity, coord_info
from tauke.lib.coord_repo import ensure_coord
from tauke.lib import git_helpers as git
from tauke.lib.logger import get

console = Console()
_log = get("cmd.cancel")


def cancel(
    task_id: str = typer.Argument(..., help="Task ID or prefix to cancel"),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Cancel even if you are not the orchestrator that submitted it",
    ),
):
    """Remove a task from the coordination branch.

    Deletes tasks/<id>.json, claims/<id>.json, and results/<id>.json, commits,
    and pushes. A worker currently executing the task will still finish and
    write a result, which will just sit orphaned (no matching task file) —
    harmless, but you can re-run this command to clean it up afterward.
    """
    ident = identity()
    handle = ident["handle"]
    remote_url, coord_branch = coord_info()
    coord_local = ensure_coord(remote_url, coord_branch)

    tasks_dir = coord_local / "tasks"
    matches = [
        f for f in tasks_dir.glob("*.json")
        if f.name != ".gitkeep" and f.stem.startswith(task_id)
    ]

    if not matches:
        console.print(f"[red]No task found with ID prefix '{task_id}'.[/red]")
        raise typer.Exit(1)
    if len(matches) > 1:
        console.print(f"[red]Ambiguous prefix — {len(matches)} matches:[/red]")
        for m in matches:
            console.print(f"  {m.stem[:8]}")
        console.print("Use a longer prefix.")
        raise typer.Exit(1)

    task_file = matches[0]
    full_id = task_file.stem

    try:
        task_data = json.loads(task_file.read_text())
    except (json.JSONDecodeError, OSError) as e:
        console.print(f"[red]Could not read task file:[/red] {e}")
        raise typer.Exit(1)

    owner = task_data.get("orchestrator")
    if owner != handle and not force:
        console.print(
            f"[red]Task {full_id[:8]} was submitted by '{owner}', not you "
            f"('{handle}').[/red]"
        )
        console.print("  Pass --force to cancel it anyway.")
        raise typer.Exit(1)

    removed = []
    for subdir in ("tasks", "claims", "results"):
        path = coord_local / subdir / f"{full_id}.json"
        if path.exists():
            path.unlink()
            removed.append(subdir)

    if not removed:
        console.print("[yellow]Nothing to remove.[/yellow]")
        return

    _log.info("cancelling task %s (removed: %s)", full_id[:8], ",".join(removed))
    git.add_all(coord_local)
    git.commit(coord_local, f"tauke: cancel task {full_id[:8]}")
    push = git.push(coord_local)
    if push.returncode != 0:
        console.print(f"[red]Push failed:[/red] {push.stderr.strip()[:200]}")
        console.print("  The coord branch may have moved — pull and retry.")
        raise typer.Exit(1)

    console.print(
        f"[green]Cancelled task {full_id[:8]}[/green] — removed: "
        f"{', '.join(removed)}"
    )
