#!/usr/bin/env python3
"""Contexierge — the concierge for Claude Code's context.

Inspired by Context Language Models (Shao et al., arXiv 2609.37725): the model edits its own context (delete,
rewrite, condense) instead of relying on a summary written by the harness. Claude Code does not let the model delete
earlier tool results, but it does allow injecting context right after every compaction (hook `SessionStart`, matcher
`compact`). So: the harness decides *when*, the model decides *what*.

Claude keeps a per-session notebook at `~/.claude/contexierge/<session-id>.md` (rewrite, don't append; see the
`context-notebook` skill). After every compaction this hook injects it verbatim and marks it as taking precedence over
the automatic summary. If there is no notebook yet, it injects a short instruction to create one. On normal startup
nothing is injected — the start prompt stays minimal.

Usage:
    contexierge.py            hook mode: reads the hook JSON from stdin, writes the hook response to stdout
    contexierge.py --path     notebook path for this session (from CLAUDE_CODE_SESSION_ID)
Log (timestamp, session prefix, size only — never content): ~/.claude/contexierge/log.jsonl
Override the directory with CONTEXIERGE_DIR.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

MAX_CHARS = 16_000
_SAFE = re.compile(r"[^A-Za-z0-9_-]")


def directory() -> Path:
    return Path(os.environ.get("CONTEXIERGE_DIR") or Path.home() / ".claude" / "contexierge")


def notebook_path(session: str) -> Path:
    return directory() / f"{_SAFE.sub('', session)[:80] or 'no-session'}.md"


def log(entry: dict) -> None:
    try:
        directory().mkdir(parents=True, exist_ok=True)
        with (directory() / "log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **entry}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def response(event: dict) -> dict | None:
    """Hook response for a SessionStart event, or None (inject nothing)."""
    if event.get("hook_event_name") != "SessionStart" or event.get("source") != "compact":
        return None
    session = str(event.get("session_id") or "")
    path = notebook_path(session)
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        text = ""
    if text:
        truncated = len(text) > MAX_CHARS
        body = text[:MAX_CHARS] + (
            "\n\n[… truncated: notebook exceeds 16,000 characters — condense it the next time you update it]"
            if truncated else ""
        )
        context = (
            f"Context notebook for this session (kept by you, {path}). Where it and the automatic summary disagree, "
            f"the notebook wins. Keep maintaining it: rewrite, don't append.\n\n{body}"
        )
        log({"session": session[:8], "source": "compact", "chars": len(text), "truncated": truncated})
    else:
        context = (
            f"Context notebook missing ({path}). Create it now (skill context-notebook): the user's requests in their "
            "own words, decisions and approvals, state of each thread, running background work, open steps, pitfalls "
            "— at most ~150 lines, no tool output."
        )
        log({"session": session[:8], "source": "compact", "chars": 0})
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}


def main(argv: list[str]) -> int:
    if argv[1:2] == ["--path"]:
        print(notebook_path(os.environ.get("CLAUDE_CODE_SESSION_ID", "")))
        return 0
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # a hook must never disturb the session
    out = response(event if isinstance(event, dict) else {})
    if out is not None:
        print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
