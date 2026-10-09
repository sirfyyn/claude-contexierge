---
name: context-notebook
description: Load for long or branching work (several threads, background jobs, sessions over an hour, context getting full, before or after a compaction). Keep your own session notebook so that what matters survives compaction verbatim instead of depending on the automatic summary.
---

# Context notebook

The harness decides **when** context gets compacted; you decide **what** survives. Write it yourself — short,
rewritten rather than appended, stale parts deleted. After every compaction the Contexierge hook injects your notebook
verbatim, and it takes precedence over the automatic summary.

## Where

`~/.claude/contexierge/<session-id>.md`, where the session id is `$CLAUDE_CODE_SESSION_ID`.
Print the exact path with:

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/contexierge.py" --path
```

(or `echo ~/.claude/contexierge/$CLAUDE_CODE_SESSION_ID.md`). Write it with the Write/Edit tools.

## When

- Start it as soon as a task has more than one thread, background work, or will clearly run long.
- Update it at milestones: a thread finished, a new decision or approval, a new request, a background job started or
  done. Rewrite — collapse finished work to one line, delete what was revoked.
- If a compaction just happened and the hook said the notebook is missing, create it right away.

## What goes in (≤ ~150 lines)

- The user's requests, in their own words where wording matters.
- Decisions and approvals (who, what, when).
- Where the work lives: directory, worktree, branch, what is committed or pushed.
- State of each thread and the next concrete step.
- Running background work: task ids, PIDs, URLs, what to check.
- Pitfalls discovered in this session (commands that failed and why, traps to avoid).

## What stays out

- Tool output, file contents, logs — keep facts, not dumps.
- Rules already in CLAUDE.md, memory, or skills.
- Anything that should outlive the session — put that in memory or the repo's docs instead.

## Keeping context lean in general

- Push noisy work (broad searches, log trawls, inventories) into subagents and keep only the findings.
- Read narrowly (`grep -n`, line ranges, offset/limit); don't read the same file twice — note the fact instead.
