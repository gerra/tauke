"""tauke log — list submitted tasks and their statuses."""

import json
import typer
from datetime import datetime, timezone
from rich.console import Console
from rich.table import Table

from tauke.lib.config import identity, coord_info
from tauke.lib.coord_repo import ensure_coord

console = Console()


def log(
    all_users: bool = typer.Option(False, "--all", "-a", help="Show tasks from all users, not just yours"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max number of tasks to show"),
):
    """Show task history."""
    ident = identity()
    handle = ident["handle"]
    remote_url, coord_branch = coord_info()
    coord_local = ensure_coord(remote_url, coord_branch)

    tasks = _load_tasks(coord_local)
    results = _load_results(coord_local)
    claims = _load_claims(coord_local)

    # Filter
    if not all_users:
        tasks = [t for t in tasks if t.get("orchestrator") == handle]

    # Sort newest first
    tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    tasks = tasks[:limit]

    if not tasks:
        console.print("[dim]No tasks found.[/dim]")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim")
    table.add_column("Status")
    table.add_column("Worker")
    table.add_column("Prompt", max_width=50)
    table.add_column("Created")

    for task in tasks:
        task_id = task.get("id", "?")
        short_id = task_id[:8]
        result = results.get(task_id)
        claim = claims.get(task_id)

        if result:
            status = result.get("status", "?")
            status_str = {
                "completed": "[green]completed[/green]",
                "rate_limited": "[yellow]rate_limited[/yellow]",
                "error": "[red]error[/red]",
            }.get(status, f"[dim]{status}[/dim]")
            worker = result.get("worker", "?")
        elif claim:
            status_str = "[cyan]in_progress[/cyan]"
            worker = claim.get("worker", "?")
        else:
            status_str = "[dim]pending[/dim]"
            worker = "—"

        prompt = task.get("prompt", "")[:50]
        created = _fmt_time(task.get("created_at", ""))

        table.add_row(short_id, status_str, worker, prompt, created)

    console.print(table)


def _load_tasks(coord_local) -> list[dict]:
    return _load_json_dir(coord_local / "tasks")


def _load_results(coord_local) -> dict:
    results = {}
    for item in _load_json_dir(coord_local / "results"):
        results[item.get("task_id", "")] = item
    return results


def _load_claims(coord_local) -> dict:
    claims = {}
    for item in _load_json_dir(coord_local / "claims"):
        claims[item.get("task_id", "")] = item
    return claims


def _load_json_dir(path) -> list[dict]:
    from pathlib import Path
    items = []
    if not path.exists():
        return items
    for f in Path(path).glob("*.json"):
        if f.name == ".gitkeep":
            continue
        try:
            items.append(json.loads(f.read_text()))
        except Exception:
            pass
    return items


def _fmt_time(iso: str) -> str:
    if not iso:
        return "?"
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - dt
        secs = int(delta.total_seconds())
        if secs < 60:
            return f"{secs}s ago"
        if secs < 3600:
            return f"{secs // 60}m ago"
        if secs < 86400:
            return f"{secs // 3600}h ago"
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return iso[:16]
