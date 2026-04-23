"""tauke run "<prompt>" — delegate a task to an available teammate."""

import typer
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from typing import Optional

from tauke.lib.config import identity, coord_info
from tauke.lib.coord_repo import ensure_coord, list_available_workers
from tauke.lib.task import create_task, submit_and_wait
from tauke.lib import git_helpers as git
from tauke.lib.logger import get
from tauke.commands.pull import merge_branch_into_head

console = Console()
_log = get("cmd.run")


def run(
    prompt: str = typer.Argument(..., help="The task prompt to delegate"),
    files: Optional[str] = typer.Option(None, "--files", "-f", help="Comma-separated context files to highlight"),
    timeout: int = typer.Option(900, "--timeout", "-t", help="Seconds to wait for result (default: 900)"),
):
    """Delegate a Claude task to an available teammate."""
    ident = identity()
    handle = ident["handle"]
    remote_url, coord_branch = coord_info()

    _log.info("tauke run — user=%s coord=%s branch=%s", handle, remote_url, coord_branch)

    console.print("Pulling coordination repo...")
    coord_local = ensure_coord(remote_url, coord_branch)

    workers = list_available_workers(coord_local)
    if not workers:
        _log.warning("no available workers found")
        console.print("[yellow]No workers are currently available.[/yellow]")
        console.print("Run the task locally with:")
        console.print(f"  [cyan]claude -p {prompt!r}[/cyan]")
        raise typer.Exit(1)

    best = workers[0]
    _log.info(
        "routing to worker %s (%d tokens remaining)",
        best['handle'], best['remaining_tokens'],
    )
    console.print(
        f"[green]Worker available:[/green] [bold]{best['handle']}[/bold] "
        f"({best['remaining_tokens']:,} tokens remaining)"
    )

    try:
        repo_url = git.current_remote_url()
        branch = git.current_branch()
        commit = git.current_commit()
        _log.info("project context: repo=%s branch=%s commit=%s", repo_url, branch, commit[:8])
    except OSError as e:
        _log.error("could not read git info: %s", e)
        console.print(f"[red]Could not read git info:[/red] {e}")
        raise typer.Exit(1)

    context_files = [f.strip() for f in files.split(",")] if files else []

    task = create_task(
        prompt=prompt,
        orchestrator=handle,
        repo_url=repo_url,
        branch=branch,
        commit=commit,
        context_files=context_files,
    )

    console.print(f"Submitting task [dim]{task['id'][:8]}[/dim]...")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        prog_task = progress.add_task("Waiting for worker to pick up task...", total=None)

        def on_waiting(elapsed: float):
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            progress.update(prog_task, description=f"Working... [{mins:02d}:{secs:02d}]")

        result = submit_and_wait(
            task=task,
            coord_local=coord_local,
            poll_interval=10,
            timeout=timeout,
            on_waiting=on_waiting,
        )

    if result is None:
        _log.error("timed out waiting for task %s after %ds", task['id'][:8], timeout)
        console.print(f"[red]Timed out after {timeout}s.[/red] Task ID: {task['id']}")
        console.print("Check again later with:")
        console.print(f"  [cyan]tauke pull {task['id']}[/cyan]")
        raise typer.Exit(1)

    _log.info(
        "task %s result: status=%s worker=%s tokens=%d",
        task['id'][:8], result.get('status'), result.get('worker'), result.get('tokens_used', 0),
    )

    _print_result(result)


def _print_result(result: dict):
    status = result.get("status", "unknown")
    worker = result.get("worker", "?")
    summary = result.get("summary", "")
    branch = result.get("result_branch", "")
    tokens = result.get("tokens_used", 0)

    if status == "completed":
        console.print(f"\n[green bold]Done![/green bold] (worker: {worker}, {tokens:,} tokens used)")
        if summary:
            console.print(f"  Summary: {summary}")
        if branch:
            console.print(f"Auto-merging [cyan]{branch}[/cyan] into current branch...")
            ok, err = merge_branch_into_head(branch, worker)
            if ok:
                console.print("[green]Merged![/green]")
            else:
                console.print(f"[yellow]Auto-merge skipped:[/yellow] {err}")
                console.print(f"  Branch is available: [cyan]{branch}[/cyan]")
                console.print(f"  To merge manually: [cyan]tauke pull[/cyan]")
    elif status == "rate_limited":
        console.print(f"\n[yellow]Worker {worker} hit their rate limit.[/yellow]")
        console.print("Re-queue with [cyan]tauke run[/cyan] to try another worker.")
    else:
        console.print(f"\n[red]Task {status}.[/red] Worker: {worker}")
        if result.get("error"):
            console.print(f"  Error: {result['error']}")
