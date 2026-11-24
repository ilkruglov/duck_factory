"""Checks that keep the two skill sets in step: Claude Code in plugins/duck-factory, Codex in duck-factory-codex."""

from __future__ import annotations

import datetime
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CLAUDE = ROOT / "plugins" / "duck-factory" / "skills"
CODEX = ROOT / "plugins" / "duck-factory-codex" / "skills"


def body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return text[text.index("---", 3) + 3 :]


def test_handoff_is_the_same_skill_in_both_harnesses() -> None:
    claude = body(CLAUDE / "handoff" / "SKILL.md").replace("CLAUDE.md", "AGENTS.md")
    assert body(CODEX / "handoff" / "SKILL.md") == claude


def test_codex_skills_do_not_call_claude() -> None:
    for path in CODEX.rglob("*"):
        if path.is_file():
            assert "claude" not in path.read_text(encoding="utf-8").lower(), path


def test_every_codex_skill_has_ui_metadata_and_handoff_is_manual() -> None:
    for skill in ("grill", "review", "handoff"):
        assert (CODEX / skill / "SKILL.md").is_file()
        assert "display_name" in (CODEX / skill / "agents" / "openai.yaml").read_text(encoding="utf-8")
    assert "allow_implicit_invocation: false" in (CODEX / "handoff" / "agents" / "openai.yaml").read_text()
    assert "disable-model-invocation: true" in (CLAUDE / "handoff" / "SKILL.md").read_text()


def test_repository_is_english_only_except_the_russian_readme_and_changelog() -> None:
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    for name in files:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert name in ("README.ru.md", "CHANGELOG.ru.md") or not re.search("[\u0400-\u04ff]", text), name


def test_the_russian_readme_has_the_sections_and_commands_of_the_english_one() -> None:
    english = (ROOT / "README.md").read_text(encoding="utf-8")
    russian = (ROOT / "README.ru.md").read_text(encoding="utf-8")
    for level in ("## ", "### "):
        count = [sum(line.startswith(level) for line in text.splitlines()) for text in (english, russian)]
        assert count[0] == count[1], level
    commands = [line for line in english.splitlines() if line.startswith(("claude plugin", "codex plugin", "python3 "))]
    assert commands
    for command in commands:
        assert command.split("  #")[0].rstrip() in russian, command


# --- the hooks around a compaction ---------------------------------------------------------------

HOOK = ROOT / "plugins" / "duck-factory" / "scripts" / "context_hooks.py"


def run_hook(cwd: Path, raw: str | None = None, **fields: object) -> subprocess.CompletedProcess[str]:
    """The hook on an event: by default the start of a session after a compaction, in `cwd`."""
    event = {"cwd": str(cwd), "hook_event_name": "SessionStart", "source": "compact", **fields}
    stdin = json.dumps(event) if raw is None else raw
    return subprocess.run(
        [sys.executable, "-I", str(HOOK)], input=stdin, capture_output=True, text=True, encoding="utf-8", check=False
    )


def plan(root: Path, name: str, status: str | None, tail: str = "", text: str | None = None) -> Path:
    path = root / ".tmp" / "plans" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    head = f"# {name}\n\n" + (f"Status: {status}\n\n" if status else "") + "Goal: something\n"
    path.write_text(head + tail if text is None else text, encoding="utf-8")
    return path


def git_init(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)


def test_hook_prints_only_active_plans(tmp_path: Path) -> None:
    active = plan(tmp_path, "export.md", "active")
    plan(tmp_path, "old.md", "done")
    plan(tmp_path, "gone.md", "dropped")
    plan(tmp_path, "legacy.md", None)
    done = run_hook(tmp_path)
    assert done.returncode == 0
    assert str(active) in done.stdout
    for other in ("old.md", "gone.md", "legacy.md"):
        assert other not in done.stdout
    assert "Goal: something" in done.stdout  # the plan itself, so that nothing depends on a later Read


def test_hook_names_a_plan_too_long_to_print_and_asks_to_read_it(tmp_path: Path) -> None:
    long = plan(tmp_path, "long.md", "active", tail="detail\n" * 3000)
    done = run_hook(tmp_path)
    assert str(long) in done.stdout
    assert "detail" not in done.stdout
    assert "read" in done.stdout.lower()
    assert len(done.stdout) < 10_000  # over that, Claude Code moves a hook's output to a file


def test_hook_finds_plans_from_a_subdirectory_of_the_repository(tmp_path: Path) -> None:
    git_init(tmp_path)
    active = plan(tmp_path, "export.md", "active")
    (tmp_path / "src").mkdir()
    assert str(active) in run_hook(tmp_path / "src").stdout


def test_hook_finds_the_root_plan_past_a_nearer_folder_without_active_plans(tmp_path: Path) -> None:
    git_init(tmp_path)
    active = plan(tmp_path, "export.md", "active")
    plan(tmp_path / "src", "old.md", "done")
    assert str(active) in run_hook(tmp_path / "src").stdout


def test_hook_reads_the_status_from_the_first_status_line_however_it_is_dressed(tmp_path: Path) -> None:
    closed = plan(tmp_path, "closed.md", "done", tail="A new plan starts with:\n\nStatus: active\n")
    bold = plan(tmp_path, "bold.md", None, text="# bold\n\n**Status:** active\n\nGoal: something\n")
    noted = plan(tmp_path, "noted.md", "active (waiting for the review)")
    shown = run_hook(tmp_path).stdout
    assert str(bold) in shown
    assert str(noted) in shown
    assert str(closed) not in shown


def test_hook_closes_a_plan_only_after_the_user_accepted_the_result(tmp_path: Path) -> None:
    plan(tmp_path, "export.md", "active")
    shown = " ".join(run_hook(tmp_path).stdout.split())
    assert "the user has accepted the result" in shown
    assert "finished" not in shown


def test_in_a_new_session_the_hook_only_names_the_active_plan(tmp_path: Path) -> None:
    active = plan(tmp_path, "export.md", "active")
    plan(tmp_path, "old.md", "done")
    # A resumed session still has its history, so the plan is not printed again: only a compaction loses it.
    for source in ("startup", "resume"):  # not `clear`: the user clears to start from an empty context
        shown = run_hook(tmp_path, source=source).stdout
        assert str(active) in shown
        assert "old.md" not in shown
        assert "Goal: something" not in shown
        assert "today" in shown  # when it was last changed
        # The user may have started a new session to get away from that work.
        assert "only when the user asks to continue that work" in " ".join(shown.split()), source
        assert len(shown) < 700


def test_hook_says_nothing_on_an_event_it_was_not_written_for(tmp_path: Path) -> None:
    plan(tmp_path, "export.md", "active")
    assert run_hook(tmp_path, hook_event_name="Stop").stdout == ""
    assert run_hook(tmp_path, json.dumps({"cwd": str(tmp_path)})).stdout == ""


def test_hook_does_not_look_above_the_repository_root(tmp_path: Path) -> None:
    plan(tmp_path, "export.md", "active")
    repo = tmp_path / "repo"
    git_init(repo)
    (repo / "src").mkdir()
    assert run_hook(repo / "src").stdout == ""


def test_hook_does_not_look_above_a_directory_that_is_not_a_repository(tmp_path: Path) -> None:
    if any((folder / ".git").is_file() or (folder / ".git" / "HEAD").is_file() for folder in tmp_path.parents):
        pytest.skip("the temporary directory is inside a repository on this machine")
    plan(tmp_path, "export.md", "active")
    (tmp_path / ".git").mkdir()  # a stray empty folder is not a repository
    (tmp_path / "other").mkdir()
    assert run_hook(tmp_path / "other").stdout == ""


def test_hook_is_silent_without_active_plans_and_survives_bad_input(tmp_path: Path) -> None:
    plan(tmp_path, "old.md", "done")
    assert run_hook(tmp_path).stdout == ""
    for bad in ("", "not json", "[]", '{"cwd": 5}'):
        done = run_hook(tmp_path, bad)
        assert (done.returncode, done.stdout) == (0, ""), bad


def before_compaction(cwd: Path, instructions: str | None = None) -> str:
    return run_hook(cwd, hook_event_name="PreCompact", trigger="auto", custom_instructions=instructions).stdout


def test_before_a_compaction_the_hook_asks_the_summary_to_keep_what_gets_lost(tmp_path: Path) -> None:
    active = plan(tmp_path, "export.md", "active")
    plan(tmp_path, "old.md", "done")
    asked = before_compaction(tmp_path)
    for heading in (
        "Exact commands",
        "Long materials",
        "Done, not checked",
        "Waiting on the user",
        "Standing corrections",
    ):
        assert heading in asked
    assert str(active) in asked
    assert "old.md" not in asked
    assert "Goal: something" not in asked  # the plan comes back in full after the compaction, not through the summary
    assert len(asked) < 10_000


def test_before_a_compaction_the_hook_works_without_plans_and_yields_to_the_users_own_instructions(
    tmp_path: Path,
) -> None:
    assert "Exact commands" in before_compaction(tmp_path)
    assert ".tmp/plans" not in before_compaction(tmp_path)
    assert before_compaction(tmp_path, "keep only the test results") == ""


def handoff(root: Path, name: str, status: str | None) -> Path:
    path = root / ".tmp" / "handoff" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    head = f"# {name} - handoff\n\n" + (f"Status: {status}\n\n" if status else "")
    path.write_text(head + "Traps: the render farm drops jobs over 20 minutes\n", encoding="utf-8")
    return path


def test_at_the_start_of_a_session_the_hook_names_an_active_handoff_with_its_date(tmp_path: Path) -> None:
    active = handoff(tmp_path, "ep20.md", "active")
    handoff(tmp_path, "ep19.md", "done")
    handoff(tmp_path, "legacy.md", None)  # written before handoff files had a Status line
    for source in ("startup", "resume"):  # not `clear`: the user clears to start from an empty context
        shown = run_hook(tmp_path, source=source).stdout
        assert f"{active} (last changed {datetime.date.today().isoformat()}, today)" in shown, source
        assert "ep19.md" not in shown and "legacy.md" not in shown, source
        assert "render farm" not in shown, source  # named, not loaded: the session may be about something else
        flat = " ".join(shown.split())
        assert "only when the user asks to continue that work" in flat, source
        # The user may have started a new session to get away from that work: no question about it, no closing rule.
        assert "ask the user" not in flat and "Status line" not in flat, source
        assert len(shown) < 600


def test_after_a_compaction_the_hook_names_the_active_handoff_and_asks_to_reread_it(tmp_path: Path) -> None:
    active = handoff(tmp_path, "ep20.md", "active")
    plan(tmp_path, "export.md", "active")
    shown = run_hook(tmp_path).stdout
    assert "Goal: something" in shown  # the plan still comes back in full
    assert str(active) in shown and "render farm" not in shown
    assert shown.index("Goal: something") < shown.index(str(active))  # the plan first: it is the source of truth
    flat = " ".join(shown.split())
    assert "read its traps and decisions again" in flat and "handoff file's Status line to done" in flat


def test_after_a_compaction_plans_and_handoffs_together_stay_under_the_limit(tmp_path: Path) -> None:
    deep = tmp_path / ("a" * 80) / ("b" * 80) / ("c" * 80)  # long paths are part of the output too
    plans = [plan(deep, f"plan{n}-{'x' * 40}.md", "active", tail=str(n) * 2560) for n in range(3)]
    handoffs = [handoff(deep, f"handoff{n}-{'z' * 40}.md", "active") for n in range(3)]
    for n, path in enumerate(plans):
        os.utime(path, (1_000_000 + n, 1_000_000 + n))
    shown = run_hook(deep).stdout
    assert len(shown) < 10_000  # over that, Claude Code moves a hook's output to a file
    assert all(str(path) in shown for path in plans + handoffs)
    assert "2" * 2560 in shown  # the newest plan still comes back in full


def test_only_the_first_line_under_the_title_is_the_files_status(tmp_path: Path) -> None:
    active = handoff(tmp_path, "ep20.md", "active")
    quoted = handoff(tmp_path, "quoted.md", None)  # an old file quoting the Status line of a plan
    quoted.write_text(
        "# old - handoff\n\nGoal: x\n\nDecisions and why:\n> Status: active was its line\n", encoding="utf-8"
    )
    plan(tmp_path, "fenced.md", None, tail="```markdown\n# a plan\n\nStatus: active\n```\n")
    shown = run_hook(tmp_path, source="startup").stdout
    assert str(active) in shown
    assert "quoted.md" not in shown and "fenced.md" not in shown


def test_the_title_and_headings_under_it_are_not_the_status(tmp_path: Path) -> None:
    bom = plan(tmp_path, "bom.md", None, text="\ufeff# bom\n\nStatus: active\n\nGoal: bom\n")  # an editor on Windows
    plan(tmp_path, "title.md", None, text="# Status: active\n\nStatus: done\n")
    handoff(tmp_path, "nested.md", None).write_text("# Old\n\n## Example\n\n> Status: active\n", encoding="utf-8")
    # Only a plain or bold Status line counts: a quote, a heading or a list item right under the title is not one.
    odd = {
        "quote": "> Status: active was its line",
        "heading": "## Status: active",
        "item": "- Status: active",
        "italic": "*Status:* active",
        "code": "    Status: active",  # indented: a code block
        "longer": "Status: active2",
        "dashed": "Status: active-old",
        "unclosed": "**Status: active",
        "mismatched": "**Status:__ active",
    }
    for name, line in odd.items():
        handoff(tmp_path, f"{name}.md", None).write_text(f"# Old\n\n{line}\n\nStatus: done\n", encoding="utf-8")
    underscored = plan(tmp_path, "underscored.md", None, text="# u\n\n__Status:__ active\n")  # bold too
    shown = run_hook(tmp_path, source="startup").stdout
    assert str(bom) in shown and str(underscored) in shown
    for name in ("title", "nested", *odd):
        assert f"{name}.md" not in shown, name
    # A line cut where the hook stops reading is not read as a whole one: `active2` is not `active`.
    cut = "# " + "x" * 1982 + "\n\nStatus: active2\n"
    assert len(cut.encode("utf-8")[: cut.index("2\n")]) == 2000
    plan(tmp_path, "cut.md", None, text=cut)
    # But a file that ends right where the reading stops is read whole, and any line break counts.
    ends = "# " + "x" * 1982 + "\n\nStatus: active"
    assert len(ends.encode("utf-8")) == 2000
    plan(tmp_path / "whole", "ends.md", None, text=ends)  # apart: only the newest three plans come back
    plan(tmp_path / "whole", "mac.md", None, text="# mac\rStatus: active\r" + "x" * 3000 + "\r")
    assert "cut.md" not in run_hook(tmp_path, source="startup").stdout
    whole = run_hook(tmp_path / "whole", source="startup").stdout
    assert "ends.md" in whole and "mac.md" in whole
    after = run_hook(tmp_path).stdout  # after a compaction the plan itself is read, BOM and all
    assert "# bom\n\nStatus: active\n\nGoal: bom" in after and "\ufeff" not in after


def test_a_plan_gone_before_it_is_printed_is_named_and_the_rest_still_shown(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("context_hooks", HOOK)
    assert spec and spec.loader
    hooks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hooks)
    kept = plan(tmp_path, "kept.md", "active")
    gone = kept.parent / "gone.md"  # found active, then removed before the hook read it in full
    shown = hooks.in_full([(gone, 2.0), (kept, 1.0)], "")
    assert f"{gone} ---\nCould not be read: it may have been moved or removed." in shown  # not "too long, read it"
    assert "Goal: something" in shown


def fits_both_hosts(text: str) -> bool:
    """Claude Code counts UTF-16 units up to 10,000; Codex counts 4 bytes of UTF-8 as a token, up to 5000."""
    return len(text.encode("utf-16-le")) // 2 < 10_000 and len(text.encode("utf-8")) / 4 <= 5000


def test_after_a_compaction_a_plan_in_any_script_stays_under_both_limits(tmp_path: Path) -> None:
    mixed = "a" * 5000 + "\U0001f986" * 2900  # Latin letters count once in UTF-16, emoji twice
    for name, body in (("chinese", "\u754c" * 8000), ("emoji", "\U0001f986" * 6000), ("mixed", mixed)):
        export = plan(tmp_path / name, "export.md", "active", tail=body)
        handoff(tmp_path / name, "\u4ea4\u63a5.md", "active")  # a handoff file with a Chinese name, named after it
        shown = run_hook(tmp_path / name).stdout
        assert str(export) in shown and "\u4ea4\u63a5.md" in shown, name
        assert fits_both_hosts(shown), name


def test_after_a_compaction_the_limit_of_codex_counts_too(tmp_path: Path) -> None:
    # A Chinese plan of 18,900 bytes fits Claude Code's 10,000 UTF-16 units easily; with the names of three handoff
    # files around it, it would not fit Codex's 5000 tokens of 4 bytes.
    text = "\u754c" * 6300
    export = plan(tmp_path, "export.md", "active", tail=text)
    for n in range(3):
        handoff(tmp_path, "\u4ea4" * 60 + f"{n}.md", "active")
    shown = run_hook(tmp_path).stdout
    assert str(export) in shown and text not in shown and fits_both_hosts(shown)
    whole = len(shown.encode("utf-8")) + len(export.read_text(encoding="utf-8").encode("utf-8"))
    assert whole > 20_000  # shown in full, it would have been over Codex's limit


def test_after_a_compaction_the_plan_that_gives_way_is_the_largest_as_measured(tmp_path: Path) -> None:
    # Emoji take 4 bytes of UTF-8 each: the emoji plan is the largest, though it has fewer characters.
    emoji = plan(tmp_path, "emoji.md", "active", tail="\U0001f986" * 4150)
    latin = [plan(tmp_path, f"latin{n}.md", "active", tail=str(n) * 4200) for n in range(2)]
    for n, path in enumerate([*latin, emoji]):
        os.utime(path, (1_000_000 + n, 1_000_000 + n))  # the emoji plan is the newest
    shown = run_hook(tmp_path).stdout
    assert "0" * 4200 in shown and "1" * 4200 in shown and "\U0001f986" * 100 not in shown
    assert fits_both_hosts(shown) and str(emoji) in shown


def test_after_a_compaction_plans_that_fit_are_shown_in_full(tmp_path: Path) -> None:
    # Chinese takes 3 bytes of UTF-8 a character: a plan just under Codex's limit still comes back whole.
    export = plan(tmp_path / "chinese", "export.md", "active")
    room = 19_000 - len(run_hook(tmp_path / "chinese").stdout.encode("utf-8"))
    body = "\u754c" * ((room - 30) // 3)
    plan(tmp_path / "chinese", "export.md", "active", tail=body)
    shown = run_hook(tmp_path / "chinese").stdout
    assert body in shown and fits_both_hosts(shown) and str(export) in shown
    # A tiny old plan does not push out a big new one when both fit.
    big = plan(tmp_path / "pair", "big.md", "active")
    tiny = plan(tmp_path / "pair", "tiny.md", None, text="Status: active\n")
    os.utime(tiny, (1_000_000, 1_000_000))
    room = 9500 - len(run_hook(tmp_path / "pair").stdout)
    body = "b" * (room - 30)
    plan(tmp_path / "pair", "big.md", "active", tail=body)
    shown = run_hook(tmp_path / "pair").stdout
    assert body in shown and f"{tiny} ---\nStatus: active" in shown and str(big) in shown


def test_a_file_name_that_is_not_utf_8_does_not_silence_the_hook(tmp_path: Path) -> None:
    export = plan(tmp_path, "export.md", "active")
    try:
        (export.parent / os.fsdecode(b"bad-\xff.md")).write_bytes(b"# bad\n\nStatus: active\n")
    except (OSError, UnicodeError):  # Windows decodes file names strictly
        pytest.skip("this file system takes only UTF-8 names")
    assert str(export) in run_hook(tmp_path, source="startup").stdout


def test_the_hook_speaks_utf_8_whatever_the_console_encoding(tmp_path: Path) -> None:
    cwd = tmp_path / "\u043f\u0440\u043e\u0435\u043a\u0442"  # a Cyrillic folder name
    plan(cwd, "export.md", "active", tail="Goal: \u044d\u043a\u0441\u043f\u043e\u0440\u0442\n")
    event = json.dumps({"cwd": str(cwd), "hook_event_name": "SessionStart", "source": "compact"}, ensure_ascii=False)
    # A Windows console: stdin and stdout in cp1252, which has no Cyrillic.
    console = (
        "import io, runpy, sys; "
        "sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='cp1252', errors='replace'); "
        "sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='cp1252'); "
        f"runpy.run_path({str(HOOK)!r}, run_name='__main__')"
    )
    done = subprocess.run([sys.executable, "-I", "-c", console], input=event.encode(), capture_output=True, check=False)
    assert "Goal: \u044d\u043a\u0441\u043f\u043e\u0440\u0442" in done.stdout.decode("utf-8")


def test_the_date_and_the_age_of_a_handoff_agree(tmp_path: Path) -> None:
    path = handoff(tmp_path, "ep20.md", "active")
    today = datetime.date.today()
    midnight = datetime.datetime.combine(today, datetime.time()).timestamp()
    for changed, day, age in (
        (midnight - 60, today - datetime.timedelta(days=1), "yesterday"),  # late last night is not "today"
        (midnight - 3 * 86400 + 3600, today - datetime.timedelta(days=3), "3 days ago"),
        (time.time() + 2 * 86400, today, "today"),  # a clock ahead of this one is not "-2 days ago"
    ):
        os.utime(path, (changed, changed))
        assert f"(last changed {day.isoformat()}, {age})" in run_hook(tmp_path, source="startup").stdout, age


def test_a_bad_byte_far_down_does_not_hide_an_active_file(tmp_path: Path) -> None:
    active = handoff(tmp_path, "ep20.md", "active")
    active.write_bytes(active.read_bytes() + b"x" * 3000 + b"\xff\n")
    export = plan(tmp_path, "export.md", "active")
    export.write_bytes(export.read_bytes() + b"\xff\n")
    shown = run_hook(tmp_path).stdout
    assert str(active) in shown and "Goal: something" in shown


def test_before_a_compaction_the_summary_keeps_the_path_of_the_active_handoff(tmp_path: Path) -> None:
    active = handoff(tmp_path, "ep20.md", "active")
    handoff(tmp_path, "ep19.md", "done")
    asked = before_compaction(tmp_path)
    assert str(active) in asked and "ep19.md" not in asked


def test_the_hook_names_at_most_three_handoffs_the_newest_first(tmp_path: Path) -> None:
    paths = [handoff(tmp_path, f"work{n}.md", "active") for n in range(5)]
    for n, path in enumerate(paths):
        os.utime(path, (1_000_000 + n, 1_000_000 + n))
    shown = run_hook(tmp_path, source="startup").stdout
    assert [p.name for p in paths if str(p) in shown] == ["work2.md", "work3.md", "work4.md"]
    assert shown.index("work4.md") < shown.index("work3.md")


def test_handoff_files_carry_a_status_and_grill_reads_the_decisions_of_closed_ones() -> None:
    for skills in (CLAUDE, CODEX):
        text = (skills / "handoff" / "SKILL.md").read_text(encoding="utf-8")
        template = between(text, "```markdown", "```")
        assert "Status: active" in template, skills
        # The session that finishes the work reads the file, not this skill: the closing rule goes into the file.
        assert "change the Status line to `done`; when it is dropped, to `dropped`" in " ".join(template.split())
        assert "Keep the sentence under the Status line" in " ".join(text.split()), skills
        grill = words(skills / "grill" / "SKILL.md")
        assert "the `Decisions and why` section of one with `Status: done`" in grill, skills
        assert "not the options it lists as tried and dropped" in grill, skills
        assert "exactly as shown, right under the title" in grill, skills  # the hook looks for it only there


def test_hooks_are_registered() -> None:
    hooks = json.loads((ROOT / "plugins" / "duck-factory" / "hooks" / "hooks.json").read_text(encoding="utf-8"))[
        "hooks"
    ]
    (starting,) = hooks["SessionStart"]
    assert set(starting["matcher"].split("|")) == {"compact", "resume", "startup"}
    assert [group.get("matcher") for group in hooks["PreCompact"]] == [None]  # manual and automatic alike
    for groups in hooks.values():
        for group in groups:
            assert all("scripts/context_hooks.py" in hook["command"] for hook in group["hooks"])


def test_the_codex_plugin_carries_the_same_script_on_session_start_only() -> None:
    codex = ROOT / "plugins" / "duck-factory-codex"
    assert (codex / "scripts" / "context_hooks.py").read_bytes() == HOOK.read_bytes()  # one script, two copies
    hooks = json.loads((codex / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    assert list(hooks) == ["SessionStart"]  # Codex ignores what a PreCompact hook prints
    (starting,) = hooks["SessionStart"]
    assert set(starting["matcher"].split("|")) == {"compact", "resume", "startup"}
    (hook,) = starting["hooks"]
    assert hook["type"] == "command"  # Codex skips any other kind of handler here
    assert hook["command"] == 'python3 -I "${PLUGIN_ROOT}/scripts/context_hooks.py"'
    # Codex counts a token as 4 bytes of UTF-8 and moves output over 2500 of them to a file; 9500 characters of
    # Cyrillic after a compaction are 19,000 bytes, 4750 such tokens.
    assert hook["additionalContextLimit"] == 5000 and hook["timeout"] == 10


# --- what both versions of the skills must say -----------------------------------------


def words(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def description(path: Path) -> str:
    return next(line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("description:"))


def tool_rows(path: Path) -> dict[str, str]:
    """The rows of the question-tool table in a grill skill, by tool name."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return {line.split("|")[1].strip(): line for line in lines if line.startswith("| `")}


def between(text: str, start: str, end: str) -> str:
    """The part of a text from `start` up to the next `end` after it."""
    part = text[text.index(start) :]
    return part[: part.index(end, len(start))]


def quoted(brief: str) -> str:
    """A quoted brief as one text: the quote markers of its wrapped lines dropped."""
    return brief.replace(" > ", " ")


def review_brief(skills: Path) -> str:
    """The reviewer brief of a review skill, up to its last sentence."""
    return quoted(between(words(skills / "review" / "SKILL.md"), "> Review the changes in the repository", "Answer in"))


def test_the_hook_finds_a_plan_written_from_the_template_of_either_grill(tmp_path: Path) -> None:
    for skills in (CLAUDE, CODEX):
        text = (skills / "grill" / "SKILL.md").read_text(encoding="utf-8")
        templates = [part.split("```")[0] for part in text.split("```markdown\n")[1:]]
        assert len(templates) == 2, skills  # the full plan and the short record
        for number, template in enumerate(templates):
            written = plan(tmp_path / f"{skills.parent.name}-{number}", "plan.md", None, text=template)
            assert str(written) in run_hook(written.parents[2]).stdout, (skills, number)


def test_grill_writes_a_short_record_for_work_without_code() -> None:
    """The owner objected three times to a full plan for slides and skills (22-24.11); a record for the agent
    itself, with steps and checked criteria, still comes back after a compaction and is what the review checks."""
    for skills in (CLAUDE, CODEX):
        text = words(skills / "grill" / "SKILL.md")
        assert "changes program code" in text, skills
        short = text[text.index("**Without code**") :]
        template = short[short.index("```markdown") : short.index("```", short.index("```markdown") + 3)]
        for heading in ("Status: active", "Source:", "Decisions:", "Steps:", "Acceptance criteria:"):
            assert heading in template, (skills, heading)
        assert "how it is checked" in template and "(by default)" in template, skills
        for absent in ("Goal:", "Skills used:", "Not touching:", "Scope:", "Risks"):
            assert absent not in template, (skills, absent)
        assert "start, or change something" in text, skills  # one question holds the record; yes is the go-ahead
        assert "never from a line marked (by default)" in text, skills  # the agent's own picks are not decisions
        assert "and the (by default) mark" in text, skills  # both may be written in the user's language
        assert "drop its (by default) mark" in text, skills  # a default the user changed is a decision now
        assert "still write the record" in text and "for large work" not in text, skills  # skipped interview too
        assert "a prompt the project's code does not read" in text and "no program loads" not in text, skills
        plan_part = between(text, "## The plan", "### Review of the plan")
        assert "Plan mode" in plan_part or "plan mode" in plan_part, skills  # not inside the full-plan-only review
        assert "in the full plan" in text, skills  # a short record has no Skills used line
        assert "a config, prompt or data file the code reads" in text, skills  # the review counts those as code
        assert "approved with the confirmation" not in text and text.count("go-ahead") <= 2, skills  # said once
    assert "In a plan mode that forbids writing files" in words(CLAUDE / "grill" / "SKILL.md")
    assert "the record goes into the final message" in words(
        CODEX / "grill" / "SKILL.md"
    )  # a Plan-mode question is one sentence
    for name in ("README.md", "README.ru.md", "CHANGELOG.md", "CHANGELOG.ru.md"):
        text = words(ROOT / name)
        assert (
            "checks the change against it" not in text
            and "\u0441\u0432\u0435\u0440\u044f\u0435\u0442 \u0441 \u043d\u0435\u0439 \u043f\u0440\u0430\u0432\u043a\u0443"
            not in text
        ), name  # no review of .md
    readme = words(ROOT / "README.md")
    assert "You objected" not in readme and "a script in the repository" in readme
    for name in ("README.md", "CHANGELOG.md"):
        assert "a config, prompt or data file the code reads" in words(ROOT / name), name


def test_grill_asks_whether_to_do_an_inferred_task_and_tracks_the_plan() -> None:
    for skills in (CLAUDE, CODEX):
        text = words(skills / "grill" / "SKILL.md")
        assert "Source:" in text, skills
        assert "whether to do it at all" in text, skills
        assert "only to a full plan" in text, skills  # a short record has no code to check against the repository
        assert "wholesale" in text, skills  # "do everything" about a list, not every request with two tasks
        assert "named one by one" in text, skills
    assert "more than four" in words(CLAUDE / "grill" / "SKILL.md")  # the dialog holds four options
    assert "picking none" in words(CLAUDE / "grill" / "SKILL.md")


def test_review_measures_without_whitespace_and_knows_critical_paths() -> None:
    for skills in (CLAUDE, CODEX):
        text = words(skills / "review" / "SKILL.md")
        assert "git diff HEAD -w --numstat" in text, skills
        assert "counted from the plain run" in text, skills  # indentation is syntax in Python and YAML
        assert "Critical paths" in text, skills
        assert "what they get and what they lose" in text, skills
        assert "what the review itself created" in text, skills  # uv.lock, caches: removed before the report
    assert "counts as code), and not when you were started as the reviewer" in description(
        CODEX / "review" / "SKILL.md"
    )


# --- the Codex model ------------------------------------------------------------------------


def test_claude_skills_use_the_model_from_the_codex_config() -> None:
    launches = [
        line
        for path in CLAUDE.rglob("SKILL.md")
        for line in path.read_text(encoding="utf-8").splitlines()
        if "codex-companion.mjs" in line
    ]
    assert launches
    for line in launches:  # the model and the effort come from ~/.codex/config.toml
        assert not re.search(r"(--model|--effort|\s-m)\b", line), line


def test_codex_grill_has_a_rule_for_each_question_tool() -> None:
    rows = tool_rows(CODEX / "grill" / "SKILL.md")
    assert {"`request_user_input`", "`request_user_input_async`", "`send_message_to_user_async`"} <= set(rows)
    assert "next message" in rows["`request_user_input_async`"]
    flat = words(CODEX / "grill" / "SKILL.md")
    assert "elapsed time is not an answer" in flat.lower()
    assert "Not touching" not in flat  # the model writes what the work covers, not what stays unchanged
    assert "Scope:" in flat


# --- review of the whole change, in groups ----------------------------------------------------


def test_review_has_a_final_review_of_everything_since_the_work_started() -> None:
    for skills in (CLAUDE, CODEX):
        text = words(skills / "review" / "SKILL.md")
        assert "Final review" in text, skills
        for moment in ("pull request", "worktree", "release", "merge-base"):
            assert moment in text, (skills, moment)


def test_review_splits_a_large_change_into_groups_with_one_brief() -> None:
    for skills in (CLAUDE, CODEX):
        text = words(skills / "review" / "SKILL.md")
        assert "from 2 to 4" in text and "100 code lines" in text and "500" in text, skills
        brief = review_brief(skills)
        assert "in full" in brief, skills
        assert "consumes it" in brief, skills  # the other side of a boundary, often outside the change
        assert "external APIs" in brief, skills  # the contracts the code relies on
    claude = words(CLAUDE / "review" / "SKILL.md")
    assert "a Claude subagent" in claude and "task --fresh" in claude


def test_review_runs_codex_with_the_brief_the_adversarial_review_and_the_built_in_on_the_whole_change() -> None:
    """The reviewer set the review bench of 23.11 chose: Codex with the group brief always, its adversarial review from
    the normal tier, the built-in review on the whole change - not Codex's own review, not Claude subagents per group
    outside a final review."""
    text = words(CLAUDE / "review" / "SKILL.md")
    rows = {
        row.split("|")[1].strip(): [cell.strip() for cell in row.split("|")[3:-1]]
        for row in (CLAUDE / "review" / "SKILL.md").read_text(encoding="utf-8").splitlines()
        if row.startswith("| ") and row.split("|")[1].strip() in ("light", "normal", "enhanced", "final", "repeat")
    }
    assert rows["light"][:2] == ["`low`", "the group brief"]
    assert rows["normal"][:2] == [
        "`medium`; `high` with more than one group",
        "the group brief and adversarial, with a focus",
    ]
    assert rows["enhanced"][:2] == ["`high`", "the group brief and adversarial, with a focus"]
    assert "adversarial since the base" in rows["final"][1]
    assert 'codex-companion.mjs" review' not in text  # Codex's own review found 10 of 22 important bugs, our brief 15
    assert "task --fresh --prompt-file .tmp/review/<run>/codex.md" in text  # the brief for the whole change
    assert (
        "adversarial-review --wait --scope working-tree" in text and "adversarial-review --wait --base <base>" in text
    )
    assert "sees only the commits" in text  # --base compares base...HEAD (lib/git.mjs of the Codex plugin)
    per_group = between(text, "**Reviewers per group**", "> Review the changes")
    assert "final review" in per_group
    without = between(text, "### When Codex is not available", "## 3.")
    assert "one Claude subagent with a fresh context and the group brief for the whole change" in without
    repeat = between(text, "3. A **repeat**", "When a round leaves")
    assert 'effort `medium` (Agent tool, `effort: "medium"`)' in repeat
    # the brief for a whole large change took 11.8 and 15.1 minutes on the bench and was cut at 15 in a live run
    assert (
        'timeout 1800 node "<CODEX_ROOT>/scripts/codex-companion.mjs" task --fresh --prompt-file .tmp/review/<run>/codex.md'
        in text
    )
    assert "its own brief" not in description(CLAUDE / "review" / "SKILL.md")  # read as Codex's own review
    assert "every tier, outside a final review" in text  # a final review gives Codex a brief per group instead
    assert "Outside a final review both cover every uncommitted file" in text  # --base sees the commits only
    assert "`high` stays `high`" in without
    assert "outside a final review, with more than one group, also one Claude subagent" in without
    assert "With more than one group the built-in review runs at `high`" not in text  # said once, in the table
    for readme in ("README.md", "README.ru.md"):
        assert "review_model" not in (ROOT / readme).read_text(encoding="utf-8"), readme  # no native review runs
    rules = between(text, "## Rules", "never go to")
    assert "without the `model` parameter" in rules  # a subagent then runs on the session's model


def test_codex_review_keeps_its_report_format() -> None:
    text = " ".join(
        (ROOT / "plugins" / "duck-factory-codex" / "skills" / "review" / "SKILL.md").read_text(encoding="utf-8").split()
    )
    report = text[text.index("## 4. Report") : text.index("## 5.")]
    positions = [
        report.index(heading) for heading in ["**Bugs**", "**Plan check**", "**Quality notes**", "**Not confirmed**"]
    ]
    assert positions == sorted(positions)
    assert "word for word" in report


def test_review_fixes_from_the_first_review_in_groups() -> None:
    for skills in (CLAUDE, CODEX):
        text = words(skills / "review" / "SKILL.md")
        assert "| final |" in text, skills  # the final review is a row of the tier table, not a rule beside it
        assert "the branch the work will be merged into" in text, skills  # not the branch's own upstream
        assert "Every changed file" in text, skills  # tests included
        assert "cannot simply be reverted" not in review_brief(skills), skills  # the brief states the tier's reason
        assert "Do the review yourself" in text, skills  # a reviewer does not start the review skill again
        assert "the `Groups:` line" in text, skills  # allowed by the report format
    claude = words(CLAUDE / "review" / "SKILL.md")
    assert "--prompt-file" in claude  # a brief inside "..." would be run by the shell: it has backticks
    assert "15 minutes" in claude
    assert "into every command" in claude  # a shell variable does not survive between Bash calls
    assert "at `max` on the whole change" in claude


def test_codex_grill_always_repeats_open_questions_in_the_final_message() -> None:
    assert "final message" in words(CODEX / "grill" / "SKILL.md")
    for readme in ("README.md", "README.ru.md"):
        lines = (ROOT / readme).read_text(encoding="utf-8").splitlines()
        row = next(line for line in lines if "`grill`" in line and "request_user_input" in line)
        assert "`request_user_input_async`" in row and "Plan mode" in row, readme
        assert readme.endswith(".ru.md") or "final message" in row, readme


def test_second_round_fixes_in_the_skills() -> None:
    for skills in (CLAUDE, CODEX):
        text = words(skills / "review" / "SKILL.md")
        assert "rounded up" in text, skills
        assert "in the worktree of the branch being merged" in text, skills
        assert "adding a delete command is reversible" in text, skills  # what a one-way door is not
        assert "the commit hash, not the word `HEAD`" in text, skills
    claude = words(CLAUDE / "review" / "SKILL.md")
    assert "CODEX_ROOT=" not in claude  # the command prints the path, the agent puts it into every command
    launch = 'node "<CODEX_ROOT>/scripts/codex-companion.mjs"'
    limited = claude.count("timeout 900 " + launch) + claude.count("timeout 1800 " + launch)
    assert claude.count(launch) == limited > 0  # every Codex command has its limit
    assert "in single quotes" in claude  # the focus of an enhanced review: no backticks, no $
    assert "$CODEX_ROOT" not in words(CLAUDE / "grill" / "SKILL.md")
    assert "all the changed files" in words(CODEX / "review" / "SKILL.md")


def test_codex_grill_asks_by_mode() -> None:
    rows = tool_rows(CODEX / "grill" / "SKILL.md")
    assert "Plan mode" in rows["`request_user_input`"] and "not for these questions" not in rows["`request_user_input`"]
    assert "Plan mode" in rows["`request_user_input_async`"]
    text = words(CODEX / "grill" / "SKILL.md")
    assert "end the turn with the open questions written out in your final message" in text
    assert "in Plan mode, give the plan or the record in your final answer" in text


def test_readmes_show_the_final_row_and_the_anchor_links() -> None:
    final_ru = "\u0444\u0438\u043d\u0430\u043b\u044c\u043d\u0430\u044f"  # the Russian name of the tier
    for readme, final in (("README.md", "| final |"), ("README.ru.md", "| " + final_ru + " |")):
        text = (ROOT / readme).read_text(encoding="utf-8")
        assert final in text, readme
        assert "#L" in text, readme  # the bench reads file#Lline links too


def test_reviewers_read_the_project_rules_and_tests_fail_for_the_right_reason() -> None:
    for skills in (CLAUDE, CODEX):
        brief = review_brief(skills)
        assert "the project's rules" in brief and "report a change that breaks them as a finding" in brief, skills
        assert "fails on the bug itself" in words(skills / "review" / "SKILL.md"), skills
        # one general rule instead of a list of file kinds that each review round found incomplete
        assert "would load for your files" in brief, skills


# Paragraphs both versions must say alike: the Claude text becomes the Codex text after these replacements.
MIRRORED = (
    ("review", "> Review the changes in the repository", "Answer in"),
    ("review", "> Look for security vulnerabilities", "language>."),
    ("review", "A yes covers", "In this order:"),
    ("review", "> Check the fixes just made", "Answer in"),
    ("review", "1. Each confirmed bug", "3. A **repeat**"),
    ("review", "If two rounds in a row find only edge cases", "Do not fix in circles."),
    ("review", "For each confirmed bug, check the places", "whether the bug is there too."),
    ("review", "When a round leaves nothing left to fix", "once for the whole work:"),
    ("grill", "**Finished work first.**", "commit after leaving it."),
    ("grill", "**Decided before.**", "came from."),
    ("grill", "Defaults are not hidden", "**"),
    ("grill", "When the user changes a decision during the work", "- A defect"),
)
TO_CODEX = (
    ("Claude Code would load", "Codex would load"),
    ("(`CLAUDE.md`, `AGENTS.md`, `.claude/rules/` and the like)", "(`AGENTS.md`, `AGENTS.override.md` and the like)"),
    (
        "the next question you ask or",
        "the next question you ask (in Plan mode, where a question is one sentence, into the final message) or",
    ),
    ("`Not touching:` section", "`Scope:` section"),
)


def mirrored(skills: Path, skill: str, start: str, end: str) -> str:
    return quoted(between(words(skills / skill / "SKILL.md"), start, end))


def test_mirrored_paragraphs_say_the_same_in_both_versions() -> None:
    claude = [mirrored(CLAUDE, *block) for block in MIRRORED]
    for old, _ in TO_CODEX:
        assert any(old in text for text in claude), old  # a replacement that matches nothing hides a drift
    for text, block in zip(claude, MIRRORED):
        for old, new in TO_CODEX:
            text = text.replace(old, new)
        assert text == mirrored(CODEX, *block), block[1]


def test_readmes_cover_the_whole_review() -> None:
    for readme in ("README.md", "README.ru.md"):
        text = (ROOT / readme).read_text(encoding="utf-8")
        assert "Security paths" in text and "SECURITY.md" in text, readme
        assert "gtimeout" in text, readme  # the timeout command the Codex calls need
    english = (ROOT / "README.md").read_text(encoding="utf-8")
    review_row = tool_rows(ROOT / "README.md")["`review`"]
    assert "final review" in review_row and "group" in review_row
    assert "adding a delete command" in english
    assert "These three habits" not in english  # the list has four now, and oh-my-pi gave three of them
    assert "already reported and you already decided on are dropped" in words(ROOT / "README.md")


def test_grill_takes_only_the_users_decisions_from_accepted_plans() -> None:
    text = words(CLAUDE / "grill" / "SKILL.md")  # the Codex text is the same: see the mirror test
    rule = between(text, "**Decided before.**", "came from.")
    for phrase in (
        "`Decisions:`",
        "`Status: done`",
        "never from its `Taken by default, not asked` section",  # those were the agent's picks
        "never from a plan that was dropped",
        "headings and the (by default) mark in translation",  # plans are written in the user's language, headings included
        "from the current folder up to the root of the repository",  # as the hook looks
        "would load for the files",  # nested rules load only when their files are read
        "Before the first round, search once",  # not again before every question
        "two plans or handoff files disagree, ask",  # neither carries a date to tell which is newer
    ):
        assert phrase in rule, phrase
    defaults = between(text, "Defaults are not hidden", "**")
    assert "even when only one question is asked" in defaults and "into the text of the next question" in defaults
    change = between(text, "When the user changes a decision during the work", "- A defect")
    assert "`Decisions:`" in change and "acceptance criteria" in change and "Taken by default" in change
    assert "`gtimeout` on macOS" in between(text, "timeout 900 node", "Show the path")


def test_review_runs_the_security_pass_only_after_the_user_says_yes() -> None:
    for skills, own in (
        # Claude asks while the other checks run; headless, at the end of the report
        (CLAUDE, ("AskUserQuestion", "is not available", "task --fresh --prompt-file .tmp/review/<run>/security.md")),
        (CODEX, ('fork_turns="none"', "end of the report")),  # Codex does not stop mid-run to ask
    ):
        text = words(skills / "review" / "SKILL.md")
        part = between(text, "**Security pass - only after the user says yes.**", "**Plan check**")
        rule, brief = part.split("> Look for security vulnerabilities")
        assert rule.index("Offer it") < rule.index("On yes,"), skills  # asked first, run after the answer
        assert "once per piece of work" in rule and "not again in a repeat round" in rule, skills
        assert "Run it without a question when the user asked for it" in rule, skills
        assert all(phrase in rule for phrase in own), skills
        brief = quoted(brief)
        assert "crosses a trust boundary" in brief and "`SECURITY.md`" in brief and "if they describe" in brief
        assert "critical, high, medium or low" in brief and "since `<base>`" in brief and "Answer in" in brief, skills
        assert "No such list: no security paths" in between(text, "- **Security paths**", "**Final review.**"), skills
        none = between(text, 'For tier "none"', "###")
        assert "only the security pass may follow" in none and "step 2" in none, skills
        questions = between(text, "End with the open questions", "## 5.")
        assert "numbered" in questions and "the pass runs first" in questions, skills  # one yes cannot answer two
        assert "the security pass, when it is offered" in questions, skills  # also when it was not asked before
    # a yes given before the findings existed does not cover fixing them; the steps of the fix are part of it
    consent = between(words(CLAUDE / "review" / "SKILL.md"), "A yes covers", "In this order:")
    assert "the findings the user has seen and the steps below" in consent and "come later" in consent
    review = words(CLAUDE / "review" / "SKILL.md")
    assert "the security pass are done by a subagent" in between(review, "### When Codex is not available", "## 3.")


def test_claude_review_briefs_live_in_a_folder_of_their_own_run() -> None:
    text = words(CLAUDE / "review" / "SKILL.md")
    assert text.count("mktemp -d") == 1 and text.index("mktemp -d") < text.index("--prompt-file")  # one per review
    files = re.findall(r"--prompt-file (\S+)", text)
    assert all(f.startswith(".tmp/review/<run>/") for f in files), files
    assert ".tmp/review/<run>/group-<number>.md" in files  # a name with a space or a name like "security" is safe


def test_simplification_joins_a_fresh_list_with_the_agents_own_pass() -> None:
    # On two reviewed changes /simplify found 17 real simplifications for 65M Claude tokens and applied a change of
    # behaviour; Codex found 23 without Claude tokens, a fresh Claude agent 14, the two together 31 of 37.
    for skills, start in ((CLAUDE, "4. Simplify the change"), (CODEX, "4. Simplify the change")):
        text = words(skills / "review" / "SKILL.md")
        step = between(text, start, "5. The project's tests")
        assert "`/simplify`" not in text, skills  # not the built-in skill
        for angle in ("reuse", "simplification", "efficiency", "altitude", "rules repeated or contradicting"):
            assert angle in step, (skills, angle)
    codex = between(words(CODEX / "review" / "SKILL.md"), "4. Simplify the change", "5. The project's tests")
    assert 'fork_turns="none"' in codex and "Do not change any files" in codex  # a fresh reader lists, edits nothing
    assert "go through the diff yourself" in codex and "Without sub-agents, the step is yours alone" in codex
    for dropped in ("taste", "changes behaviour", "code the change did not touch"):
        assert dropped in codex, dropped  # what the agent drops from the sub-agent's list
    claude = between(words(CLAUDE / "review" / "SKILL.md"), "4. Simplify the change", "5. The project's tests")
    assert "task --fresh --prompt-file .tmp/review/<run>/simplify-find.md" in claude  # Codex lists, changes nothing
    assert "Do not change any files" in claude and "go through the diff yourself" in claude
    for dropped in ("taste", "changes behaviour", "code the change did not touch"):
        assert dropped in claude, dropped  # what the agent drops from Codex's list
    assert "Without Codex, the step is yours alone" in claude
    for skills in (CLAUDE, CODEX):
        step = between(words(skills / "review" / "SKILL.md"), "4. Simplify the change", "5. The project's tests")
        assert "before you edit" in step, skills  # its file:line numbers would move under your edits
        assert "your own under the same limits" in step, skills  # keep behaviour, stay inside the change
        assert (
            "Do it yourself: do not start a skill or other agents" in step and "Read the project's rules first" in step
        )
    assert "without a fresh look" not in words(ROOT / "CHANGELOG.md")  # the bench's 14 was a fresh Claude agent
    simplification = between(
        words(ROOT / "README.md"), "the work ends once with a simplification", "changed behaviour."
    )
    assert (
        "instead of Codex" not in simplification and "In Codex the list comes from a fresh sub-agent" in simplification
    )


def test_readmes_name_agents_md_for_codex_and_the_project_rules() -> None:
    for readme in ("README.md", "README.ru.md"):
        text = (ROOT / readme).read_text(encoding="utf-8")
        rows = [line for line in text.splitlines() if line.startswith("|")]  # the table, not a paragraph
        row = next(line for line in rows if "`Security paths`" in line and "`AGENTS.md`" in line)
        cells = row.split("|")
        assert "`CLAUDE.md`" in cells[2] and "`AGENTS.md`" in cells[3], readme  # Claude Code, then Codex
    english = words(ROOT / "README.md")
    assert "reviewer to read the project's rules" in english
    assert "as a task with the brief below for the whole change" in english  # Codex gets the brief at every tier
    assert "and the brief reaches no one" not in english
    for readme in ("README.md", "README.ru.md"):
        text = (ROOT / readme).read_text(encoding="utf-8")
        security = next(line for line in text.splitlines() if line.startswith("|") and "AskUserQuestion" in line)
        headless = (
            "headless"
            if readme == "README.md"
            else "\u0431\u0435\u0437 \u0438\u043d\u0442\u0435\u0440\u0444\u0435\u0439\u0441\u0430"
        )  # the Russian words for it
        assert headless in security, readme  # then the question ends the report
        paths = between(" ".join(text.split()), "`Security paths`", ". ")
        assert "`AGENTS.md`" in paths, readme  # read from AGENTS.md when the project has no CLAUDE.md


def test_a_repeat_checks_only_the_fixes_and_simplify_runs_once() -> None:
    for skills in (CLAUDE, CODEX):  # what differs between the versions; the shared paragraphs: the mirror test
        text = words(skills / "review" / "SKILL.md")
        fixes = between(text, "## 5.", "## Rules")
        assert "in one group" in fixes and "where something was fixed" in fixes, skills
        assert "outside the change" in fixes and "number 1" in fixes, skills  # every fixed place has a reviewer
        assert "its text before and after" in fixes, skills  # what a check of a simplification needs
        rows = (skills / "review" / "SKILL.md").read_text(encoding="utf-8").splitlines()
        assert "repeat brief" in next(line for line in rows if line.startswith("| repeat |")), skills
    text = words(CLAUDE / "review" / "SKILL.md")
    fixes = between(text, "## 5.", "## Rules")
    for phrase in (
        "list of the fixed places",  # the agent knows them; a git snapshot missed new files
        "the places the report named",  # a yes covers what the user saw
        "goes to the user first",
        "tests of the module",
        "full test suite once",  # one full run per round
        "once for the whole work",  # simplify at the end only
        "nothing left to fix",
        "After the third repeat round",
        "real bugs each round brought",
    ):
        assert phrase in fixes, phrase
    verify = between(text, "## 3.", "## 4.")
    assert "where the same logic repeats" in verify and "name those places with the finding" in verify
    brief = mirrored(CLAUDE, "review", "> Check the fixes just made", "Answer in")
    assert "Do not review the rest of the change again" in brief and "the code that calls it" in brief
    assert "would fail without it" in brief and "the files they point to" in brief
    assert "behaviour stayed the same" in brief  # a simplification has no bug to remove
    repeat = between(fixes, "3. A **repeat**", "When a round leaves")
    assert "repeat-<group number>.md" in repeat and "in the background" in repeat  # one file per group
    assert "task --fresh --prompt-file .tmp/review/<run>/simplify.md" in fixes  # never the brief on the command line
    assert "a Claude subagent with a fresh context" in between(fixes, "5. The project's tests", "The repeat brief")
    assert "same reviewers per group" not in text  # no full review of every group after a fix
    codex = between(words(CODEX / "review" / "SKILL.md"), "## 5.", "## Rules")
    assert codex.count('fork_turns="none"') >= 2  # every sub-agent of the step reads without the conversation


def test_grill_asks_to_commit_finished_work_before_a_new_task() -> None:
    rule = mirrored(CLAUDE, "grill", "**Finished work first.**", "commit after leaving it.")  # Codex: the mirror test
    assert "`git status`" in rule and "`Status: done`" in rule and "only on the user's command" in rule
    assert "also when the interview is skipped" in rule and "in a git repository" in rule and "plan mode" in rule


def changelog_entries(text: str) -> list[tuple[str, str]]:
    """Each entry of a changelog as (heading, body)."""
    parts = re.split(r"^## ", text, flags=re.MULTILINE)[1:]
    return [(part.split("\n", 1)[0], part.split("\n", 1)[1]) for part in parts]


def changelog_check(english: str, russian: str, versions: list[str], marketplace: str) -> None:
    entries = changelog_entries(english)
    assert [h for h, _ in entries] == [h for h, _ in changelog_entries(russian)]  # same versions and dates
    for heading, body in entries + changelog_entries(russian):
        assert re.fullmatch(r"\d+\.\d+\.\d+ - \d{4}-\d{2}-\d{2}", heading), heading
        assert "\n- " in "\n" + body, heading  # an entry says what changed
    listed = [h.split(" ")[0] for h, _ in entries]
    assert all(version in listed for version in versions), versions  # each plugin's version has its entry
    newest = max(versions, key=lambda v: tuple(int(n) for n in v.split(".")))
    assert listed[0] == newest, listed[0]  # on top; one plugin may stay behind, as in 0.2.1
    assert marketplace == versions[0], marketplace  # the Claude Code marketplace lists the Claude Code plugin


def test_the_changelog_has_the_version_of_both_plugins_in_both_languages() -> None:
    manifests = (CLAUDE.parent / ".claude-plugin" / "plugin.json", CODEX.parent / ".codex-plugin" / "plugin.json")
    versions = [json.loads(m.read_text(encoding="utf-8"))["version"] for m in manifests]
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    english, russian = ((ROOT / n).read_text(encoding="utf-8") for n in ("CHANGELOG.md", "CHANGELOG.ru.md"))
    changelog_check(english, russian, versions, market["plugins"][0]["version"])


def test_the_changelog_check_takes_a_release_of_one_plugin_and_rejects_gaps() -> None:
    english, russian = ((ROOT / n).read_text(encoding="utf-8") for n in ("CHANGELOG.md", "CHANGELOG.ru.md"))
    at_021 = [text[text.index("## 0.2.1") :] for text in (english, russian)]  # the changelog as it stood at 0.2.1
    changelog_check(*at_021, ["0.2.1", "0.2.0"], "0.2.1")  # Claude Code ahead of Codex
    top = changelog_entries(english)[0][0].split(" ")[0]
    major, minor, patch = (int(n) for n in top.split("."))
    bumped = f"{major}.{minor}.{patch + 1}"  # a version above every entry
    with pytest.raises(AssertionError):
        changelog_check(english, russian, [bumped, bumped], bumped)  # a bump without an entry
    with pytest.raises(AssertionError):
        changelog_check(english, russian.replace("## 0.4.1 - 2026-11-23", "## 0.4.1 - 2026-11-21"), [top] * 2, top)
    empty = f"## {bumped} - 2026-12-01\n\n"
    with pytest.raises(AssertionError):
        changelog_check(empty + english, empty + russian, [bumped, bumped], bumped)
