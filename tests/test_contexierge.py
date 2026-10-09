"""Contexierge hook: only after compaction, content verbatim, instruction when missing, never disturb the session."""

from __future__ import annotations

import json
import subprocess
import sys
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
