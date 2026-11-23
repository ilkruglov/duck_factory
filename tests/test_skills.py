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
    assert "in single quotes" in claude  # the focus of an enhanced review: no backticks, no $
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
    ("review", "For the text of skills, prompts and docs in the change", "what the rules say."),
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
    ("subagent with a fresh context does this step", 'sub-agent with `fork_turns="none"` does this step'),
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
        "translated heading",  # plans are written in the user's language, headings included
        "from the current folder up to the root of the repository",  # as the hook looks
        "would load for the files",  # nested rules load only when their files are read
        "Before the first round, search once",  # not again before every question
        "two plans disagree, ask",  # plans carry no date to tell which is newer
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


def test_text_is_reviewed_by_one_subagent_and_code_by_simplify() -> None:
    fixes = between(words(CLAUDE / "review" / "SKILL.md"), "## 5.", "## Rules")  # Codex: see the mirror test
    assert "`/simplify` (Skill tool, skill `simplify`) for the code" in fixes
    assert "For the text of skills, prompts and docs in the change, one subagent" in fixes


def test_readmes_name_agents_md_for_codex_and_the_project_rules() -> None:
    for readme in ("README.md", "README.ru.md"):
        text = (ROOT / readme).read_text(encoding="utf-8")
        rows = [line for line in text.splitlines() if line.startswith("|")]  # the table, not a paragraph
        row = next(line for line in rows if "`Security paths`" in line and "`AGENTS.md`" in line)
        cells = row.split("|")
        assert "`CLAUDE.md`" in cells[2] and "`AGENTS.md`" in cells[3], readme  # Claude Code, then Codex
    english = words(ROOT / "README.md")
    assert "reviewer to read the project's rules" in english
    assert "`/code-review` checks the rules of `CLAUDE.md` itself" in english  # one group: no brief for Codex review
    assert "and the brief reaches no one" in english  # said of an ordinary review with one group
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
    assert codex.count('fork_turns="none"') >= 3  # every sub-agent of the step reads without the conversation


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
    with pytest.raises(AssertionError):
        changelog_check(english, russian, ["0.4.2", "0.4.2"], "0.4.2")  # a bump without an entry
    with pytest.raises(AssertionError):
        changelog_check(
            english, russian.replace("## 0.4.1 - 2026-11-23", "## 0.4.1 - 2026-11-21"), ["0.4.1"] * 2, "0.4.1"
        )
    empty = "## 0.4.2 - 2026-11-24\n\n"
    with pytest.raises(AssertionError):
        changelog_check(empty + english, empty + russian, ["0.4.2", "0.4.2"], "0.4.2")
