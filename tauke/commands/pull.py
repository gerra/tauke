"""tauke pull [task-id] — fetch and merge the result branch."""

import json
import typer
from pathlib import Path
from rich.console import Console

from tauke.lib.config import identity, coord_info
from tauke.lib.coord_repo import ensure_coord, read_result
from tauke.lib import git_helpers as git

console = Console()


def pull(
    task_id: str = typer.Argument(None, help="Task ID (or prefix). Defaults to the latest completed task."),
):
    """Fetch and merge the result branch from a completed task."""
    ident = identity()
    handle = ident["handle"]
    remote_url, coord_branch = coord_info()
    coord_local = ensure_coord(remote_url, coord_branch)

    if task_id:
        result = _find_result(coord_local, task_id)
    else:
        result = _latest_result(coord_local, handle)

    if not result:
        console.print("[red]No completed task found.[/red]")
        if task_id:
            console.print(f"  Looked for task ID starting with: {task_id}")
        raise typer.Exit(1)

    status = result.get("status")
    if status != "completed":
        console.print(f"[yellow]Task status is '{status}', not 'completed'.[/yellow]")
        raise typer.Exit(1)

    result_branch = result.get("result_branch")
    if not result_branch:
        console.print("[red]Result has no branch reference.[/red]")
        raise typer.Exit(1)

    console.print(f"Fetching branch [cyan]{result_branch}[/cyan]...")
    try:
        git.fetch(Path("."), "origin")
    except Exception as e:
        console.print(f"[red]git fetch failed:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"Merging [cyan]{result_branch}[/cyan] into current branch...")
    try:
        merge = git.run(["merge", f"origin/{result_branch}", "--no-ff", "-m",
                         f"tauke: merge result from {result.get('worker', '?')}"])
        if merge.returncode != 0:
            console.print("[red]Merge failed (conflicts?):[/red]")
            console.print(merge.stderr)
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Merge failed:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"\n[green]Merged successfully![/green]")
    console.print(f"  Worker  : {result.get('worker', '?')}")
    console.print(f"  Tokens  : {result.get('tokens_used', 0):,}")
    if result.get("summary"):
        console.print(f"  Summary : {result['summary']}")


def _find_result(coord_local: Path, task_id_prefix: str) -> dict | None:
    results_dir = coord_local / "results"
    for f in results_dir.glob("*.json"):
        if f.name == ".gitkeep":
            continue
        if f.stem.startswith(task_id_prefix):
            try:
                return json.loads(f.read_text())
            except Exception:
                pass
    return None


def _latest_result(coord_local: Path, handle: str) -> dict | None:
    """Find the most recent completed task submitted by this user."""
    tasks_dir = coord_local / "tasks"
    results_dir = coord_local / "results"

    my_task_ids = []
    for f in tasks_dir.glob("*.json"):
        if f.name == ".gitkeep":
            continue
        try:
            task = json.loads(f.read_text())
            if task.get("orchestrator") == handle:
                my_task_ids.append((task.get("created_at", ""), task["id"]))
        except Exception:
            pass

    my_task_ids.sort(reverse=True)

    for _, task_id in my_task_ids:
        result_path = results_dir / f"{task_id}.json"
        if result_path.exists():
            try:
                result = json.loads(result_path.read_text())
                if result.get("status") == "completed":
                    return result
            except Exception:
                pass
    return None
