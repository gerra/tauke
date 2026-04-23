# Tauke — codebase guide for agents

## What this project does

Tauke lets teammates share Claude Code token quota. When you hit your daily limit,
`tauke run "<prompt>"` delegates the task to an available teammate's Claude instance.
Results come back as a git branch you merge with `tauke pull`.

No central server. A dedicated orphan branch (`tauke-coord`) in the project repo
acts as the message bus.

## Tech stack

- Python 3.10+, `typer` CLI, `rich` for output
- Standard library only (subprocess, json, pathlib, uuid) — no extra runtime deps
- Entry point: `tauke = tauke.cli:app` (see `pyproject.toml`)

## Directory structure

```
tauke/
  cli.py                     # Typer app — registers all commands
  _daemon.py                 # Background daemon entry: python -m tauke._daemon

  commands/
    setup.py                 # tauke setup <handle>
    init.py                  # tauke init — creates tauke-coord branch
    run.py                   # tauke run "<prompt>" — submit + poll
    pull.py                  # tauke pull — merge result branch
    status.py                # tauke status — worker table
    log.py                   # tauke log — task history
    install_skill.py         # tauke install-skill — write /tauke to .claude/commands/
    worker/
      start.py               # register project + start daemon
      stop.py                # stop daemon (SIGTERM via PID file)
      allow.py               # add trusted orchestrator
      set_cap.py             # set daily token cap
      status.py              # show local daemon + token usage

  lib/
    config.py                # load ~/.tauke/identity.json + .tauke/config.json
    coord_repo.py            # all reads/writes on the tauke-coord branch
    git_helpers.py           # thin wrappers around git CLI subprocess calls
    task.py                  # task creation + polling loop
    worker.py                # daemon loop — claims tasks, runs claude, pushes results
    claude_runner.py         # runs `claude -p`, measures tokens via stats-cache diff
    token_tracker.py         # reads ~/.claude/stats-cache.json for real token usage
    logger.py                # central logger → ~/.tauke/tauke.log (rotating 5 MB × 3)

  skill_template.md          # bundled content for the /tauke Claude Code slash command
```

## Key files to know

| File | What to read when… |
|------|-------------------|
| `lib/config.py` | changing how config is loaded/stored |
| `lib/coord_repo.py` | changing task/claim/result/worker JSON ops |
| `lib/worker.py` | changing the daemon poll loop or task execution |
| `lib/claude_runner.py` | changing how `claude -p` is invoked |
| `lib/token_tracker.py` | changing how token usage is measured |
| `lib/logger.py` | changing log format, rotation, or log file location |

## Config split

**Machine-local** (`~/.tauke/identity.json`) — never committed:
```json
{ "handle": "alice", "worker": { "daily_cap": 80000, "allowed_orchestrators": ["bob"] } }
```

**Per-project** (`.tauke/config.json`) — committed to the project repo:
```json
{ "coord_branch": "tauke-coord" }
```

`config.coord_info()` merges both and returns `(remote_url, coord_branch)`.

## Machine-local runtime files

All under `~/.tauke/`:

| File/dir | Purpose |
|----------|---------|
| `identity.json` | handle, daily cap, allowlist |
| `projects.json` | list of repos the worker daemon polls |
| `worker.pid` | daemon PID (deleted on clean shutdown) |
| `tauke.log` | all logs — rotating 5 MB × 3 files |
| `coord-repos/` | local clones of project repos, checked out on tauke-coord branch |
| `workspaces/` | temporary task clones (auto-deleted after task completes) |

## Coordination branch layout

The `tauke-coord` orphan branch (in the project repo) — append-only log
of task lifecycle events:
```
tasks/{uuid}.json     # orchestrator writes; status: pending
claims/{uuid}.json    # worker writes to claim (atomic via git push)
results/{uuid}.json   # worker writes outcome + result_branch
```

Heartbeats live on **per-worker orphan branches** `tauke-hb/<handle>`, one
`worker.json` per branch, rewritten every 30s via `commit --amend` +
`push --force`. Each worker owns its own ref — force-pushes never race
with other workers, and the branch stays at exactly one commit forever
(no history growth from heartbeat churn).

`list_available_workers(coord_local)` fetches `refs/heads/tauke-hb/*` from
origin and reads each `worker.json` via `git show`.

`write_worker_heartbeat(coord_local, ...)` operates on a separate local
clone at `~/.tauke/coord-repos/<project>-hb-<handle>/` to avoid switching
branches in the shared coord working tree.

## Token tracking

`lib/token_tracker.py` reads `~/.claude/stats-cache.json` — the same file
that powers `/usage` in Claude Code. Token counts are exact; no stdout parsing.

To measure tokens for a single `claude -p` call: snapshot before, run, snapshot after,
subtract. See `lib/claude_runner.py`.

## Logging

All log output goes to `~/.tauke/tauke.log`. To follow it live:
```bash
tail -f ~/.tauke/tauke.log
```

Log levels:
- `DEBUG` — every git op, poll cycle details, token snapshots
- `INFO` — task lifecycle events, daemon start/stop, heartbeats
- `WARNING` — rate limits, stale workers, pull failures
- `ERROR` — push failures, unhandled exceptions

Logger names map to modules: `tauke.worker`, `tauke.coord_repo`, `tauke.git`,
`tauke.claude_runner`, `tauke.token_tracker`, `tauke.cmd.run`.

## Common workflows

### Run a task (orchestrator)
```
tauke run "prompt"
  → coord_info() reads remote URL + coord branch
  → ensure_coord() pulls tauke-coord branch
  → list_available_workers() checks workers/*.json
  → create_task() + submit_and_wait() polls results/*.json every 10s
  → tauke pull merges tauke/result-{uuid} into current branch
```

### Worker daemon
```
tauke worker start
  → registers project in ~/.tauke/projects.json
  → spawns python -m tauke._daemon in background
  → daemon polls every 30s per project:
      pull tauke-coord → heartbeat → scan tasks → try_claim → execute → write result
```

### Adding tauke to an existing project
```bash
cd ~/projects/my-project
tauke init                          # creates tauke-coord branch, writes .tauke/config.json
git add .tauke/config.json && git push
tauke install-skill                 # writes .claude/commands/tauke.md
```

## Conventions

- All git operations go through `lib/git_helpers.py` — never call subprocess git directly
- All log calls use `from tauke.lib.logger import get; _log = get("module_name")`
- JSON files in the coord branch use 2-space indent (`json.dumps(..., indent=2)`)
- Task IDs are UUIDs; use `[:8]` for display in logs and UI
- `check=False` on git push calls — push rejection is normal (race condition handling)
