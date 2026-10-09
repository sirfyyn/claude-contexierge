"""Contexierge hook: inject after compaction, verbatim, instruction when missing, daily archive, never disturb."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "plugins" / "contexierge" / "hooks" / "contexierge.py"


def _hook(directory: Path, event, env_extra=None) -> tuple[int, str]:
    data = event if isinstance(event, str) else json.dumps(event)
    env = {"CONTEXIERGE_DIR": str(directory), "PATH": "/usr/bin:/bin", **(env_extra or {})}
    r = subprocess.run([sys.executable, str(SCRIPT)], input=data, capture_output=True, text=True, env=env, timeout=10)
    return r.returncode, r.stdout


@pytest.fixture
def directory(tmp_path: Path) -> Path:
    return tmp_path / "cx"


def test_startup_injects_nothing(directory: Path):
    rc, out = _hook(directory, {"hook_event_name": "SessionStart", "source": "startup", "session_id": "abc"})
    assert rc == 0 and out == ""


def test_notebook_is_injected_after_compaction(directory: Path):
    directory.mkdir()
    (directory / "abc-123.md").write_text("# State\n- Request: clean up\n", encoding="utf-8")
    rc, out = _hook(directory, {"hook_event_name": "SessionStart", "source": "compact", "session_id": "abc-123"})
    d = json.loads(out)["hookSpecificOutput"]
    assert rc == 0 and d["hookEventName"] == "SessionStart"
    assert "- Request: clean up" in d["additionalContext"] and "notebook wins" in d["additionalContext"]
    line = json.loads((directory / "log.jsonl").read_text().splitlines()[-1])
    assert line["session"] == "abc-123"[:8] and line["chars"] > 0


def test_missing_notebook_gives_short_instruction(directory: Path):
    rc, out = _hook(directory, {"hook_event_name": "SessionStart", "source": "compact", "session_id": "new"})
    context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert rc == 0 and "notebook missing" in context and "new.md" in context and len(context) < 600


def test_oversized_notebook_is_truncated(directory: Path):
    directory.mkdir()
    (directory / "x.md").write_text("a" * 20_000, encoding="utf-8")
    _, out = _hook(directory, {"hook_event_name": "SessionStart", "source": "compact", "session_id": "x"})
    context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "truncated" in context and len(context) < 17_000


def test_session_id_cannot_escape_directory(directory: Path):
    _, out = _hook(directory, {"hook_event_name": "SessionStart", "source": "compact", "session_id": "../../etc/passwd"})
    assert "etcpasswd.md" in json.loads(out)["hookSpecificOutput"]["additionalContext"]


def test_broken_input_never_disturbs(directory: Path):
    assert _hook(directory, "not json") == (0, "")


def test_path_from_environment(directory: Path):
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--path"], capture_output=True, text=True, timeout=10,
        env={"CONTEXIERGE_DIR": str(directory), "CLAUDE_CODE_SESSION_ID": "s-1"},
    )
    assert r.stdout.strip() == str(directory / "s-1.md")


# --- daily archive -------------------------------------------------------------------------------------------------

DAY = 24 * 3600


def _age(path: Path, seconds: float) -> None:
    t = time.time() - seconds
    os.utime(path, (t, t))


def _module(directory: Path, monkeypatch):
    monkeypatch.setenv("CONTEXIERGE_DIR", str(directory))
    spec = importlib.util.spec_from_file_location("contexierge", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_first_start_of_day_archives_earlier_books(directory: Path):
    directory.mkdir()
    old, today = directory / "old-1.md", directory / "today-1.md"
    old.write_text("# yesterday\n", encoding="utf-8")
    today.write_text("# today\n", encoding="utf-8")
    (directory / "log.jsonl").write_text('{"x": 1}\n', encoding="utf-8")
    _age(old, 2 * DAY)
    _age(directory / "log.jsonl", 2 * DAY)
    rc, out = _hook(directory, {"hook_event_name": "SessionStart", "source": "startup", "session_id": "s"})
    assert rc == 0 and out == ""
    archived = list((directory / "archive").glob("*/old-1.md"))
    assert len(archived) == 1 and not old.exists() and today.exists()
    assert (archived[0].parent / "log.jsonl").read_text() == '{"x": 1}\n'
    last = json.loads((directory / "log.jsonl").read_text().splitlines()[-1])
    assert last["event"] == "archive" and last["files"] == 2


def test_rollover_runs_once_per_day(directory: Path, monkeypatch):
    mod = _module(directory, monkeypatch)
    assert mod.rollover() == 0
    stale = directory / "late.md"
    stale.write_text("x", encoding="utf-8")
    _age(stale, 2 * DAY)
    assert mod.rollover() is None and stale.exists()  # same day: no second tidy-up


def test_day_starts_at_configured_hour(directory: Path, monkeypatch):
    mod = _module(directory, monkeypatch)
    monkeypatch.setenv("CONTEXIERGE_DAY_START_HOUR", "4")
    night = time.mktime((2026, 10, 10, 2, 30, 0, 0, 0, -1))
    morning = time.mktime((2026, 10, 10, 5, 0, 0, 0, 0, -1))
    assert mod.day_of(night) == "2026-10-09" and mod.day_of(morning) == "2026-10-10"


def test_archive_never_overwrites(directory: Path, monkeypatch):
    mod = _module(directory, monkeypatch)
    book = directory / "s.md"
    directory.mkdir()
    for _ in range(2):
        book.write_text("x", encoding="utf-8")
        _age(book, 2 * DAY)
        (directory / ".day").unlink(missing_ok=True)
        mod.rollover()
    assert len(list((directory / "archive").glob("*/s*.md"))) == 2


def test_compaction_after_day_change_asks_for_fresh_notebook(directory: Path):
    directory.mkdir()
    book = directory / "long-run.md"
    book.write_text("# State\n- Request: keep order\n", encoding="utf-8")
    _age(book, 2 * DAY)
    rc, out = _hook(directory, {"hook_event_name": "SessionStart", "source": "compact", "session_id": "long-run"})
    context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert rc == 0 and "archived at the day change" in context and "Write a fresh notebook" in context
    assert "- Request: keep order" in context and str(directory / "long-run.md") in context
    assert not book.exists()
