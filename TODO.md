# Tauke — known gaps & things to implement

Real issues discovered while dogfooding, grouped by area. Keep this tight —
if something's in the code, delete it from here.

## Orchestrator UX

- [x] Warn when HEAD isn't pushed (uncommitted changes or local commits
  ahead of origin). Worker only sees pushed state.
- [ ] Offer to `git push` from `tauke run` instead of just warning.
- [ ] If all available workers are at/near their cap, say so explicitly
  instead of "no workers."
- [ ] Show which workers exist but were filtered out (offline, no allowlist,
  low budget) so the orchestrator knows who to ping.

## Worker resilience

- [ ] Clean up orphaned workspaces under `~/.tauke/workspaces/` on daemon
  start — crashed runs leave them behind.
- [ ] Detect SSH auth failures at `worker start` time and print a clear
  "set up SSH or use HTTPS" message instead of only hitting it at clone time.
- [ ] Heartbeat branch pruning — if a worker unregisters, their
  `tauke-hb/<handle>` ref sticks around forever.

## Task lifecycle

- [ ] `tauke cancel` leaves orphaned results if worker was already executing.
  Teach the daemon to drop its result if the task file is gone.
- [ ] Auto-requeue on `rate_limited` — currently the orchestrator sees the
  status and has to re-run manually.
- [ ] Task timeout on the worker side — a hung `claude -p` blocks the
  daemon for that project indefinitely.
- [ ] Tasks re-delivered if a worker claims and then crashes before writing
  a result (stale claim detection).

## Routing / fairness

- [ ] When multiple workers are available, pick by remaining tokens rather
  than alphabetical order.
- [ ] Per-orchestrator rate limits so one person can't drain a worker's
  whole daily cap in one session.

## Observability

- [ ] `tauke log` should filter by task id / orchestrator / status.
- [ ] Surface worker errors in `tauke status` (e.g. "last 3 tasks failed").
- [ ] Track p50/p95 task completion time somewhere visible.

## Security

- [ ] Allowlist is handle-based but handles aren't verified — any teammate
  with coord-repo push access can impersonate. Signed commits or a shared
  secret per project would help.
- [ ] Prompts are world-readable on the coord branch. Consider age/gpg
  encryption for sensitive tasks.
- [ ] `--allowedTools Read,Write,Edit,Glob,Grep,Bash` means a malicious
  prompt can shell out. Sandbox/container the worker eventually.

## Setup friction

- [ ] `tauke init` assumes push access to the project remote — explicit
  check + better error if the user only has read access.
- [ ] `tauke install-skill` should work from any subdirectory, not just
  the repo root.

## Nice-to-haves (not blocking)

- [ ] Multiple parallel tasks per worker.
- [ ] Web dashboard / TUI for live worker + queue state.
- [ ] Auto-detect local Claude rate limit and route to a worker without
  the user typing `tauke run`.
