"""tauke install-skill — write the /tauke Claude Code slash command."""

import importlib.resources
import typer
from pathlib import Path
from rich.console import Console

from tauke.lib.config import _find_git_root

console = Console()


def install_skill(
    global_: bool = typer.Option(False, "--global", "-g", help="Install globally in ~/.claude/commands/"),
):
    """Install the /tauke slash command for Claude Code."""
    if global_:
        dest_dir = Path.home() / ".claude" / "commands"
    else:
        git_root = _find_git_root()
        dest_dir = git_root / ".claude" / "commands"

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "tauke.md"

    # Read the bundled template
    template = _read_template()
    dest.write_text(template)

    scope = "globally" if global_ else f"in {dest.relative_to(Path.home() if global_ else _find_git_root())}"
    console.print(f"[green]Skill installed {scope}:[/green] {dest}")
    console.print()
    console.print("Usage inside Claude Code:")
    console.print("  [cyan]/tauke fix the auth bug in login.py[/cyan]")

    if not global_:
        console.print()
        console.print("To commit to the project:")
        console.print("  [cyan]git add .claude/commands/tauke.md && git commit -m 'add tauke skill'[/cyan]")


def _read_template() -> str:
    try:
        ref = importlib.resources.files("tauke").joinpath("skill_template.md")
        return ref.read_text(encoding="utf-8")
    except Exception:
        # Fallback: read relative to this file
        here = Path(__file__).parent.parent
        return (here / "skill_template.md").read_text()
