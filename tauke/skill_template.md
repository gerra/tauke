Delegate the current task to an available teammate's Claude instance using tauke.

Run: `tauke run "$ARGUMENTS"` from the project root directory (use the `Bash` tool).

If no arguments are provided, summarize what you were asked to do and use that as the prompt.

After running, poll every 10 seconds by checking output. When the task completes, report back:
- The summary of what the worker did
- The result branch name (e.g. `tauke/result-<id>`) to merge with `tauke pull`

If no workers are available, inform the user and suggest running the task locally.
