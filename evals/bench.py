"""Benches for the duck-factory skills: a small synthetic project with known bugs put back into its changes.

    python3 evals/bench.py list
    python3 evals/bench.py build <case> <directory>           # only build the repository of a review case
    python3 evals/bench.py review <case> --harness claude     # build it, run the review skill, print the summary
    python3 evals/bench.py grill <prompt> --harness codex     # run a request and show whether grill took it

A review case is a git repository with one commit and an uncommitted change that holds the seeded bugs; no test
of the project fails on them, as with a real bug. The summary says which seeded lines the final report
cites as file:line or file#Lline (a hint only: read the report), the tier line, the time and whether the working
tree stayed untouched.
Runs are kept in `.tmp/evals/`. One run is one sample: repeat it before comparing two versions of a skill.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / ".tmp" / "evals"

# --- the project ------------------------------------------------------------------------

STORE = '''"""Notes kept in one JSON file: a list of {"id", "title", "body", "tags"}."""

from __future__ import annotations

import json
from pathlib import Path

from notes.tags import canonical


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, notes: list[dict]) -> None:
    path.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")


def add(path: Path, title: str, body: str = "", tags: list[str] | None = None) -> dict:
    notes = load(path)
    new_id = max((n["id"] for n in notes), default=0) + 1
    note = {"id": new_id, "title": title, "body": body, "tags": [canonical(t) for t in tags or []]}
    notes.append(note)
    save(path, notes)
    return note
'''

TAGS = '''"""Tag aliases: the table in tags.csv maps what people type to the tag that is stored."""

from __future__ import annotations

import csv
from pathlib import Path


def aliases() -> dict[str, str]:
    with (Path(__file__).parent / "tags.csv").open(newline="", encoding="utf-8") as table:
        rows = list(csv.reader(table))[1:]
    return {alias: tag for alias, tag in rows}


def canonical(tag: str) -> str:
    return aliases().get(tag, tag)
'''

TAGS_CSV = "alias,tag\ntodo,task\nwip,task\nref,reference\n"

CLI = '''"""Command line: python -m notes.cli <file> add <title> | list."""

from __future__ import annotations

import argparse
from pathlib import Path

from notes import store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="notes")
    parser.add_argument("file", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    adding = commands.add_parser("add", help="Add a noet")
    adding.add_argument("title")
    adding.add_argument("--tag", action="append", default=[])
    commands.add_parser("list", help="List the notes")
    args = parser.parse_args(argv)
    if args.command == "add":
        print(store.add(args.file, args.title, tags=args.tag)["id"])
    elif args.command == "list":
        for note in store.load(args.file):
            print(note["id"], note["title"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

TEST_STORE = """from notes import store


def test_add_gives_ids_in_order(tmp_path):
    path = tmp_path / "notes.json"
    assert store.add(path, "first")["id"] == 1
    assert store.add(path, "second")["id"] == 2
    assert [n["title"] for n in store.load(path)] == ["first", "second"]
"""

BASE = {
    "notes/__init__.py": "",
    "notes/store.py": STORE,
    "notes/tags.py": TAGS,
    "notes/tags.csv": TAGS_CSV,
    "notes/cli.py": CLI,
    "tests/test_store.py": TEST_STORE,
    "pyproject.toml": '[project]\nname = "notes"\nversion = "0.1.0"\n\n[tool.pytest.ini_options]\npythonpath = ["."]\n',
    "README.md": '# notes\n\nA tiny notes keeper. `python -m notes.cli notes.json add "Buy milk"`.\n',
    ".gitignore": "__pycache__/\n.pytest_cache/\n.tmp/\n",
}

# --- the changes with seeded bugs -------------------------------------------------------

REMOVE = """

def remove(path: Path, note_id: int) -> bool:
    notes = load(path)
    kept = [n for n in notes if n["id"] != note_id]
    save(path, kept)
    return len(kept) < len(notes)
"""

TEST_REMOVE = """

def test_remove_drops_the_note(tmp_path):
    path = tmp_path / "notes.json"
    store.add(path, "first")
    store.add(path, "second")
    assert store.remove(path, 2)
    assert not store.remove(path, 7)
    assert [n["id"] for n in store.load(path)] == [1]
"""

EXPORT = '''"""Export of notes as CSV or JSON."""

from __future__ import annotations

import json
from pathlib import Path

from notes.store import load


def to_csv(notes: list[dict]) -> str:
    lines = ["id,title,tags"]
    for note in notes:
        lines.append(f"{note['id']},{note['title']},{' '.join(note['tags'])}")
    return "\\n".join(lines) + "\\n"


def to_json(notes: list[dict]) -> str:
    return json.dumps(notes, ensure_ascii=False, indent=2) + "\\n"


def export(path: Path, fmt: str = "csv", limit: int = 0) -> str:
    """The first `limit` notes in the given format; 0 means all of them."""
    notes = load(path)[:limit]
    if fmt == "json":
        return to_json(notes)
    return to_csv(notes)
'''

TEST_EXPORT = """from notes import export, store


def test_export_writes_the_first_notes(tmp_path):
    path = tmp_path / "notes.json"
    for title in ("first", "second", "third"):
        store.add(path, title)
    assert export.export(path, "csv", limit=2) == "id,title,tags\\n1,first,\\n2,second,\\n"
    assert '"title": "first"' in export.export(path, "json", limit=1)
"""


def replace(root: Path, name: str, old: str, new: str) -> None:
    text = (root / name).read_text(encoding="utf-8")
    assert text.count(old) == 1, (name, old)
    (root / name).write_text(text.replace(old, new), encoding="utf-8")


def append(root: Path, name: str, text: str) -> None:
    (root / name).write_text((root / name).read_text(encoding="utf-8") + text, encoding="utf-8")


def change_small(root: Path) -> None:
    """One file, a dozen lines: `remove`, and a "simpler" id that repeats after a removal."""
    replace(root, "notes/store.py", 'max((n["id"] for n in notes), default=0) + 1', "len(notes) + 1")
    append(root, "notes/store.py", REMOVE)
    append(root, "tests/test_store.py", TEST_REMOVE)


def change_feature(root: Path) -> None:
    """Three code files, one of them new: export and removal, with three bugs."""
    change_small(root)
    (root / "notes/export.py").write_text(EXPORT, encoding="utf-8")
    (root / "tests/test_export.py").write_text(TEST_EXPORT, encoding="utf-8")
    replace(root, "notes/cli.py", "from notes import store\n", "from notes import export, store\n")
    replace(root, "notes/cli.py", "add <title> | list.", "add <title> | list | remove <id> | export.")
    replace(
        root,
        "notes/cli.py",
        "    args = parser.parse_args(argv)\n",
        '    removing = commands.add_parser("remove", help="Remove a note")\n'
        '    removing.add_argument("id", type=int)\n'
        '    exporting = commands.add_parser("export", help="Print the notes as CSV or JSON")\n'
        '    exporting.add_argument("--format", choices=["csv", "json"], default="csv")\n'
        '    exporting.add_argument("--limit", type=int, default=0, help="how many notes; 0 for all")\n'
        "    args = parser.parse_args(argv)\n",
    )
    replace(
        root,
        "notes/cli.py",
        "    return 0\n",
        '    elif args.command == "remove":\n'
        "        return 0 if store.remove(args.file, args.id) else 1\n"
        '    elif args.command == "export":\n'
        '        print(export.export(args.file, args.format, args.limit), end="")\n'
        "    return 0\n",
    )


def change_data(root: Path) -> None:
    """Only a data file that the code reads: a row the loader cannot unpack, and an alias defined twice."""
    append(root, "notes/tags.csv", "idea,note\nlater;someday\ntodo,chore\n")


# A seed is a seeded line, given as the places a report can point at: file and a piece of the line.
# The report mentions the seed when it cites one of those lines as file:line, alone or inside a range.
ID_SEED = ("an id repeats after a note is removed", [("notes/store.py", "len(notes) + 1")])
CASES = {
    "small": (change_small, "light", [ID_SEED]),
    "feature": (
        change_feature,
        "normal",
        [
            ID_SEED,
            (
                "the default limit 0 exports nothing",
                [("notes/export.py", "[:limit]"), ("notes/export.py", "limit: int = 0"), ("notes/cli.py", '"--limit"')],
            ),
            ("CSV fields are not quoted", [("notes/export.py", "lines.append(f"), ("notes/export.py", "def to_csv")]),
        ],
    ),
    "data": (
        change_data,
        "light",
        [
            ("a row with a semicolon crashes the loader", [("notes/tags.csv", "later;someday")]),
            ("the alias todo is defined twice", [("notes/tags.csv", "todo,chore"), ("notes/tags.csv", "todo,task")]),
        ],
    ),
}
TIER = re.compile(r"\W*Review:\W*(none|light|normal|enhanced|final|repeat)\b", re.IGNORECASE)  # the first line
# file:line, file:Lline or file#Lline, alone or as a range written without spaces (file:20-30, file#L20-L30)
CITED = re.compile(r"([\w./-]+\.\w+)[:#]L?(\d+)(?:-L?(\d+))?")


def tier_line(report: str) -> str | None:
    """The tier line, when it is the first line of the report, as the skill requires."""
    first = next((line.strip() for line in report.splitlines() if line.strip()), "")
    return first if TIER.match(first) else None


GRILL = {
    "feature": ("interview", "Add export of the notes to CSV and JSON, the format chosen on the command line."),
    "approach": ("interview", "The notes must be stored in something more reliable than a JSON file. Do it."),
    "rename": (
        "interview",
        "Rename the field title to name everywhere: store, CLI and tests, and keep old files readable.",
    ),
    "inferred": (
        "first question: which of the three to do at all",
        "The backlog: 1) export to CSV, 2) full-text search, 3) sync with a server. Do everything.",
    ),
    "named": (
        "interview about how to build both, no question whether to do them",
        "Add export of the notes to CSV, and a search command that looks through titles and tags.",
    ),
    "no-code": (
        "interview and a plan, no review of the plan by another model",
        "I want a short guide for people who move their notes here from a paper notebook. Prepare it.",
    ),
    "bug": ("no interview", "load() in notes/store.py crashes on an empty file. Fix it."),
    "typo": ("no interview", "Fix the typo in the CLI help: it says 'noet' instead of 'note'."),
    "question": ("no interview", "Explain how saving the notes works in this project."),
}

# --- building and running ---------------------------------------------------------------


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


def build(case: str | None, root: Path) -> None:
    """The project with one commit; for a review case, its change on top, uncommitted."""
    if root.exists():
        raise SystemExit(f"{root} already exists")
    for name, text in BASE.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "-c", "user.name=bench", "-c", "user.email=bench@example.invalid", "commit", "-qm", "base")
    if case:
        CASES[case][0](root)


def file_hash(path: Path, size: int) -> bytes:
    """The hash of a file's content, read in pieces: a large file an agent left must not take all the memory."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as file:
            while piece := file.read(1 << 20):
                digest.update(piece)
    except OSError:  # a file the run cannot read is still a change: its size and mode tell
        return f"unreadable {size}".encode()
    return digest.hexdigest().encode()


def snapshot(root: Path) -> str:
    """A hash of the project as the skill left it: the commit, the index with its flags, and every file outside `.git`
    and `.tmp/` (where a skill may write) with its type, mode and content, ignored files included."""
    digest = hashlib.sha256()

    def add(*parts: bytes) -> None:
        for part in parts:  # each part with its length, so that no two different states give the same stream
            digest.update(str(len(part)).encode() + b":" + part)

    for args in (("rev-parse", "HEAD"), ("ls-files", "-s", "-v", "-z")):
        add(subprocess.run(["git", *args], cwd=root, check=True, capture_output=True).stdout)
    for folder, names, files in os.walk(root):
        names[:] = sorted(n for n in names if not (folder == str(root) and n in (".git", ".tmp")))
        for name in sorted(files) + names:
            path = Path(folder) / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                content = os.fsencode(os.readlink(path))
            elif stat.S_ISREG(info.st_mode):
                content = file_hash(path, info.st_size)
            else:
                content = b""
            add(os.fsencode(path.relative_to(root)), str(info.st_mode).encode(), content)
    return digest.hexdigest()


def seed_lines(seeds: list[tuple[str, list[tuple[str, str]]]], root: Path) -> list[set[tuple[str, int]]]:
    """For each seed, the lines it can be cited at, as (path in the project, number), in the project at `root`."""
    return [
        {
            (name, number)
            for name, piece in places
            for number, line in enumerate((root / name).read_text(encoding="utf-8").splitlines(), 1)
            if piece in line
        }
        for _, places in seeds
    ]


def same_file(cited: str, seeded: str) -> bool:
    """Whether a cited path names the seeded file: the same path, or one of them ends with the other at a slash."""
    cited = cited.removeprefix("./")
    return cited == seeded or cited.endswith("/" + seeded) or seeded.endswith("/" + cited)


def mentioned(lines: list[set[tuple[str, int]]], report: str) -> list[bool]:
    """For each seed, whether the report cites one of its lines, alone or inside a range."""
    cited = []
    for match in CITED.finditer(report):
        first = int(match[2])
        last = max(first, int(match[3] or first))  # a reversed range is read as its first line only
        cited.append((match[1], first, last))
    return [
        any(same_file(path, seeded) and low <= number <= high for seeded, number in seed for path, low, high in cited)
        for seed in lines
    ]


def command(
    harness: str, root: Path, prompt: str, model: str | None, write: bool, plugin: Path | None, last: Path
) -> list[str]:
    """The command line of one run. Codex writes its final message to `last`: its output is mostly the trace."""
    model_args = ["--model", model] if model else []
    if harness == "claude":
        plugin_args = ["--plugin-dir", str(plugin)] if plugin else []
        tools = "Bash,Read,Grep,Glob,Skill,Agent" + (",Write,Edit" if write else "")
        return [
            *("claude", "-p", prompt, *model_args, *plugin_args, "--allowedTools", tools),
            *("--output-format", "stream-json", "--verbose", "--max-turns", "70"),
        ]
    sandbox = ["--sandbox", "workspace-write"] if write else []
    return ["codex", "exec", *model_args, *sandbox, "--output-last-message", str(last), "-C", str(root), prompt]


def final_message(harness: str, raw: str, last: Path) -> tuple[str, list[tuple[str, dict]]]:
    """The agent's final message, and for Claude Code the tools it called on the way.

    Only the final message is judged, in both harnesses: the rest of the output holds announcements, the commands
    that were run and the sources that were read, where a seeded bug is "mentioned" by the code itself.
    """
    if harness != "claude":
        return (last.read_text(encoding="utf-8") if last.is_file() else ""), []
    final = ""
    tools: list[tuple[str, dict]] = []
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "result":  # one per turn; a run that waited for background work has several
            final = "" if event.get("is_error") else str(event.get("result") or "")
        elif event.get("type") == "assistant":
            for part in event.get("message", {}).get("content", []):
                if part.get("type") == "tool_use":
                    tools.append((part["name"], part.get("input") or {}))
    return final, tools


def run(kind: str, name: str, harness: str, model: str | None, timeout: int, plugin: Path | None) -> bool:
    """One run and its summary; False when the harness itself failed and there is no result to read."""
    RUNS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")  # the suffix keeps apart runs started in the same second
    folder = Path(tempfile.mkdtemp(prefix=f"{kind}-{name}-{harness}-{stamp}-", dir=RUNS))
    root = folder / "project"
    last = folder / "last-message.txt"
    if kind == "review":
        build(name, root)
        skill = "$review" if harness == "codex" else "Run the duck-factory:review skill on the uncommitted changes."
        prompt = f"{skill} Answer in English."
    else:
        build(None, root)
        prompt = f"{GRILL[name][1]} Answer in English."
    before = snapshot(root)
    seeds = CASES[name][2] if kind == "review" else []
    lines = seed_lines(seeds, root)  # taken before the run: the skill under test may move or delete the files
    started = time.monotonic()
    argv = command(harness, root, prompt, model, write=kind == "grill", plugin=plugin, last=last)
    with (folder / "output.txt").open("w", encoding="utf-8") as out, (folder / "stderr.txt").open("w") as err:
        # A session of its own, so that at the timeout everything the harness started can be stopped with it.
        harness_run = subprocess.Popen(
            argv, cwd=root, stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True
        )
        try:
            code: int | None = harness_run.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(harness_run.pid, signal.SIGKILL)
            harness_run.wait()
            code = None
    seconds = round(time.monotonic() - started)
    raw = (folder / "output.txt").read_text(encoding="utf-8", errors="replace")
    text, tools = final_message(harness, raw, last)

    print(f"{kind} {name}, {harness}: {seconds} s, output in {folder}")
    if code != 0 or not text.strip():
        why = f"no answer in {timeout} s" if code is None else f"exit code {code}" if code else "no final message"
        errors = (folder / "stderr.txt").read_text(encoding="utf-8", errors="replace").strip().splitlines()[-5:]
        print(f"  THE RUN FAILED ({why}); there is no result to judge.\n    " + "\n    ".join(errors))
        return False
    print(f"  working tree untouched (outside .tmp/): {'yes' if snapshot(root) == before else 'NO'}")
    if kind == "review":
        print(f"  tier line: {tier_line(text) or 'not the first line'} (expected tier: {CASES[name][1]})")
        for (title, _), found in zip(seeds, mentioned(lines, text)):
            print(f"  {'cited  ' if found else 'MISSING'}  {title}")
    else:
        print(f"  expected: {GRILL[name][0]}")
        if harness == "claude":
            grill = any(tool == "Skill" and "grill" in str(args.get("skill")) for tool, args in tools)
            other = any(
                tool == "Bash" and re.search(r"\bnode\b.*codex-companion\.mjs", str(args.get("command")))
                for tool, args in tools
            )
            print(f"  grill skill called: {'yes' if grill else 'no'}")
            print(f"  another model called: {'yes' if other else 'no'}")
        plans = sorted((root / ".tmp" / "plans").glob("*.md"))
        print(f"  plan written: {plans[0] if plans else 'no'}")
        print("  the reply ends with:\n    " + "\n    ".join(text.strip().splitlines()[-12:]))
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("list")
    building = commands.add_parser("build")
    building.add_argument("case", choices=sorted(CASES))
    building.add_argument("directory", type=Path)
    for action, names in (("review", CASES), ("grill", GRILL)):
        running = commands.add_parser(action)
        running.add_argument("name", choices=sorted(names))
        running.add_argument("--harness", choices=["claude", "codex"], required=True)
        running.add_argument("--model", help="passed to the harness as is; its default model otherwise")
        running.add_argument("--timeout", type=int, default=1500, help="seconds")
        running.add_argument(
            "--plugin-dir",
            type=Path,
            help="Claude Code only: load the plugin from this folder, to try a working copy before it is published",
        )
    args = parser.parse_args()
    if args.action == "list":
        for name, (change, tier, seeds) in CASES.items():
            print(f"review {name}: {(change.__doc__ or '').strip()} Expected tier: {tier}; seeded bugs: {len(seeds)}.")
        for name, (expected, prompt) in GRILL.items():
            print(f"grill {name}: {prompt!r} Expected: {expected}.")
    elif args.action == "build":
        build(args.case, args.directory.resolve())
        print(git(args.directory.resolve(), "status", "--short"), end="")
    else:
        plugin = args.plugin_dir.resolve() if args.plugin_dir else None
        if not run(args.action, args.name, args.harness, args.model, args.timeout, plugin):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
