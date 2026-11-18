"""Checks that keep the two skill sets in step: Claude Code in plugins/duck-factory, Codex in duck-factory-codex."""

from __future__ import annotations

import json
import re
import subprocess
import sys
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


def test_repository_is_english_only() -> None:
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    for name in files:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert not re.search("[\u0400-\u04ff]", text), name


# --- the hooks around a compaction ---------------------------------------------------------------

HOOK = ROOT / "plugins" / "duck-factory" / "scripts" / "context_hooks.py"


def run_hook(cwd: Path, raw: str | None = None, **fields: object) -> subprocess.CompletedProcess[str]:
    """The hook on an event: by default the start of a session after a compaction, in `cwd`."""
    event = {"cwd": str(cwd), "hook_event_name": "SessionStart", "source": "compact", **fields}
    stdin = json.dumps(event) if raw is None else raw
    return subprocess.run([sys.executable, "-I", str(HOOK)], input=stdin, capture_output=True, text=True, check=False)


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
    for source in ("startup", "clear"):  # whatever starts a session that is not a continuation
        shown = run_hook(tmp_path, source=source).stdout
        assert str(active) in shown
        assert "old.md" not in shown
        assert "Goal: something" not in shown
        assert "today" in shown  # when it was last changed
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


# --- what both versions of the skills must say -----------------------------------------


def words(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def description(path: Path) -> str:
    return next(line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("description:"))


def test_the_hook_finds_a_plan_written_from_the_template_of_either_grill(tmp_path: Path) -> None:
    for skills in (CLAUDE, CODEX):
        text = (skills / "grill" / "SKILL.md").read_text(encoding="utf-8")
        template = text[text.index("```markdown\n") + len("```markdown\n") :]
        written = plan(tmp_path / skills.parent.name, "plan.md", None, text=template[: template.index("```")])
        assert str(written) in run_hook(written.parents[2]).stdout, skills


def test_grill_asks_whether_to_do_an_inferred_task_and_tracks_the_plan() -> None:
    for skills in (CLAUDE, CODEX):
        text = words(skills / "grill" / "SKILL.md")
        assert "Source:" in text, skills
        assert "whether to do it at all" in text, skills
        assert "only when the plan changes code" in text, skills
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
