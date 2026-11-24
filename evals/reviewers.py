"""Bench of reviewers on real cases: which of the known bugs each kind of reviewer finds, and at what cost.

A case is a folder outside the repository (its code is private): `repo/` - a git repository with one commit (the
base) and the change under review uncommitted on top - and `seeds.json` - the known bugs, each with the places a
report may cite it at. Every run reviews its own copy of `repo/`.

    python3 evals/reviewers.py run <case folder> --model opus --variants brief-xhigh builtin-high --runs 3
    python3 evals/reviewers.py summary <case folder>

Variants: the group brief of the review skill given to one Claude Code reviewer at an effort level (brief-xhigh,
brief-high, brief-medium) or to one Claude Code reviewer per group of files (groups-xhigh, groups-medium); the built-in /code-review
(builtin-medium, builtin-high, at the session's own effort); Codex with the group brief (codex-brief), Codex's own
review (codex-review) and its adversarial review as the skill runs it (codex-adversarial). Claude Code reports its tokens and cost; codex exec prints its own token count.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench  # the seed places and the citation matching come from the main bench

VARIANTS = (
    "brief-xhigh",
    "brief-high",
    "brief-medium",
    "builtin-medium",
    "builtin-high",
    "codex-brief",
    "codex-review",
    "codex-adversarial",
    "groups-xhigh",
    "groups-medium",
)
FINDING = re.compile(
    r"^\s*(?:(?:[*_]{1,2})?\d+[.)]|- \[(?:P\d|critical|high|medium|low)\])\s", re.MULTILINE
)  # "1. ", "**2. ", "- [P1] ", "- [high] "
CODEX_TOKENS = re.compile(r"^tokens used\s*\n\s*([\d,]+)", re.MULTILINE)  # its own count: not Claude's measure
JSON_BLOCK = re.compile(r"```json[ \t]*\n(.*?)\n```", re.DOTALL)  # the built-in review lists its findings in one
WORK = Path(__file__).resolve().parent.parent / ".tmp" / "rb"  # the copies under review, away from the cases
FOCUS = (  # the directions the review skill lists for the focus of Codex's adversarial review, the same for every case
    "error handling and silent failures, concurrency and ordering, the migration and its rollback, whether the tests "
    "would fail without the change, the contracts of external APIs and libraries the code relies on"
)
REVIEW_TOOLS = "Bash,Read,Grep,Glob"  # a reviewer reads, runs and builds; it does not edit or start other agents
BUILTIN_TOOLS = "Bash,Read,Grep,Glob,Skill,Agent"  # the built-in review starts its own agents


def changed_files(root: Path) -> list[str]:
    """The files of the change under review: modified ones and new ones, sorted."""
    modified = bench.git(root, "diff", "HEAD", "--name-only").split()
    new = bench.git(root, "ls-files", "-o", "--exclude-standard").split()
    return sorted(set(modified) | set(new))


def split(files: list[str], count: int) -> list[list[str]]:
    """The files in `count` groups by folder: a folder stays whole, the smallest groups are merged first."""
    folders: dict[str, list[str]] = {}
    for name in files:
        folders.setdefault(str(Path(name).parent), []).append(name)
    groups = sorted(folders.values(), key=len)
    while len(groups) > max(count, 1):
        first, second = groups.pop(0), groups.pop(0)
        groups.append(first + second)
        groups.sort(key=len)
    return [sorted(group) for group in groups]


def group_count(root: Path, files: list[str]) -> int:
    """How many groups the review skill would make: under 100 code lines or 1-2 files one, under 500 two, else one
    per three files, from 2 to 4. Counted from the whole change, tests included - a close enough estimate here."""
    lines = 0
    for row in bench.git(root, "diff", "HEAD", "--numstat").splitlines():
        added, deleted, _ = row.split("\t", 2)
        lines += int(added) + int(deleted) if added.isdigit() and deleted.isdigit() else 0
    for name in bench.git(root, "ls-files", "-o", "--exclude-standard").split():
        lines += len((root / name).read_text(encoding="utf-8", errors="replace").splitlines())
    if lines < 100 or len(files) <= 2:
        return 1
    if lines < 500:
        return 2
    return min(max(-(-len(files) // 3), 2), 4)


def brief(root: Path, base: str, files: list[str]) -> str:
    """The group brief of the review skill (plugins/duck-factory/skills/review/SKILL.md), filled in."""
    return (
        f"Review the changes in the repository at `{root}` since `{base}` (`git diff {base}` shows them, uncommitted "
        "files included; new files: `git ls-files -o --exclude-standard`). Your part is these files: "
        + ", ".join(f"`{name}`" for name in files)
        + "; read any other file you need. Do not change any files. Do the review yourself: do not start a review "
        "skill or other reviewers. Read the project's rules first - the instruction files Claude Code would load for "
        "your files (`CLAUDE.md`, `AGENTS.md`, `.claude/rules/` and the like) not already in your context, and the "
        "files they point to that cover your files - and report a change that breaks them as a finding. Read each of "
        "your files in full, not only the changed lines. For every new or changed type, value, message or command "
        "that crosses a function or module boundary, find the code that consumes it - often outside the change - and "
        "check that it handles it rather than dropping it. Check the code against the contracts of the external "
        "APIs, operating-system calls and libraries it relies on, from their documentation or source. Report each "
        "bug separately: what breaks and on what input, file:line, and how you verified it. Number the findings. "
        "Answer in English."
    )


def codex_plugin() -> Path:
    """Where the enabled Codex plugin of Claude Code is installed (its path changes with its version)."""
    plugins = json.loads(
        subprocess.run(["claude", "plugin", "list", "--json"], capture_output=True, text=True, check=True).stdout
    )
    return Path(next(p["installPath"] for p in plugins if p["id"] == "codex@openai-codex" and p["enabled"]))


def variant_command(variant: str, root: Path, prompt: str, out: Path, model: str) -> list[str]:
    """The command line of one reviewer of a variant; Codex writes its final message to `out`/last.txt. Claude Code
    runs on `model`: without it claude -p takes the default model of the settings, which may change mid-bench."""
    claude_json = ["--model", model, "--output-format", "json", "--max-turns", "300"]
    if variant.startswith(("brief-", "groups-")):
        effort = variant.split("-", 1)[1]
        return ["claude", "-p", prompt, "--effort", effort, "--allowedTools", REVIEW_TOOLS, *claude_json]
    if variant.startswith("builtin-"):
        level = variant.split("-", 1)[1]
        return ["claude", "-p", f"/code-review {level} {root}", "--allowedTools", BUILTIN_TOOLS, *claude_json]
    if variant == "codex-brief":
        return ["codex", "exec", "--sandbox", "read-only", "-C", str(root), "-o", str(out / "last.txt"), prompt]
    if variant == "codex-review":
        return ["codex", "review", "--uncommitted"]
    if variant == "codex-adversarial":  # as the review skill runs it at the enhanced tier
        companion = str(codex_plugin() / "scripts" / "codex-companion.mjs")
        return ["node", companion, "adversarial-review", "--wait", "--scope", "working-tree", FOCUS]
    raise ValueError(variant)


def claude_result(raw: str) -> tuple[str, int, float]:
    """The report, the tokens (all models: input, output, cache read and written) and the cost of a claude -p run."""
    try:
        result = json.loads(raw)
    except ValueError:
        return "", 0, 0.0
    if not isinstance(result, dict) or result.get("is_error"):
        return "", 0, 0.0
    tokens = sum(
        usage.get(key, 0)
        for usage in (result.get("modelUsage") or {}).values()
        for key in ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens")
    )
    return str(result.get("result") or ""), tokens, float(result.get("total_cost_usd") or 0.0)


def json_findings(report: str) -> list[dict]:
    """The findings a report gives as a JSON list of objects with `file` and `line`, as the built-in review does."""
    items = []
    for block in JSON_BLOCK.findall(report):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if isinstance(data, list):
            items += [item for item in data if isinstance(item, dict) and "file" in item]
    return items


def codex_tokens(log: str) -> int:
    """The last token count codex exec prints to its log; 0 when it prints none (codex review)."""
    counts = CODEX_TOKENS.findall(log)
    return int(counts[-1].replace(",", "")) if counts else 0


def score(seeds: list[dict], root: Path, report: str) -> list[str]:
    """The titles of the seeds the report cites at one of their places, as file:line or as a JSON finding."""
    pairs = [(seed["title"], [tuple(place) for place in seed["places"]]) for seed in seeds]
    cited = "\n".join([report, *(f"{item['file']}:{item.get('line')}" for item in json_findings(report))])
    found = bench.mentioned(bench.seed_lines(pairs, root), cited)
    return [title for (title, _), hit in zip(pairs, found) if hit]


def count_findings(report: str) -> int:
    """How many findings a report holds: numbered, Codex's "- [P1]" bullets, or a JSON list."""
    return len(FINDING.findall(report)) + len(json_findings(report))


def execute(argv: list[str], cwd: Path, out: Path, timeout: int, env: dict[str, str]) -> tuple[int | None, float]:
    """Run one reviewer in its own process group, so that a timeout stops everything it started."""
    started = time.monotonic()
    with (out / "output.txt").open("w", encoding="utf-8") as stdout, (out / "stderr.txt").open("w") as stderr:
        process = subprocess.Popen(
            argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, start_new_session=True, env=env
        )
        try:
            code: int | None = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            code = None
    return code, time.monotonic() - started


def review(
    variant: str, root: Path, out: Path, timeout: int, env: dict[str, str], parallel_groups: bool, model: str
) -> dict:
    """One reviewer of a variant on `root` (several for groups-*), with its report, tokens, cost and time."""
    base = bench.git(root, "rev-parse", "HEAD").strip()
    files = changed_files(root)
    parts = split(files, group_count(root, files)) if variant.startswith("groups-") else [files]
    folders = [out / f"group-{n}" for n in range(1, len(parts) + 1)] if len(parts) > 1 else [out]

    def one(part: list[str], folder: Path) -> dict:
        folder.mkdir(parents=True, exist_ok=True)
        argv = variant_command(variant, root, brief(root, base, part), folder, model)
        code, seconds = execute(argv, root, folder, timeout, env)
        raw = (folder / "output.txt").read_text(encoding="utf-8", errors="replace")
        if variant.startswith("codex-"):
            last = folder / "last.txt"
            report = last.read_text(encoding="utf-8") if last.is_file() else raw
            tokens, cost = codex_tokens((folder / "stderr.txt").read_text(encoding="utf-8", errors="replace")), 0.0
        else:
            report, tokens, cost = claude_result(raw)
        return {"code": code, "seconds": seconds, "report": report, "tokens": tokens, "cost": cost}

    if parallel_groups and len(parts) > 1:
        with ThreadPoolExecutor(max_workers=len(parts)) as pool:
            results = list(pool.map(one, parts, folders))
    else:
        results = [one(part, folder) for part, folder in zip(parts, folders)]
    return {
        "ok": all(r["code"] == 0 and r["report"].strip() for r in results),
        "report": "\n\n".join(r["report"] for r in results),
        "tokens": sum(r["tokens"] for r in results),
        "cost": round(sum(r["cost"] for r in results), 4),
        "seconds": round(max(r["seconds"] for r in results)),  # groups run side by side in the skill
        "groups": len(parts),
    }


def copy_case(case: Path) -> Path:
    """The case's repository copied into a fresh folder of its own, named after the case: the seeds, the notes and
    the reports of other runs are out of the reviewer's reach, and the path does not say it is a bench."""
    WORK.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(dir=WORK)) / case.name
    shutil.copytree(case / "repo", root, symlinks=True)
    return root


def collect(root: Path, out: Path) -> None:
    """Move the reviewed copy next to the result, for scoring, and drop its work folder with whatever the reviewers
    built, downloaded or wrote beside the copy."""
    shutil.move(root, out / "repo")
    shutil.rmtree(root.parent)


def run_one(case: Path, variant: str, number: int, timeout: int, parallel_groups: bool, model: str) -> dict:
    """Copy the case, run the variant on the copy, then move the copy next to the result, score it and save both."""
    out = case / "runs" / f"{variant}-{number}"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    root = copy_case(case)
    env = dict(os.environ, CARGO_TARGET_DIR=str(root.parent / "target"))  # builds stay out of the reviewed tree
    result = review(variant, root, out, timeout, env, parallel_groups, model)
    collect(root, out)
    seeds = json.loads((case / "seeds.json").read_text(encoding="utf-8"))
    result.update(
        variant=variant,
        number=number,
        found=score(seeds, out / "repo", result["report"]) if result["ok"] else [],
        findings=count_findings(result["report"]),
    )
    (out / "report.md").write_text(result.pop("report"), encoding="utf-8")
    (out / "result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def rescore(case: Path, seeds: list[dict]) -> list[dict]:
    """Every run of the case scored again from its saved report and copy: a change of the scoring needs no new runs."""
    runs = []
    for path in sorted((case / "runs").glob("*/result.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        report = (path.parent / "report.md").read_text(encoding="utf-8")
        found = score(seeds, path.parent / "repo", report) if result["ok"] else []
        result.update(found=found, findings=count_findings(report))
        path.write_text(json.dumps(result, indent=1), encoding="utf-8")
        runs.append(result)
    return runs


def summary(runs: list[dict], seeds: int) -> list[dict]:
    """Per variant: runs that worked, the mean of seeds found, every seed any run found, and the mean cost."""
    rows = []
    for variant in VARIANTS:
        mine = [r for r in runs if r["variant"] == variant]
        if not mine:
            continue
        good = [r for r in mine if r["ok"]]  # a failed run is not "found nothing": it is left out of the means

        def mean(values: list[float]) -> float:
            return round(sum(values) / len(values), 2) if values else 0.0

        rows.append(
            {
                "variant": variant,
                "ok": f"{len(good)}/{len(mine)}",
                "found_mean": mean([len(r["found"]) for r in good]),
                "found_runs": [len(r["found"]) for r in good],
                "union": sorted({title for r in good for title in r["found"]}),
                "of": seeds,
                "findings_mean": mean([r.get("findings", 0) for r in good]),
                "tokens_mean": mean([r["tokens"] for r in good]),
                "cost_mean": mean([r["cost"] for r in good]),
                "seconds_mean": mean([r["seconds"] for r in good]),
            }
        )
    return rows


def adds(runs: list[dict], extra: str, base: str) -> list[str]:
    """The seeds `extra` found in some run that no run of `base` found: what running it alongside would add."""
    seen = {title for r in runs if r["variant"] == base and r["ok"] for title in r["found"]}
    return sorted({title for r in runs if r["variant"] == extra and r["ok"] for title in r["found"]} - seen)


def run_all(case: Path, variants: list[str], runs: int, parallel: int, timeout: int, model: str) -> None:
    """Every variant `runs` times, `parallel` at once. A run that breaks is reported and the others go on: its
    reviewer's answer stays in its folder."""
    lock = threading.Lock()

    def job(item: tuple[str, int]) -> None:
        variant, number = item
        try:
            result = run_one(case, variant, number, timeout, parallel_groups=parallel > 1, model=model)
        except Exception as error:  # noqa: BLE001 - one broken run must not cancel the runs not started yet
            line = f"{variant} #{number}: BROKE, {type(error).__name__}: {error}"
        else:
            line = (
                f"{variant} #{number}: {'ok' if result['ok'] else 'FAILED'}, found {len(result['found'])}, "
                f"{result['findings']} findings, {result['tokens']} tokens, ${result['cost']}, {result['seconds']} s"
            )
        with lock:
            print(line, flush=True)

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        list(pool.map(job, [(variant, n) for n in range(1, runs + 1) for variant in variants]))


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    commands = parser.add_subparsers(dest="action", required=True)
    running = commands.add_parser("run")
    running.add_argument("case", type=Path)
    running.add_argument("--variants", nargs="+", choices=VARIANTS, default=list(VARIANTS))
    running.add_argument("--runs", type=int, default=3)
    running.add_argument("--parallel", type=int, default=3, help="runs at once; 1 for a case whose tests share state")
    running.add_argument("--timeout", type=int, default=2700, help="seconds per reviewer")
    running.add_argument("--model", required=True, help="the Claude model of every claude -p run, such as opus")
    summing = commands.add_parser("summary")
    summing.add_argument("case", type=Path)
    args = parser.parse_args()
    case = args.case.resolve()
    if args.action == "run":
        run_all(case, args.variants, args.runs, args.parallel, args.timeout, args.model)
    seeds = json.loads((case / "seeds.json").read_text(encoding="utf-8"))
    runs = rescore(case, seeds)
    for row in summary(runs, len(seeds)):
        print(json.dumps(row, ensure_ascii=False))
    for extra in ("builtin-medium", "builtin-high", "codex-brief", "codex-review"):
        if any(r["variant"] == extra for r in runs):
            print(f"{extra} adds to brief-xhigh: {adds(runs, extra, 'brief-xhigh')}")


if __name__ == "__main__":
    main()
