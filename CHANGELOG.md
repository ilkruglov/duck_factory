# Changelog

What changed for the user in each version of duck-factory. Both plugins - Claude Code (`plugins/duck-factory`) and
Codex (`plugins/duck-factory-codex`) - carry the same version since 0.2.0, except 0.2.1, which changed the Claude
Code plugin only. The commit messages hold the measurements and the reasons in full. Russian:
[CHANGELOG.ru.md](CHANGELOG.ru.md).

## 0.4.4 - 2026-11-25

- In Codex, the simplification step at the end of `review` no longer rests on the author alone: a fresh sub-agent
  lists simplifications without changing anything while the agent goes through the diff itself, then the agent drops
  what is only taste, changes behaviour or touches code outside the change, and applies the rest with its own - the
  same step as in Claude Code, with a sub-agent in place of Codex. On two finished changes a fresh Codex found 23
  real simplifications, more than a Claude agent with the same directions (14); the author alone was not measured.
- `handoff` files get a `Status` line, as plans do: `active` until the work they hand over is finished or dropped;
  the sentence under it tells the session that finishes the work to change it. The hooks name an active handoff file
  with its date when a session starts - the agent reads it only when you ask to continue that work, so "let's
  continue" is enough - and after a compaction, so that a session working from it reads its traps and decisions
  again; the summary keeps its path. Files without a `Status` line are not named. `grill` takes earlier decisions
  from handoff files marked `done` too.
- The hook takes the `Status` of a plan or handoff file only from the first line of text under the title, written
  plainly or in bold, so a quoted `Status: active` - under the title or further down - no longer marks a file
  active, and it reads only the head of each file, so a bad byte further down no longer hides it; it writes UTF-8
  whatever the console's encoding, so a Windows console no longer garbles or drops Cyrillic. After a compaction the
  hook builds the whole output and measures it as each host does - 9500 UTF-16 units for Claude Code, 19,000 bytes
  of UTF-8 for Codex - and while it does not fit, the largest plan gives way to its path, so the output stays under
  both limits in any script. Dates read "today", "yesterday" or "N days ago" by the calendar. When a session starts,
  the agent reads a named plan, like a handoff file, only when you ask to continue that work.
- The Codex plugin gets the same hook on `SessionStart`: it names the active plans and handoff files when a session
  starts or resumes and brings the plan back in full after a compaction, with `additionalContextLimit` 5000 (Codex
  counts a token as 4 bytes of UTF-8). Codex runs it once you trust it in `/hooks`. Codex ignores what a
  `PreCompact` hook prints, so the request to the summary stays in Claude Code. Checked in a live Codex session.
- A `ruff.toml` keeps the line length at 120, so `ruff format` without flags leaves the code as it is.

## 0.4.3 - 2026-11-24

- `grill` writes the full one-page plan only when the work changes program code: a hook, a service, a script in
  the repository, CI, a config, prompt or data file the code reads. For a skill, a prompt the project's code does
  not read, a document, slides, research or a setup - also with tests next to them -
  it writes a short record instead: the decisions, a default marked as such, the steps and the acceptance criteria,
  each with its check. The confirmation shows the record itself and the user's yes starts the work. The owner
  objected three times to a full plan for slides and skills; the short record still comes back after a compaction,
  and the final report goes through its criteria. Defaults marked in a record are never taken as earlier decisions.

## 0.4.2 - 2026-11-24

- In Claude Code, `review` runs a new set of reviewers, chosen on a measurement on two real changes with 22 important
  bugs known from later fixes, every finding checked against the code. Codex always gets the skill's brief, for the
  whole change, instead of running its own review; from the normal tier Codex's adversarial review runs alongside,
  with a focus the agent writes from the diff; Claude's side is the built-in `/code-review` on the whole change -
  `low` for a light change, `medium` for a normal one, `high` for an enhanced one or one in several groups. Claude
  subagents per group of files run only in a final review now. Together the three found 19 of the 22 important bugs
  with 12.4M Claude tokens; the previous setup for a large change found 18 with 81.5M. The Codex task with the
  brief for the whole change has 30 minutes instead of 15: on a large change it takes longer.
- In a repeat round the Claude subagent runs at effort `medium`. Claude subagents start without a model, so
  they run on the session's model. Without Codex the built-in review goes one level up
  (`high` stays `high`), and outside a final review a change in several groups also gets one Claude subagent with
  the brief for the whole change.
- The simplification step at the end of `review` no longer starts `/simplify`. In Claude Code, Codex lists
  simplifications without changing anything while the agent goes through the diff itself; the agent drops what is
  only taste, changes behaviour or touches code outside the change, and applies the rest with its own. In Codex the
  agent does it alone. The directions are those of `/simplify` - reuse, duplication and dead code, repeated work,
  special cases where a general rule should change - and, in the text of skills and docs, rules repeated or
  contradicting each other. On two finished changes Codex and the agent together found 31 of 37 real
  simplifications; `/simplify` found 17 for four times the Claude tokens and changed behaviour in one of the two changes.

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
