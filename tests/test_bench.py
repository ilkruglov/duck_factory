"""Checks of the bench runner itself: a summary that lies is worse than no bench."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("bench", ROOT / "evals" / "bench.py")
assert spec and spec.loader
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)

INNOCENT = """Review: normal - 49 code lines, 3 files, 3 call sites, reversible. Decided by: over 1 file.

No bugs found. The command I ran passed, and a repeat review is next.

The limit of 50 code lines holds; 0 call sites changed. The export module reuses the loader.

Quality note: `remove` writes the file even when nothing was removed (notes/store.py:33).
"""

REPORT = """Review: normal - 49 code lines, 3 files.

1. Duplicate ids: after a remove, the next add reuses an existing id - `notes/store.py:23`.

2. `export` with no `--limit` exports nothing: the default 0 gives an empty list
   ([export.py:22-24](/somewhere/notes/export.py:22)).

3. CSV breaks on commas, quotes or newlines: nothing is quoted (notes/export.py:14).
"""

DATA_REPORT = """Review: light - 3 code lines.

1. The row `later;someday` cannot be unpacked by the loader (notes/tags.csv:6).

2. The alias `todo` gets a second value that silently replaces the first (notes/tags.csv:7).
"""


def built(case: str, tmp_path: Path) -> Path:
    bench.build(case, tmp_path / case)
    return tmp_path / case


def cited(case: str, report: str, tmp_path: Path) -> list[bool]:
    return bench.mentioned(bench.seed_lines(bench.CASES[case][2], built(case, tmp_path)), report)


def test_seeds_are_not_found_in_a_report_that_cites_none_of_their_lines(tmp_path: Path) -> None:
    for name, (_, _, seeds) in bench.CASES.items():
        assert bench.mentioned(bench.seed_lines(seeds, built(name, tmp_path)), INNOCENT) == [False] * len(seeds), name


def test_seeds_are_found_in_a_report_that_cites_their_lines(tmp_path: Path) -> None:
    assert cited("feature", REPORT, tmp_path) == [True, True, True]
    assert cited("data", DATA_REPORT, tmp_path) == [True, True]
    only_first = DATA_REPORT[: DATA_REPORT.index("2. The alias")]
    assert bench.mentioned(bench.seed_lines(bench.CASES["data"][2], tmp_path / "data"), only_first) == [True, False]


def test_the_tier_line_is_recognised_as_the_review_skill_writes_it() -> None:
    for skills in ("duck-factory", "duck-factory-codex"):
        text = (ROOT / "plugins" / skills / "skills" / "review" / "SKILL.md").read_text(encoding="utf-8")
        example = next(line for line in text.splitlines() if line.startswith("`Review:"))
        assert bench.TIER.search(example), skills


def test_both_harnesses_are_judged_by_the_final_message_not_by_the_trace(tmp_path: Path) -> None:
    last = tmp_path / "last.txt"
    argv = bench.command("codex", tmp_path, "prompt", None, write=False, plugin=None, last=last)
    assert argv[argv.index("--output-last-message") + 1] == str(last)
    last.write_text("No findings.", encoding="utf-8")
    assert bench.final_message("codex", "exec cat notes/store.py\n    new_id = len(notes) + 1\n", last) == (
        "No findings.",
        [],
    )

    events = [
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Review: light - announced early"}]}},
        {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "x:grill"}}]},
        },
        {"type": "result", "result": "Waiting on the other reviewer."},
        {"type": "result", "result": "Review: normal - the report"},
    ]
    stream = "\n".join(json.dumps(event) for event in events)
    assert bench.final_message("claude", stream, last) == (
        "Review: normal - the report",
        [("Skill", {"skill": "x:grill"})],
    )


def test_a_run_without_a_result_is_reported_as_failed_not_as_missed_bugs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(bench, "RUNS", tmp_path)
    for script, why in (
        ("import sys; sys.stderr.write('boom: no such model'); sys.exit(3)", "exit code 3"),
        ("print('not a stream of events')", "no final message"),
    ):
        monkeypatch.setattr(bench, "command", lambda *_, script=script, **__: [sys.executable, "-c", script])
        assert bench.run("review", "small", "claude", None, 60, None) is False
        shown = capsys.readouterr().out
        assert why in shown
        assert "MISSING" not in shown
    assert any("boom" in errors.read_text(encoding="utf-8") for errors in tmp_path.glob("*/stderr.txt"))


def test_a_run_stopped_at_the_timeout_takes_down_what_it_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    note = tmp_path / "child.pid"
    script = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(note)!r}, 'w').write(str(child.pid))\n"
        "time.sleep(60)\n"
    )
    monkeypatch.setattr(bench, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(bench, "command", lambda *_, **__: [sys.executable, "-c", script])
    assert bench.run("review", "small", "claude", None, 2, None) is False
    assert "no answer in 2 s" in capsys.readouterr().out
    child = int(note.read_text())
    for _ in range(50):  # the orphan is reaped a moment after it is killed
        state = Path(f"/proc/{child}/stat")
        if not state.exists() or state.read_text().split(") ")[-1].startswith("Z"):
            break
        time.sleep(0.1)
    else:
        os.kill(child, 9)
        pytest.fail("the process started by the harness outlived the run")


def test_a_run_reports_a_skill_that_broke_the_tree_instead_of_crashing_on_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = json.dumps(
        {"type": "result", "result": "Review: light - 9 code lines\n1. Duplicate ids (notes/store.py:23)."}
    )
    monkeypatch.setattr(bench, "RUNS", tmp_path)
    for damage in ("os.remove('notes/store.py')", "open('\u0437\u0430\u043c\u0435\u0442\u043a\u0430.py', 'w').close()"):
        script = f"import os; {damage}; print({report!r})"
        monkeypatch.setattr(bench, "command", lambda *_, script=script, **__: [sys.executable, "-c", script])
        assert bench.run("review", "small", "claude", None, 60, None) is True, damage
        shown = capsys.readouterr().out
        assert "cited" in shown, damage  # the seeded line is known from before the run
        assert "working tree untouched: NO" in shown, damage
