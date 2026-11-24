"""Checks of the reviewers bench: what each variant runs, how a run is scored and summed up."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "evals"))
spec = importlib.util.spec_from_file_location("reviewers", ROOT / "evals" / "reviewers.py")
assert spec and spec.loader
reviewers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reviewers)


def case_repo(tmp_path: Path) -> Path:
    """A case: one commit, then an uncommitted change in two folders and a new file."""
    repo = tmp_path / "repo"
    (repo / "src" / "audio").mkdir(parents=True)
    (repo / "src" / "ui").mkdir(parents=True)
    (repo / "src" / "audio" / "player.rs").write_text("fn play() {}\n", encoding="utf-8")
    (repo / "src" / "ui" / "gui.rs").write_text("fn draw() {}\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=a", "-c", "user.email=a@a", "commit", "-qm", "base"], check=True
    )
    (repo / "src" / "audio" / "player.rs").write_text("fn play() {\n    let x = 1;\n}\n", encoding="utf-8")
    (repo / "src" / "ui" / "gui.rs").write_text("fn draw() {\n    redraw(0);\n}\n", encoding="utf-8")
    (repo / "src" / "audio" / "asio.rs").write_text("fn open() {}\n", encoding="utf-8")
    return repo


def test_the_change_lists_modified_and_new_files(tmp_path: Path) -> None:
    repo = case_repo(tmp_path)
    assert reviewers.changed_files(repo) == ["src/audio/asio.rs", "src/audio/player.rs", "src/ui/gui.rs"]


def test_groups_follow_the_folders_and_every_file_is_in_one() -> None:
    files = ["src/audio/asio.rs", "src/audio/player.rs", "src/ui/gui.rs", "src/ui/menu.rs", "src/api.rs"]
    groups = reviewers.split(files, count=2)
    assert sorted(f for group in groups for f in group) == sorted(files)
    assert len(groups) == 2
    assert any({"src/audio/asio.rs", "src/audio/player.rs"} <= set(group) for group in groups)  # a folder stays whole


def test_the_brief_is_the_group_brief_of_the_skill(tmp_path: Path) -> None:
    text = reviewers.brief(tmp_path, "abc123", ["src/a.rs", "src/b.rs"])
    assert text.startswith(f"Review the changes in the repository at `{tmp_path}` since `abc123`")
    assert "`src/a.rs`, `src/b.rs`" in text and "Do not change any files" in text and "Answer in English" in text
    skill = " ".join((ROOT / "plugins" / "duck-factory" / "skills" / "review" / "SKILL.md").read_text().split())
    assert "Read each of your files in full" in skill and "Read each of your files in full" in text  # the same words


def test_each_variant_runs_what_it_names(tmp_path: Path) -> None:
    root, out = tmp_path / "repo", tmp_path / "out"
    assert "groups-medium" in reviewers.VARIANTS
    groups = reviewers.variant_command("groups-medium", root, "BRIEF", out, model="opus")
    assert groups[groups.index("--effort") + 1] == "medium"
    claude = reviewers.variant_command("brief-high", root, "BRIEF", out, model="opus")
    assert claude[:3] == ["claude", "-p", "BRIEF"] and claude[claude.index("--effort") + 1] == "high"
    assert "Agent" not in claude[claude.index("--allowedTools") + 1]  # the reviewer does the review itself
    builtin = reviewers.variant_command("builtin-medium", root, "BRIEF", out, model="opus")
    assert builtin[2] == f"/code-review medium {root}" and "--effort" not in builtin  # the session's own effort
    for argv in (groups, claude, builtin):  # the model named for the bench, not the default of the settings
        assert argv[argv.index("--model") + 1] == "opus"
    codex = reviewers.variant_command("codex-brief", root, "BRIEF", out, model="opus")
    assert codex[:2] == ["codex", "exec"] and codex[codex.index("--sandbox") + 1] == "read-only"
    assert reviewers.variant_command("codex-review", root, "BRIEF", out, model="opus")[:3] == [
        "codex",
        "review",
        "--uncommitted",
    ]


def test_usage_and_report_come_from_the_json_of_claude() -> None:
    raw = json.dumps(
        {
            "type": "result",
            "is_error": False,
            "result": "1. bug at src/a.rs:3",
            "total_cost_usd": 0.5,
            "modelUsage": {
                "claude-opus-5-5": {
                    "inputTokens": 10,
                    "outputTokens": 20,
                    "cacheReadInputTokens": 300,
                    "cacheCreationInputTokens": 40,
                },
                "claude-sonnet-5-5": {
                    "inputTokens": 1,
                    "outputTokens": 2,
                    "cacheReadInputTokens": 3,
                    "cacheCreationInputTokens": 4,
                },
            },
        }
    )
    report, tokens, cost = reviewers.claude_result(raw)
    assert report == "1. bug at src/a.rs:3" and tokens == 380 and cost == 0.5
    assert reviewers.claude_result("not json") == ("", 0, 0.0)  # a failed run is read as no report


def test_a_run_is_scored_by_the_places_of_each_seed(tmp_path: Path) -> None:
    repo = case_repo(tmp_path)
    seeds = [
        {"title": "x is unused", "places": [["src/audio/player.rs", "let x = 1"]]},
        {"title": "redraw gets zero", "places": [["src/ui/gui.rs", "redraw(0)"]]},
    ]
    found = reviewers.score(seeds, repo, "1. src/audio/player.rs:2 x is never read\n2. src/ui/gui.rs:9 other")
    assert found == ["x is unused"]
    assert reviewers.count_findings("1. one\n2. two\n\n**3. three**\nnot one") == 3
    assert reviewers.count_findings("- [P1] one\n- [P2] two\n- not one") == 2  # Codex's own review
    assert reviewers.count_findings("Findings:\n- [high] one\n- [low] two\n- [note] not one") == 2  # adversarial


def test_the_json_list_of_the_built_in_review_is_scored_and_counted(tmp_path: Path) -> None:
    repo = case_repo(tmp_path)
    seeds = [{"title": "x is unused", "places": [["src/audio/player.rs", "let x = 1"]]}]
    report = 'Summary.\n\n```json\n[\n  {"file": "src/audio/player.rs", "line": 2, "summary": "x"},\n  {"file": "src/ui/gui.rs", "line": 1, "summary": "y"}\n]\n```\n'
    assert reviewers.score(seeds, repo, report) == ["x is unused"]
    assert reviewers.count_findings(report) == 2


def test_the_summary_shows_the_mean_the_union_and_what_one_variant_adds() -> None:
    runs = [
        {"variant": "brief-xhigh", "ok": True, "found": ["a", "b"], "tokens": 100, "cost": 1.0, "seconds": 60},
        {"variant": "brief-xhigh", "ok": True, "found": ["a"], "tokens": 120, "cost": 1.2, "seconds": 80},
        {"variant": "builtin-high", "ok": True, "found": ["c"], "tokens": 50, "cost": 0.4, "seconds": 30},
        {"variant": "builtin-high", "ok": False, "found": [], "tokens": 0, "cost": 0.0, "seconds": 900},
    ]
    rows = {row["variant"]: row for row in reviewers.summary(runs, seeds=4)}
    assert rows["brief-xhigh"]["found_mean"] == 1.5 and rows["brief-xhigh"]["union"] == ["a", "b"]
    assert rows["builtin-high"]["ok"] == "1/2" and rows["builtin-high"]["found_mean"] == 1.0  # the failed run is out
    assert reviewers.adds(runs, "builtin-high", "brief-xhigh") == ["c"]


def test_the_summary_scores_the_saved_reports_again(tmp_path: Path) -> None:
    case = tmp_path / "case"
    out = case / "runs" / "brief-high-1"
    out.mkdir(parents=True)
    case_repo(out)
    (out / "report.md").write_text("1. src/audio/player.rs:2 x is never read", encoding="utf-8")
    (out / "result.json").write_text(json.dumps({"variant": "brief-high", "ok": True, "found": [], "findings": 0}))
    seeds = [{"title": "x is unused", "places": [["src/audio/player.rs", "let x = 1"]]}]
    [run] = reviewers.rescore(case, seeds)
    assert run["found"] == ["x is unused"] and run["findings"] == 1
    assert json.loads((out / "result.json").read_text())["found"] == ["x is unused"]  # saved for the next summary


def test_the_tokens_of_codex_come_from_its_log() -> None:
    assert reviewers.codex_tokens("thinking\ntokens used\n17,477\n") == 17477
    assert reviewers.codex_tokens("no count here") == 0  # codex review does not print one


def test_the_copy_under_review_lies_away_from_the_answers(tmp_path: Path, monkeypatch) -> None:
    case = tmp_path / "bench" / "cases" / "yamusic"
    case_repo(case)
    (case / "seeds.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(reviewers, "WORK", tmp_path / "work")
    root = reviewers.copy_case(case)
    assert case not in root.parents and root.name == "yamusic"  # the path does not say "bench" or "repo"
    assert [p.name for p in root.parent.iterdir()] == ["yamusic"]  # ../ holds only this copy
    assert (root / "src" / "audio" / "asio.rs").is_file()  # untracked files come along


def test_the_copy_is_kept_and_what_the_reviewer_left_beside_it_is_dropped(tmp_path: Path, monkeypatch) -> None:
    case = tmp_path / "cases" / "yamusic"
    case_repo(case)
    monkeypatch.setattr(reviewers, "WORK", tmp_path / "work")
    root = reviewers.copy_case(case)
    (root.parent / "review-target").mkdir()  # reviewers build and download next to the copy
    (root.parent / "review-clippy.log").write_text("warning", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    reviewers.collect(root, out)
    assert (out / "repo" / "src" / "audio" / "asio.rs").is_file() and not root.parent.exists()


def test_a_run_that_breaks_is_reported_and_does_not_stop_the_others(tmp_path: Path, monkeypatch, capsys) -> None:
    def run_one(case: Path, variant: str, number: int, timeout: int, parallel_groups: bool, model: str) -> dict:
        if variant == "brief-high":
            raise OSError("Directory not empty")
        return {"ok": True, "found": [], "findings": 0, "tokens": 0, "cost": 0.0, "seconds": 1}

    monkeypatch.setattr(reviewers, "run_one", run_one)
    reviewers.run_all(tmp_path, ["brief-high", "brief-medium"], runs=1, parallel=1, timeout=10, model="opus")
    printed = capsys.readouterr().out
    assert "brief-high #1: BROKE, OSError: Directory not empty" in printed and "brief-medium #1: ok" in printed


def test_the_adversarial_review_of_codex_runs_as_the_skill_runs_it(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(reviewers, "codex_plugin", lambda: Path("/plugins/codex/1.0.6"))
    argv = reviewers.variant_command("codex-adversarial", tmp_path, "BRIEF", tmp_path, model="opus")
    assert argv[:6] == [
        "node",
        "/plugins/codex/1.0.6/scripts/codex-companion.mjs",
        "adversarial-review",
        "--wait",
        "--scope",
        "working-tree",
    ]
    skill = " ".join((ROOT / "plugins" / "duck-factory" / "skills" / "review" / "SKILL.md").read_text().split())
    assert argv[6] in skill  # the directions the skill names, not ones written with the seeds in mind
    assert not set("'`$") & set(argv[6])
