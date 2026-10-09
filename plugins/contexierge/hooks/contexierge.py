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

Daily archive: the first session start of a new day moves every notebook (and the log) from earlier days to
`archive/<day>/`, so the directory only ever holds today's books. A day starts at CONTEXIERGE_DAY_START_HOUR
(default 4, so night work still counts to the day before). If a session runs across the day change, its next
compaction injects the archived notebook as source material and asks Claude to write a fresh, tidy one.

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

try:
    import fcntl
except ImportError:  # Windows: no lock, the day marker still keeps repeat runs cheap
    fcntl = None

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


def day_start_hour() -> int:
    try:
        return min(max(int(os.environ.get("CONTEXIERGE_DAY_START_HOUR", "4")), 0), 23)
    except ValueError:
        return 4


def day_of(timestamp: float) -> str:
    """Calendar day a moment belongs to, with the day starting at CONTEXIERGE_DAY_START_HOUR."""
    return time.strftime("%Y-%m-%d", time.localtime(timestamp - day_start_hour() * 3600))


def _free_target(folder: Path, name: str) -> Path:
    target = folder / name
    stem, suffix, n = target.stem, target.suffix, 2
    while target.exists():
        target, n = folder / f"{stem}-{n}{suffix}", n + 1
    return target


def rollover(now: float | None = None) -> int | None:
    """On the first run of a new day, move earlier days' notebooks and log to archive/<day>/.

    Returns the number of files archived, or None if today was already handled.
    """
    base = directory()
    today = day_of(time.time() if now is None else now)
    marker = base / ".day"
    try:
        if marker.read_text(encoding="utf-8").strip() == today:
            return None
    except OSError:
        pass
    base.mkdir(parents=True, exist_ok=True)
    with (base / ".lock").open("a") as lock:
        if fcntl is not None:
            fcntl.flock(lock, fcntl.LOCK_EX)
        try:  # another session may have done it while we waited for the lock
            if marker.read_text(encoding="utf-8").strip() == today:
                return None
        except OSError:
            pass
        moved = 0
        for path in sorted([*base.glob("*.md"), base / "log.jsonl"]):
            try:
                day = day_of(path.stat().st_mtime)
            except OSError:
                continue
            if day >= today:
                continue  # already written today: belongs to today's book
            folder = base / "archive" / day
            folder.mkdir(parents=True, exist_ok=True)
            if path.name == "log.jsonl" and (folder / "log.jsonl").exists():
                with (folder / "log.jsonl").open("a", encoding="utf-8") as f:
                    f.write(path.read_text(encoding="utf-8", errors="replace"))
                path.unlink()
            else:
                path.replace(_free_target(folder, path.name))
            moved += 1
        marker.write_text(today + "\n", encoding="utf-8")
    log({"event": "archive", "day": today, "files": moved})
    return moved


def archived_notebook(session_file: str) -> Path | None:
    """Most recent archived notebook of this session, if the day change moved it away."""
    found = sorted((directory() / "archive").glob(f"*/{session_file}"))
    return found[-1] if found else None


def _body(text: str) -> tuple[str, bool]:
    truncated = len(text) > MAX_CHARS
    return text[:MAX_CHARS] + (
        "\n\n[… truncated: notebook exceeds 16,000 characters — condense it the next time you update it]"
        if truncated else ""
    ), truncated


def response(event: dict) -> dict | None:
    """Hook response for a SessionStart event, or None (inject nothing)."""
    if event.get("hook_event_name") != "SessionStart":
        return None
    try:
        rollover()
    except Exception:  # tidying up must never cost the session its notebook
        pass
    if event.get("source") != "compact":
        return None
    session = str(event.get("session_id") or "")
    path = notebook_path(session)
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        text = ""
    old = None if text else archived_notebook(path.name)
    try:
        old_text = old.read_text(encoding="utf-8").strip() if old else ""
    except OSError:
        old_text = ""
    if text:
        body, truncated = _body(text)
        context = (
            f"Context notebook for this session (kept by you, {path}). Where it and the automatic summary disagree, "
            f"the notebook wins. Keep maintaining it: rewrite, don't append.\n\n{body}"
        )
        log({"session": session[:8], "source": "compact", "chars": len(text), "truncated": truncated})
    elif old_text:
        body, truncated = _body(old_text)
        context = (
            f"Context notebook archived at the day change ({old}). It still beats the automatic summary where they "
            f"disagree. Write a fresh notebook at {path} now: carry over only what is still open or still matters "
            "today (requests, decisions, running work, next steps, pitfalls), collapse finished threads to a line "
            f"or drop them.\n\n{body}"
        )
        log({"session": session[:8], "source": "compact", "chars": 0, "archived_chars": len(old_text)})
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
