"""Hooks around a compaction: keep the project's active plan and the state of the work from being lost.

A plan written by the grill skill lives in `.tmp/plans/` and carries a `Status: active` line until the user has
accepted the result or the work is dropped.

- PreCompact: what the script prints becomes instructions for the summary. It asks to keep what real sessions
  went back to the transcript for after a compaction, and names the active plans.
- SessionStart after a compaction: what it prints is added to the context. It prints the active plans
  themselves, because the compaction is what loses them.
- Any other SessionStart (a new session, a resume): it only names the active plans. A new session may be about
  something else, and a resumed one still has its history: printing the plan on every resume would add a copy.

A handoff file written by the handoff skill lives in `.tmp/handoff/` with the same Status line, active until the
work it hands over is finished. The hook only names it, with its date: at the start of a session, so that the user
need not remember the path; after a compaction, so that a session working from it reads its traps and decisions
again; and before a compaction, so that the summary keeps the path.

The script only reads files and never fails the session: on any problem it prints nothing.
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

# The Status line as the grill and handoff skills write it, plain or in bold. Only the first line of text under the
# title counts, and nothing else passes for it: a quote, a heading or a list item is not the file's own status.
STATUS = re.compile(r"^(?:Status:|\*\*Status:\*\*|__Status:__)\s*(?P<value>[A-Za-z]+)(?![\w-])", re.IGNORECASE)
HEAD_BYTES = 2000  # the title and the Status line under it
MAX_FILES = 3  # plans or handoff files named or shown at once
# Claude Code moves hook output over 10,000 UTF-16 units to a file; Codex counts 4 bytes of UTF-8 as a token and
# moves output over the hook's limit (5000) to a file. Under 9500 units and 19,000 bytes it is under both.
LIMIT = 9500
TOO_LONG = "Too long to show here: read this file before continuing the work."
UNREADABLE = "Could not be read: it may have been moved or removed."
ON_REQUEST = (
    "Read it only when the user asks to continue that work: a new session may have been started to get away from it."
)
CLOSING = (
    "When the user has accepted the result, change the plan's Status line to done; when the work is cancelled, "
    "to dropped."
)
HANDOFF_CLOSING = (
    "When the handed-over work is finished, change the handoff file's Status line to done; when it is dropped, "
    "to dropped."
)
INTRO = (
    "Active plan of this project, written by the grill skill. The plan, not the summary of the conversation, "
    "is the source of truth for the work it covers. " + CLOSING
)
SUMMARY = """In the summary, also keep the following, each under its own heading; write "none" where there is nothing:
- Exact commands: the full command lines that produced results still in use (builds, renders, exports, deploys) \
and that started what is still running, with ids and paths - word for word, not described.
- Long materials: texts the user pasted, reports of sub-agents and long tool outputs the work still needs - \
for each, the file it is saved in, or a phrase that finds it in the transcript.
- Done, not checked: what was changed or claimed with no test, command or measurement behind it, and how far \
any long pass (a reading, a migration, a batch) has got.
- Waiting on the user: open questions, and what the user has and has not agreed to so far.
- Standing corrections: what the user said about how to work, as rules still in force, in the user's words, \
with how many times each had to be repeated."""

Found = tuple[Path, float]  # an active plan or handoff file, and the time of its last change


def is_repository(folder: Path) -> bool:
    """A `.git` file (a worktree, a submodule) or a `.git` directory with HEAD; a stray empty folder is neither."""
    marker = folder / ".git"
    return marker.is_file() or (marker / "HEAD").is_file()


def tmp_dirs(cwd: Path, name: str) -> list[Path]:
    """Every `.tmp/<name>` from cwd up to the repository root; outside a repository, the one in cwd."""
    chain = [cwd, *cwd.parents]
    root = next((i for i, folder in enumerate(chain) if is_repository(folder)), 0)
    return [folder / ".tmp" / name for folder in chain[: root + 1]]


def status(lines: list[str]) -> str | None:
    """The status in the first line of text under the title; None when that line is not a Status line."""
    lines = [line for line in lines if line.strip()]
    if lines and lines[0].lstrip().startswith("#"):  # the title
        lines = lines[1:]
    found = STATUS.match(lines[0]) if lines else None
    return found.group("value").lower() if found else None


def active_files(folders: list[Path]) -> list[Found]:
    """The newest active plans or handoff files; a folder that does not exist holds none."""
    found: list[Found] = []
    for path in (path for folder in folders for path in folder.glob("*.md")):
        try:
            with path.open("rb") as file:  # only the head: a bad byte further down must not hide the file
                head = file.read(HEAD_BYTES + 1)
            lines = head[:HEAD_BYTES].decode("utf-8-sig", errors="replace").splitlines()
            if len(head) > HEAD_BYTES:  # the file goes on: its last line here may be cut, and is not a whole one
                lines = lines[:-1]
            if status(lines) == "active":
                found.append((path, path.stat().st_mtime))
        except OSError:
            continue
    found.sort(key=lambda item: item[1], reverse=True)
    return found[:MAX_FILES]


def show(plans: list[Found], bodies: list[str]) -> str:
    return "\n".join([INTRO, *(f"\n--- {path} ---\n{body}" for (path, _), body in zip(plans, bodies))]) + "\n"


def weight(text: str) -> int:
    """Bytes in UTF-16 or in UTF-8, whichever is more: Claude Code counts the one, Codex the other."""
    return max(len(text.encode("utf-16-le", errors="replace")), len(text.encode("utf-8", errors="replace")))


def body(path: Path) -> tuple[str, bool]:
    """The plan's text and True; or, when it cannot be shown, the note that takes its place and False."""
    try:
        with path.open("rb") as file:
            raw = file.read(2 * LIMIT + 1)  # a longer plan cannot fit: it is not read whole
    except OSError:  # gone since it was found: named, and the rest still shown
        return UNREADABLE, False
    if len(raw) > 2 * LIMIT:
        return TOO_LONG, False
    return raw.decode("utf-8-sig", errors="replace").rstrip(), True


def in_full(plans: list[Found], tail: str) -> str:
    """The plans in full and then `tail`; while that does not fit, the largest plan shown gives way to a note."""
    bodies, whole = [], []
    for path, _ in plans:
        text, readable = body(path)
        bodies.append(text)
        whole.append(readable)
    while True:
        out = "\n".join(part for part in (show(plans, bodies), tail) if part)
        shown = [n for n in range(len(plans)) if whole[n]]
        if weight(out) <= 2 * LIMIT or not shown:
            return out
        largest = max(shown, key=lambda n: (weight(bodies[n]), n))  # of two equal plans the older, later in the list
        bodies[largest], whole[largest] = TOO_LONG, False


def when(changed: float) -> str:
    today = datetime.date.today()
    day = min(datetime.date.fromtimestamp(changed), today)  # a clock ahead of this one is not the future
    days = (today - day).days
    return f"last changed {day.isoformat()}, " + (
        "today" if days == 0 else "yesterday" if days == 1 else f"{days} days ago"
    )


def by_name(plans: list[Found]) -> str:
    out = ["This project has an active plan written by the grill skill; it is not loaded here:"]
    out += [f"- {path} ({when(changed)})" for path, changed in plans]
    out.append(f"{ON_REQUEST} {CLOSING}")
    return "\n".join(out) + "\n"


def handoffs_by_name(handoffs: list[Found], after_compaction: bool) -> str:
    """The active handoff files, named with their date: they are a page or two, and the session may not need them."""
    if after_compaction:
        out = ["Active handoff file of this project, work handed over from an earlier session:"]
        advice = f"If this session works from it, read its traps and decisions again before going on. {HANDOFF_CLOSING}"
    else:
        out = [
            "This project has an active handoff file, work handed over from an earlier session; it is not loaded here:"
        ]
        advice = ON_REQUEST
    out += [f"- {path} ({when(changed)})" for path, changed in handoffs]
    out.append(advice)
    return "\n".join(out) + "\n"


def for_summary(plans: list[Found], handoffs: list[Found]) -> str:
    out = [SUMMARY]
    if plans:
        paths = ", ".join(str(path) for path, _ in plans)
        out.append(
            f"- Active plan: {paths}. Name the path and do not copy the plan: it is shown again in full after the"
            " compaction."
        )
    if handoffs:
        paths = ", ".join(str(path) for path, _ in handoffs)
        out.append(f"- Active handoff file: {paths}. Name the path if this session works from it.")
    return "\n".join(out) + "\n"


def emit(text: str) -> None:
    """UTF-8 whatever the console's encoding: on Windows it may have no Cyrillic, and the hook runners read UTF-8."""
    sys.stdout.buffer.write(text.encode("utf-8", errors="replace"))  # a file name may not be UTF-8
    sys.stdout.buffer.flush()


def main() -> None:
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        kind, source = event.get("hook_event_name"), event.get("source")
        # The user's own instructions for a compaction come first: do not compete with them.
        if kind not in ("PreCompact", "SessionStart") or (kind == "PreCompact" and event.get("custom_instructions")):
            return
        cwd = Path(event["cwd"])
        plans, handoffs = active_files(tmp_dirs(cwd, "plans")), active_files(tmp_dirs(cwd, "handoff"))
        if kind == "PreCompact":
            emit(for_summary(plans, handoffs))
            return
        after_compaction = source == "compact"
        named = handoffs_by_name(handoffs, after_compaction) if handoffs else ""
        # Only a compaction loses the plan; a resumed session still has it, a new one may not need it.
        if plans and after_compaction:
            emit(in_full(plans, named))
        else:
            emit("\n".join(part for part in (by_name(plans) if plans else "", named) if part))
    except Exception:  # noqa: BLE001 - a reminder must never break a compaction or the start of a session
        return


if __name__ == "__main__":
    main()
