"""
Tauke CLI entry point.
All commands are registered here.
"""

import typer
from rich.console import Console

from tauke.commands.setup import setup
from tauke.commands.init import init
from tauke.commands.run import run
from tauke.commands.pull import pull
from tauke.commands.status import status
from tauke.commands.log import log
from tauke.commands.install_skill import install_skill
from tauke.commands.worker.start import start as worker_start
from tauke.commands.worker.stop import stop as worker_stop
from tauke.commands.worker.set_cap import set_cap as worker_set_cap
from tauke.commands.worker.allow import allow as worker_allow
from tauke.commands.worker.status import worker_status

app = typer.Typer(
    name="tauke",
    help="Distributed Claude Code token sharing for teams.",
    add_completion=False,
    no_args_is_help=True,
)

worker_app = typer.Typer(help="Manage the local worker daemon.", no_args_is_help=True)
app.add_typer(worker_app, name="worker")

# Top-level commands
app.command("setup")(setup)
app.command("init")(init)
app.command("run")(run)
app.command("pull")(pull)
app.command("status")(status)
app.command("log")(log)
app.command("install-skill")(install_skill)

# Worker sub-commands
worker_app.command("start")(worker_start)
worker_app.command("stop")(worker_stop)
worker_app.command("set-cap")(worker_set_cap)
worker_app.command("allow")(worker_allow)
worker_app.command("status")(worker_status)
