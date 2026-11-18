"""Hooks around a compaction: keep the project's active plan and the state of the work from being lost.

A plan written by the grill skill lives in `.tmp/plans/` and carries a `Status: active` line until the user has
accepted the result or the work is dropped.

- PreCompact: what the script prints becomes instructions for the summary. It asks to keep what real sessions
  went back to the transcript for after a compaction, and names the active plans.
- SessionStart after a compaction or a resume: what it prints is added to the context. It prints the active
  plans themselves.
- SessionStart of a new session: it only names the active plans, because the session may be about something else.

The script only reads files and never fails the session: on any problem it prints nothing.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

# The first Status line decides, with or without Markdown around it; a later one is a quote or an example.
STATUS = re.compile(r"^[\s>*_`#-]*Status[\s*_`]*:[\s*_`]*([A-Za-z]+)", re.IGNORECASE | re.MULTILINE)
HEAD_CHARS = 2000  # the Status line is at the top of the plan
MAX_PLANS = 3
BUDGET = 8000  # characters of plan text; Claude Code moves hook output over 10,000 to a file
CLOSING = (
    "When the user has accepted the result, change the plan's Status line to done; when the work is cancelled, "
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

Plan = tuple[Path, str, float]  # path, text, time of the last change


def is_repository(folder: Path) -> bool:
    """A `.git` file (a worktree, a submodule) or a `.git` directory with HEAD; a stray empty folder is neither."""
    marker = folder / ".git"
    return marker.is_file() or (marker / "HEAD").is_file()


def plan_dirs(cwd: Path) -> list[Path]:
    """Every `.tmp/plans` from cwd up to the repository root; outside a repository, the one in cwd."""
    chain = [cwd, *cwd.parents]
    root = next((i for i, folder in enumerate(chain) if is_repository(folder)), 0)
    return [folder / ".tmp" / "plans" for folder in chain[: root + 1]]


def active_plans(folders: list[Path]) -> list[Plan]:
    """The newest active plans; a folder that does not exist holds none."""
    found: list[Plan] = []
    for path in (path for folder in folders for path in folder.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
            status = STATUS.search(text[:HEAD_CHARS])
            if status and status.group(1).lower() == "active":
                found.append((path, text, path.stat().st_mtime))
        except (OSError, UnicodeDecodeError):
            continue
    found.sort(key=lambda plan: plan[2], reverse=True)
    return found[:MAX_PLANS]


def in_full(plans: list[Plan]) -> str:
    out = [INTRO]
    left = BUDGET
    for path, text, _ in plans:
        fits = len(text) <= left
        left -= len(text) if fits else 0
        body = text.rstrip() if fits else "Too long to show here: read this file before continuing the work."
        out.append(f"\n--- {path} ---\n{body}")
    return "\n".join(out) + "\n"


def by_name(plans: list[Plan]) -> str:
    out = ["This project has an active plan written by the grill skill; it is not loaded here:"]
    for path, _, changed in plans:
        days = int((time.time() - changed) // 86400)
        out.append(f"- {path} (last changed {'today' if days == 0 else f'{days} days ago'})")
    out.append("Read it if this session continues that work. " + CLOSING)
    return "\n".join(out) + "\n"


def for_summary(plans: list[Plan]) -> str:
    out = [SUMMARY]
    if plans:
        paths = ", ".join(str(path) for path, _, _ in plans)
        out.append(
            f"- Active plan: {paths}. Name the path and do not copy the plan: it is shown again in full after the"
            " compaction."
        )
    return "\n".join(out) + "\n"


def main() -> None:
    try:
        event = json.loads(sys.stdin.read())
        kind, source = event.get("hook_event_name"), event.get("source")
        # The user's own instructions for a compaction come first: do not compete with them.
        if kind not in ("PreCompact", "SessionStart") or (kind == "PreCompact" and event.get("custom_instructions")):
            return
        plans = active_plans(plan_dirs(Path(event["cwd"])))
        if kind == "PreCompact":
            sys.stdout.write(for_summary(plans))
        elif plans:
            # The work goes on after a compaction or a resume; any other start may be about something else.
            sys.stdout.write(in_full(plans) if source in ("compact", "resume") else by_name(plans))
    except Exception:  # noqa: BLE001 - a reminder must never break a compaction or the start of a session
        return


if __name__ == "__main__":
    main()
