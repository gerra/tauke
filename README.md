# tauke

Distributed Claude Code token sharing for teams. When you hit your daily token limit, delegate tasks to a teammate's Claude instance and get results back via git.

## How it works

1. You run `tauke run "fix the auth bug"` — tauke finds an available teammate with tokens
2. Their machine picks up the task, runs `claude -p` on a fresh clone of your repo, pushes the result to a branch
3. You `tauke pull` to merge it in

No central server. Uses a private git repo as the message bus.

## Install

```bash
pip install git+https://github.com/gerra/tauke.git
# or, once published to PyPI:
pip install tauke
# or:
pipx install tauke
```

Requires Python 3.10+ and the [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed.

---

## Setup

### Project owner (once per project)

```bash
# 1. Set up your machine identity (once per machine)
tauke setup your-github-handle

# 2. In your project directory, initialize tauke
cd ~/projects/my-project
tauke init                        # auto-creates a private GitHub repo via `gh` CLI
# OR: tauke init --repo git@github.com:org/my-project-coord.git

# 3. Commit the project config
git add .tauke/config.json
git commit -m "add tauke delegation"
git push

# 4. Install the /tauke Claude Code skill (optional but recommended)
tauke install-skill
git add .claude/commands/tauke.md
git commit -m "add tauke skill"
git push
```

### Teammates (once per machine, then once per project)

```bash
# Machine setup (only needed once ever)
pip install tauke
tauke setup alice

# Per-project setup (after git pull)
git pull                          # .tauke/config.json is already there
tauke worker allow germanberezko  # trust whose tasks to accept
tauke worker set-cap 60000        # optional, defaults to 50,000
tauke worker start                # start accepting tasks
```

---

## Daily usage

### Delegating a task

```bash
# From the terminal
tauke run "refactor the auth module to use JWT"

# With context files highlighted
tauke run "fix the token expiry bug" --files src/auth/login.py,src/auth/token.py

# From inside Claude Code
/tauke fix the token expiry bug
```

### Getting results back

```bash
# tauke run automatically polls and prints the result branch when done
# Then merge it:
tauke pull           # merges the latest completed task
tauke pull abc12345  # merge a specific task by ID prefix
```

### Checking status

```bash
tauke status    # see who's online and their token budgets
tauke log       # see your task history
tauke log --all # see all team tasks
```

---

## Worker commands

```bash
tauke worker start          # start the polling daemon
tauke worker stop           # stop the daemon
tauke worker status         # show local usage + daemon status
tauke worker set-cap 80000  # set daily token cap
tauke worker allow alice    # allow alice to delegate to you
```

---

## Token cap mechanics

- Workers self-declare their daily cap (`tauke worker set-cap`)
- Caps reset at midnight
- Token counts are parsed from `claude -p` output and tracked locally
- Orchestrators only route to workers with >5,000 tokens remaining
- If a worker hits their limit mid-task, the result is marked `rate_limited` and you can re-queue

---

## Project structure

```
.tauke/
  config.json          ← coordination repo URL (commit this to git)
.claude/
  commands/
    tauke.md           ← /tauke slash command (commit this to git)
```

Machine-local files (never committed):
```
~/.tauke/
  identity.json        ← your handle + worker config
  projects.json        ← list of registered project coord repos
  worker.pid           ← daemon PID
  tauke.log            ← all logs (rotating, 5 MB × 3)
  coord-repos/         ← local clones of coordination repos
  workspaces/          ← temporary task workspaces (auto-cleaned)
```

---

## Debugging

Everything tauke does — CLI commands and the worker daemon — writes to a single log file at `~/.tauke/tauke.log` on your machine. To watch it live:

```bash
tail -f ~/.tauke/tauke.log
```

If something goes wrong, share the last ~100 lines:

```bash
tail -n 100 ~/.tauke/tauke.log
```

Logs rotate automatically (5 MB × 3 files), so they won't grow unbounded.

---

## Requirements

- Python 3.10+
- Claude Code CLI (`claude`) installed and authenticated
- `git` CLI
- All teammates must have collaborator access to the project repo (to push result branches)
- `gh` CLI (optional — only needed for `tauke init` auto-create mode)
