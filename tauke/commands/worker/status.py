"""tauke worker status — show local worker info."""

from rich.console import Console
from tauke.lib.config import identity, WORKER_PID_FILE, projects
from tauke.lib.token_tracker import get_usage

console = Console()


def worker_status():
    """Show your local worker status and token usage."""
    ident = identity()
    handle = ident["handle"]
    worker = ident.get("worker", {})

    used, cap = get_usage()
    remaining = max(0, cap - used)

    console.print(f"[bold]Worker: {handle}[/bold]")
    console.print(f"  Daily cap     : {cap:,} tokens")
    console.print(f"  Used today    : {used:,} tokens")
    remaining_str = f"[green]{remaining:,}[/green]" if remaining > 5_000 else f"[red]{remaining:,}[/red]"
    console.print(f"  Remaining     : {remaining_str} tokens")

    allowed = worker.get("allowed_orchestrators", [])
    console.print(f"  Allowlist     : {', '.join(allowed) if allowed else '[dim]empty[/dim]'}")

    running = WORKER_PID_FILE.exists()
    if running:
        pid = WORKER_PID_FILE.read_text().strip()
        console.print(f"  Daemon        : [green]running[/green] (PID {pid})")
    else:
        console.print(f"  Daemon        : [dim]stopped[/dim]")

    proj_list = projects()
    if proj_list:
        console.print(f"  Projects      : {len(proj_list)} registered")
        for p in proj_list:
            console.print(f"    [dim]{p['coord_repo']}[/dim]")
    else:
        console.print("  Projects      : [dim]none registered[/dim]")
