<p align="center">
  <img src="assets/contexierge.webp" width="320" alt="Contexierge: an anime catgirl concierge serving a floppy disk on a silver tray">
</p>

# Contexierge

*Context + concierge* — a small Claude Code plugin that lets Claude look after its own context.
Your context, served back on a silver tray after every compaction.

Long Claude Code sessions eventually get compacted: the harness replaces the conversation with an automatic summary.
That summary is written in a hurry and loses things — the exact wording of a request, a decision made two hours ago,
the PID of the job still running in the background, the trap you already fell into once.

Contexierge flips the responsibility: **the harness decides *when* to compact, Claude decides *what* survives.**
Claude keeps a short notebook for the session; after every compaction a hook puts that notebook back into context
verbatim, ahead of the summary.

## How it works

1. **Skill `context-notebook`** — tells Claude when and how to keep a notebook at
   `~/.claude/contexierge/<session-id>.md`: requests, decisions, where the work lives, state per thread, background
   jobs, pitfalls. At most ~150 lines and 9,000 characters, rewritten at milestones rather than appended to.
2. **Hook `SessionStart` (matcher `compact`)** — runs right after each compaction and injects the notebook as
   additional context, marked as taking precedence over the automatic summary where they disagree.
   If no notebook exists yet, it injects a two-line instruction to create one.
3. **One day, one book.** The first session start of a new day moves every notebook from earlier days (and the log)
   to `~/.claude/contexierge/archive/<day>/`. The folder only ever holds today's books; nothing is deleted.
   A day begins at 04:00 by default, so late-night work still counts to the day before
   (`CONTEXIERGE_DAY_START_HOUR=0` for midnight). If a session runs across the day change, its next compaction
   injects the archived notebook and asks Claude to write a fresh, tidy one — carrying over only what is still open.
4. **Nothing injected on normal startup.** For `startup`, `resume` and `clear` the hook only does the daily tidy-up and
   stays silent; your start prompt stays minimal.

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
| `~/.claude/contexierge/log.jsonl` | one line per compaction or daily archive: time, first 8 chars of the session id, notebook size, files archived — never content |
| `~/.claude/contexierge/archive/<day>/` | notebooks and log of earlier days, moved there on the first session start of a new day |

Everything stays local. Set `CONTEXIERGE_DIR` to use a different directory. The archive is never pruned; delete old
day folders whenever you like.
Notebooks over 9,000 characters are truncated on injection, with a note telling Claude to condense. The limit sits
below Claude Code's own: hook context over 10,000 characters is moved into a file and shown only as a short preview.

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

MIT. The mascot was generated with [Qwen-Image](https://huggingface.co/Qwen/Qwen-Image) (Apache 2.0).
