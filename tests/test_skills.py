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


def test_repository_is_english_only_except_the_russian_readme() -> None:
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    for name in files:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert name == "README.ru.md" or not re.search("[\u0400-\u04ff]", text), name


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
    # A resumed session still has its history, so the plan is not printed again: only a compaction loses it.
    for source in ("startup", "resume", "clear"):
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


def tool_rows(path: Path) -> dict[str, str]:
    """The rows of the question-tool table in a grill skill, by tool name."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return {line.split("|")[1].strip(): line for line in lines if line.startswith("| `")}


def review_brief(skills: Path) -> str:
    """The reviewer brief of a review skill, up to its last sentence."""
    text = words(skills / "review" / "SKILL.md")
    brief = text[text.index("> Review the changes in the repository") :]
    return brief[: brief.index("Answer in")]


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
    assert claude.count(launch) == claude.count("timeout 900 " + launch) > 0  # every Codex command has its limit
    assert "in single quotes" in claude  # the focus of a repeat: no backticks, no $
    assert "$CODEX_ROOT" not in words(CLAUDE / "grill" / "SKILL.md")
    assert "all the changed files" in words(CODEX / "review" / "SKILL.md")


def test_codex_grill_asks_by_mode() -> None:
    rows = tool_rows(CODEX / "grill" / "SKILL.md")
    assert "Plan mode" in rows["`request_user_input`"] and "not for these questions" not in rows["`request_user_input`"]
    assert "Plan mode" in rows["`request_user_input_async`"]
    text = words(CODEX / "grill" / "SKILL.md")
    assert "end the turn with the open questions written out in your final message" in text
    assert "in Plan mode, give the plan in your final answer" in text


def test_readmes_show_the_final_row_and_the_anchor_links() -> None:
    final_ru = "\u0444\u0438\u043d\u0430\u043b\u044c\u043d\u0430\u044f"  # the Russian name of the tier
    for readme, final in (("README.md", "| final |"), ("README.ru.md", "| " + final_ru + " |")):
        text = (ROOT / readme).read_text(encoding="utf-8")
        assert final in text, readme
        assert "#L" in text, readme  # the bench reads file#Lline links too
