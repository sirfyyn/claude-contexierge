# Contexierge

*Context + concierge* — a small Claude Code plugin that lets Claude look after its own context.

Long Claude Code sessions eventually get compacted: the harness replaces the conversation with an automatic summary.
That summary is written in a hurry and loses things — the exact wording of a request, a decision made two hours ago,
the PID of the job still running in the background, the trap you already fell into once.

Contexierge flips the responsibility: **the harness decides *when* to compact, Claude decides *what* survives.**
Claude keeps a short notebook for the session; after every compaction a hook puts that notebook back into context
verbatim, ahead of the summary.

## How it works

1. **Skill `context-notebook`** — tells Claude when and how to keep a notebook at
   `~/.claude/contexierge/<session-id>.md`: requests, decisions, where the work lives, state per thread, background
   jobs, pitfalls. At most ~150 lines, rewritten at milestones rather than appended to.
2. **Hook `SessionStart` (matcher `compact`)** — runs right after each compaction and injects the notebook as
   additional context, marked as taking precedence over the automatic summary where they disagree.
   If no notebook exists yet, it injects a two-line instruction to create one.
3. **Nothing on normal startup.** The hook stays silent for `startup`, `resume` and `clear`; your start prompt stays
   minimal.

The idea comes from *Context Language Models* (Shao et al., arXiv [2609.37725](https://arxiv.org/abs/2609.37725)):
models that edit their own context — delete, rewrite, condense — instead of relying on a harness summary.
Claude Code does not let a model delete earlier tool results, but it does let a hook inject context after compaction.
Contexierge uses exactly that seam. No code from the paper is used.

## Install

```text
/plugin marketplace add sirfyyn/claude-contexierge
/plugin install contexierge@contexierge
```

Requires `python3` on your `PATH` (standard library only).

## Files and privacy

| Path | What |
| --- | --- |
| `~/.claude/contexierge/<session-id>.md` | the notebook Claude writes for that session |
| `~/.claude/contexierge/log.jsonl` | one line per compaction: time, first 8 chars of the session id, notebook size — never content |

Everything stays local. Set `CONTEXIERGE_DIR` to use a different directory.
Notebooks over 16,000 characters are truncated on injection, with a note telling Claude to condense.

Print this session's notebook path from a Claude Code shell:

```sh
python3 ~/.claude/plugins/cache/contexierge/contexierge/*/hooks/contexierge.py --path
```

## Tips

- For best results, also nudge Claude in your `CLAUDE.md`: *"In long sessions, keep the context notebook (skill
  context-notebook)."*
- Ask Claude to update the notebook before you step away or before a big context-heavy step.
- The notebook is per session. Anything that should outlive the session belongs in memory or your repo docs.

## Development

```sh
python3 -m pytest tests/
```

Test the plugin locally without installing: `claude --plugin-dir ./plugins/contexierge`.

## License

MIT
