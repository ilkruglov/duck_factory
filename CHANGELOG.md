# Changelog

What changed for the user in each version of duck-factory. Both plugins - Claude Code (`plugins/duck-factory`) and
Codex (`plugins/duck-factory-codex`) - carry the same version since 0.2.0, except 0.2.1, which changed the Claude
Code plugin only. The commit messages hold the measurements and the reasons in full. Russian:
[CHANGELOG.ru.md](CHANGELOG.ru.md).

## 0.4.1 - 2026-11-23

Shorter repeat rounds in `review`. In one project two tasks went through 18 review rounds in two days, 30 to 60
minutes each, because every small fix was followed by a full review of the whole change.

- A repeat round after fixes checks only the fixed places: the fix, the code that calls it, the code it calls and its
  tests. The agent keeps the list of fixed places itself.
- Its reviewers go by where the fixes are: in Claude Code one Codex task and one Claude subagent for each group where
  something was fixed (the subagent alone without Codex), in Codex one sub-agent per group.
- The report names, next to each confirmed bug, the places where the same logic repeats; a yes covers those, and the
  same bug found anywhere else is shown to the user first.
- While fixing, only the tests of the fixed place run; the full suite runs once per round.
- The simplification step (`/simplify` in Claude Code, the agent itself in Codex; one subagent for the text of skills
  and docs) runs once, at the end, followed by the tests and one check that the behaviour stayed the same.
- After the third repeat round the skill stops and asks whether to go on, simplify the approach or accept what is
  left, with how many real bugs each round brought.
- `grill` first asks whether to commit accepted work of another task that is still uncommitted, so the review of the
  new task reads only the new change.

## 0.4.0 - 2026-11-23

- The briefs of the group reviewers and of the security pass tell them to read the project's rules (in Claude Code
  `CLAUDE.md`, `.claude/rules/` and the like; in Codex `AGENTS.md`) and to report a change that breaks them.
- A security pass, only after the user says yes, or at once when the user asked for it: offered once per piece of
  work in a final review and when the change touches a path listed under `Security paths`; it looks only for
  reachable vulnerabilities and marks each critical, high, medium or low. Security scanners are not part of it: the
  Codex Security plugin did not start a scan of changes in three runs out of three, and Claude Security scans
  committed changes only.
- A yes covers only the findings the user has seen; the questions at the end of a report are numbered.
- The failing test of a fix must fail on the bug itself, not on an import error or a typo.
- The simplification step for the text of skills, prompts and docs is one subagent (instead of `/simplify` in Claude
  Code).
- `grill` takes a decision already made from the decisions of an accepted earlier plan or the project's rules, with
  its source, instead of asking again; when two plans disagree, it asks.
- The bench reads files in pieces: a large file an agent left no longer takes all the memory.

## 0.3.0 - 2026-11-20

- A final review of everything since the work started, before a pull request, a merge or a release: on a real fork
  one review of the whole change found eight bugs that the step-by-step reviews had missed.
- At the normal and enhanced tiers a large change is split by subsystem into up to four groups; in Claude Code each
  group gets a Codex task and a fresh Claude subagent, in Codex one sub-agent. A change that fits one group keeps the
  built-in review and Codex.
- Codex runs the model from its own configuration instead of a pinned one; `review` gives its briefs to Codex as
  files.
- "One-way door" is about what the change does to what already exists, not what a new feature lets users do later.
- `grill` for Codex asks by mode: `request_user_input` in Plan mode, else the async tools, always repeated in the
  final message.

## 0.2.1 - 2026-11-18

- A resumed session gets the active plan's name instead of its full text: the full text came back on every resume
  and cost two to three thousand tokens each time. After a compaction the plan still comes back in full, if it fits
  in 8000 characters.
- README in Russian next to the English one.

## 0.2.0 - 2026-11-18

- `grill` asks first which tasks to do at all when a set of tasks was approved wholesale or proposed by the agent;
  plans carry `Status` and `Source`; it works for tasks without code too.
- `review` counts lines without indentation-only changes (a file whose whole change is indentation still counts),
  counts a data file the code reads as code, takes the tier from the table only, and before the report removes what
  it created outside `.tmp/`.
- Hooks for Claude Code: before a compaction the summary is asked to keep exact commands, unchecked work, the user's
  consents and corrections; after a compaction or a resume the active plan comes back in full (a plan longer than
  8000 characters is named instead).
- `evals/bench.py`: a synthetic project with seeded bugs to run the skills on, in Claude Code or Codex.

## 0.1.1 - 2026-11-11

- `grill` loads the skills that cover the task's area before the first question, and the plan names them.
- A detailed README: how a session goes, how the tier is picked, a sample report, time and cost.
- The same day: the Codex version of the plugin (its own 0.1.0) - the three skills inside Codex, each check in a
  sub-agent with a fresh context (in the session itself when sub-agents are not available, and the report says so).

## 0.1.0 - 2026-11-11

- Three skills: `grill` (agree on a non-trivial task before code, with a one-page plan), `review` (one code review
  with a tier measured from the change, the built-in review and Codex in parallel, every finding checked before the
  report and marked confirmed, not confirmed or not checked) and
  `handoff` (a file a fresh session checks against reality before it continues).
