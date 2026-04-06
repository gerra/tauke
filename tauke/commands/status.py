"""tauke status — show worker availability and token budgets."""

import json
import typer
from datetime import datetime, timedelta, timezone
from rich.console import Console
from rich.table import Table

from tauke.lib.config import coord_info
from tauke.lib.coord_repo import ensure_coord

console = Console()


def status():
    """Show available workers and their token budgets."""
    try:
        remote_url, coord_branch = coord_info()
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    console.print("Pulling coordination repo...")
    coord_local = ensure_coord(remote_url, coord_branch)

    all_workers = _load_all_workers(coord_local)

    if not all_workers:
        console.print("[yellow]No workers registered yet.[/yellow]")
        console.print(
            "Teammates can join by running "
            "[cyan]tauke worker start[/cyan] in this project."
        )
        return

    table = Table(title="Tauke Workers", show_header=True, header_style="bold cyan")
    table.add_column("Handle", style="bold")
    table.add_column("Status")
    table.add_column("Tokens used")
    table.add_column("Daily cap")
    table.add_column("Remaining")
    table.add_column("Last seen")

    now = datetime.now(timezone.utc)
    for w in sorted(all_workers, key=lambda x: x.get("handle", "")):
        last_seen_str = w.get("last_seen", "")
        age = _age_str(last_seen_str, now)
        online = _is_online(last_seen_str, now)
        status_str = "[green]online[/green]" if online else "[dim]offline[/dim]"

        used = w.get("tokens_used_today", 0)
        cap = w.get("daily_cap", 0)
        remaining = max(0, cap - used)
        if remaining > 5_000:
            remaining_str = f"[green]{remaining:,}[/green]"
        else:
            remaining_str = f"[red]{remaining:,}[/red]"

        table.add_row(
            w.get("handle", "?"),
            status_str,
            f"{used:,}",
            f"{cap:,}",
            remaining_str,
            age,
        )

    console.print(table)


def _load_all_workers(coord_local) -> list[dict]:
    workers_dir = coord_local / "workers"
    result = []
    for f in workers_dir.glob("*.json"):
        if f.name == ".gitkeep":
            continue
        try:
            result.append(json.loads(f.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
    return result


def _is_online(last_seen_str: str, now: datetime) -> bool:
    if not last_seen_str:
        return False
    try:
        last_seen = datetime.fromisoformat(last_seen_str)
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        return (now - last_seen) < timedelta(minutes=2)
    except ValueError:
        return False


def _age_str(last_seen_str: str, now: datetime) -> str:
    if not last_seen_str:
        return "never"
    try:
        last_seen = datetime.fromisoformat(last_seen_str)
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        secs = int((now - last_seen).total_seconds())
        if secs < 60:
            return f"{secs}s ago"
        if secs < 3600:
            return f"{secs // 60}m ago"
        return f"{secs // 3600}h ago"
    except ValueError:
        return "?"
