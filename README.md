# duck_factory

A plugin for Claude Code and for Codex CLI (`duck-factory`). The sections below describe the Claude Code
version; [Codex](#codex) lists what differs.

Three skills that make a small development pipeline for Claude Code: agree on the task before code, review
the result once with a depth that fits the change, and hand the work over to a fresh session.

| Skill | When it runs | What it does |
|---|---|---|
| `grill` | by itself, before a non-trivial change; or `/duck-factory:grill` | Interviews you in short rounds through the question dialog, recommended option first, then writes a one-page plan to `.tmp/plans/`. For large tasks the plan is checked by Codex before any code. |
| `review` | by itself, after a finished code change; or `/duck-factory:review` | Measures the change (code lines, files, call sites, reversibility), picks a tier, runs the built-in `/code-review` and Codex in parallel plus a check against the plan, verifies every finding, and reports. It only finds; fixes come after you agree. |
| `handoff` | only on `/duck-factory:handoff` | Writes `.tmp/handoff/<slug>.md` so a fresh session can continue: goal, constraints, decisions, what is done and how it was checked, what is in flight, the next step, rollback. The file starts by telling the next session to check it against reality. |

## The pipeline

1. `grill` loads the skills for the area, settles the decisions and writes the plan with acceptance criteria.
2. You approve the plan; the work goes test first.
3. `review` runs once, before the report or a commit.
4. After you agree: a failing test and a fix for each confirmed bug, `/simplify`, the tests, and a repeat review
   aimed at the fixed places.
5. `handoff` when the work continues in another session.

Nothing here replaces your approval: `grill` changes nothing until you confirm, the plan is not consent to edit
code, and `review` never edits files.

## grill

Runs before code when the task is not trivial: a new feature or module, a choice between approaches, a change in
several places, an unclear goal. For a bug fix or a small clear edit it says the task is clear and steps aside.

How a session goes:

1. **Skills for the area.** If the task touches something another installed skill covers (a framework, a kind
   of system, the project's design rules), that skill is loaded first: it changes which questions are worth
   asking.
2. **Facts first.** Anything that can be looked up in the code, configs or logs is looked up, not asked.
3. **Questions in rounds**, through the question dialog: at most four per round, the most consequential first,
   two to four options each, the recommended one first. Every question carries the fact it hinges on. From the
   second round on, the last question lets you stop: "enough, take your recommendations for the rest".
4. **Confirmation** with the decisions and the defaults taken without asking.
5. **The plan**, one page in `.tmp/plans/<slug>.md`:

```markdown
# Export notes

Goal: `notes export --format csv|json` prints all notes to stdout.

Skills used: none

Decisions:
- CSV through the standard csv module, fields id,title,text - no new dependency.
- An empty store exports an empty set, not an error - same as `list`.

Taken by default, not asked:
- `--format` is required - no obvious default between the two.

Not touching: the storage format, the add and list commands.

Acceptance criteria (each checked by a test or a command):
- `notes export --format csv` prints a header and one row per note - tests/test_cli.py::test_export_csv
- An unknown format exits with an argparse error - tests/test_cli.py::test_export_bad_format

Risks and open questions: none
```

For a large task (a new module, an approach that is costly to reverse, more than a session of work) the plan is
then checked by Codex against the repository, read-only. Its findings that are decisions come back to you as
questions.

While working by the plan, the skill re-reads the file after a context compaction or in a new session, does not
change a decision silently, and ends the report by going through the acceptance criteria one by one.

## review

Runs once after a finished code change. It answers three questions: is there a bug, does the change match the
plan, and can each finding be proved.

### How the tier is picked

The skill measures everything uncommitted (modified, staged and new files) and prints the result in one line:

`Review: normal - 132 code lines, 3 files, 7 call sites, reversible.`

- **Code lines**: added plus deleted, without tests, docs and data or config files.
- **Files**: code files changed.
- **Call sites**: places in code (not tests) that use a function, method or class whose behaviour or signature
  changed.
- **One-way door**: something that cannot simply be reverted - a data migration, deleting data or files, a
  release, an external API contract, the format of files already on disk.

| Tier | When | Built-in review | Codex | Plan check |
|---|---|---|---|---|
| none | no code lines changed | - | - | - |
| light | up to 50 code lines, 1 file, up to 5 call sites, reversible | `low` | review | no |
| normal | everything else | `medium` | review | yes |
| enhanced | a one-way door, over 10 files, over 20 call sites, or you asked | `high` | adversarial, with a focus | yes |
| repeat | after fixes | as light, aimed at the fixes | review | no |

A one-way door outweighs the other signs; in doubt the higher tier wins; `max` only when you ask for it by name.

Why these tiers. They come from a measurement on three diffs with seeded bugs (9, 16 and 581 lines, one run per
cell):

| Check | 9 lines, 1 bug | 16 lines, 3 bugs | 581 lines, 3 bugs |
|---|---|---|---|
| built-in `low` | 1/1, 10 s | 3/3, 25 s | 2/3, 28 s |
| built-in `medium` | 1/1, 34 s | 3/3, 45 s | 3/3, 101 s |
| built-in `high` | 1/1, 73 s | 3/3, 114 s | 3/3, 219 s |
| Codex | 1/1, 61 s | 3/3, 79 s | 3/3, 79 s |

`medium` and Codex found everything; `high` took twice as long for the same bugs and adds extra observations
rather than missed bugs; `low` is enough for a small change and loses a bug in a large one. The call-site
thresholds are a cautious guess, not a measurement.

### What the checks are

- **Built-in review**: Claude Code's `/code-review` at the tier's level. It also checks the diff against your
  `CLAUDE.md`.
- **Codex**: a second opinion from another model, through the `codex@openai-codex` plugin. In the enhanced tier
  it runs as an adversarial review with a focus taken from the diff: silent failures, ordering and concurrency,
  the migration and its rollback, whether the tests would fail without the change.
- **Plan check**: what the plan asked for and is missing, what was done beyond the plan, which acceptance
  criteria nothing checks. It uses the plan `grill` wrote in this session, or one named in the handoff file or
  passed as an argument; with no plan it is skipped, and the report says so.

All of them run in parallel.

### Verified findings

Reviewers are wrong in the same confident tone they are right in. Every finding that claims a bug is checked
before the report: the code is read at the cited lines and, where it is cheap, the bug is reproduced with a short
script in `.tmp/`. Each finding gets a mark:

- **confirmed** - with the command and its result, or the lines that prove it;
- **not confirmed** - with the reason; listed at the end so you can disagree;
- **not checked** - with the reason.

Duplicates from different reviewers are merged, with the names of who found them.

### The report

```text
Review: light - 9 code lines, 1 file, 1 call site, reversible.

Bugs
1. The file limit counts names that are not watched, so watching can switch off for no reason.
   watcher.py:474-477. Confirmed: .tmp/repro_limit.py - before the change enabled=True, after it
   enabled=False on the same four files. Found by the built-in review and Codex.

Plan check
Skipped: no plan in this session.

Quality notes
- The change removes the comment that explained why the filter comes before the count.

Not confirmed
None.

Not covered: the real server was not started; case-insensitive file systems were not checked.

Fix the confirmed bug and run /simplify?
```

A finding that is a decision rather than a bug goes to you as its own question, not into the fix list.

### After you agree

A failing test, the fix and a test run for each confirmed bug; then `/simplify`; then the project's tests; then
a repeat review of the whole change at the light tier, aimed at the functions and files just fixed. Findings the
previous round already reported are dropped. If two rounds in a row find only edge cases in the same place, the
skill stops and asks you whether to simplify the approach or accept the limits.

### Without Codex

A limit, no login, a model error or no answer within five minutes: the skill does not retry and does not switch
the model. It says so in one line, raises the built-in review one level (`low` to `medium`, `medium` to `high`),
gives the plan check to a subagent with a fresh context, and does not call Codex again in that session unless
you say it is back.

### Time and cost

From runs on the three benchmark diffs with an Opus-class model: a light review took 2 to 2.5 minutes and about
$0.70 to $1.00, a normal one about 5 minutes and $1.40. The checks themselves take 1.5 to 2 minutes; the rest is
reproducing the findings.

## handoff

Runs only when you type `/duck-factory:handoff`, optionally with what the next session is for. It writes
`.tmp/handoff/<slug>.md`, or updates the file this work already has:

```markdown
# Empty-file crash in load - handoff, 2026-11-11

First, check this file against reality: `git status` and `git log -3`, whether the processes under "In flight"
still run, whether the files named here exist. Tell the user what differs before doing anything else.

Goal: `store.load` crashed on an empty file; it must return [].

Constraints: do not touch cli.py without a separate go-ahead.

Read first: store.py:6-10 (the fix), tests/test_store.py:12-24 (two new tests).

Decisions and why: a whitespace-only file counts as empty; broken non-empty JSON still raises.

Done and checked:
- the fix is in the working tree - `git status --short` shows store.py and tests/test_store.py

Done, not checked: the new tests were never run - the test command needed a permission.

In flight: uncommitted changes in two files, branch main; no background processes.

Left to do: run the tests without and with the fix; review; commit.

Next step: run the tests without the fix and see the two new ones fail.

Traps: compound shell commands need a separate approval here; run them one at a time.

Waiting on the user: cli.py:21 crashes without notes.json - a separate bug, not touched.

Rollback: the work started from commit adb43c6; `git checkout -- store.py tests/test_store.py`.
```

The first paragraph matters most: the file goes stale as soon as anything changes between sessions, and it can
be wrong itself. In a test where the fix was reverted behind its back, the next session opened with "the
handoff differs from the repository" and asked before doing anything.

## Codex

The same pipeline for Codex CLI lives in `plugins/duck-factory-codex` and works entirely inside Codex.

```bash
codex plugin marketplace add ilkruglov/duck_factory
codex plugin add duck-factory@duck-factory
```

What differs from the Claude Code version:

| | Claude Code | Codex |
|---|---|---|
| Who reviews | the built-in `/code-review` and Codex, two models | sub-agents of the same model, started with a fresh context (`fork_turns="none"`) |
| light | `low` + Codex | one general pass |
| normal | `medium` + Codex + plan check | one general pass + plan check |
| enhanced | `high` + adversarial Codex + plan check | one adversarial pass instead of the general one + plan check |
| Questions in `grill` | the question dialog, up to 4 per round | `request_user_input` when the session has it (up to 3 per round), else text |
| Domain skills in `grill` | loaded with the Skill tool | their `SKILL.md` is read |
| Plan check in `grill` | Codex, read-only | a sub-agent with a fresh context |
| Simplification after fixes | `/simplify` | a step inside the skill |
| `handoff` is manual through | `disable-model-invocation` | `agents/openai.yaml`, `allow_implicit_invocation: false` |

Why one pass and not two in the enhanced tier. On two benchmarks (three seeded bugs in a 581-line diff, four
seeded bugs of other kinds in a 4-line diff) the adversarial brief found exactly the bugs the general brief
found, in every run, and took 2 to 2.5 times longer. What it adds is a reproduction for each finding and the
gaps in the tests, which is what a change that cannot be reverted needs. A second pass by the same model did
not find bugs the first one missed.

The honest limit: there is no second model here. On the larger benchmark both Codex briefs missed two real
problems that the `high` level of the other model had found. If you have both tools, the Claude Code version
gives the stronger review.

From runs on the same three benchmark diffs: a light review took about 2 minutes, a normal one about 2.5, and
every seeded bug was found without changing the tree.

Lines for your `AGENTS.md`, so the skills run by themselves:

```markdown
- A non-trivial task (a new feature or module, a choice between approaches, a change in several places, an
  unclear goal): first the `grill` skill, then code.
- After your own finished code change, before the report and a commit: the `review` skill, once. When you were
  started as the reviewer of someone else's diff, the skill is not needed: just review.
```

The second sentence matters when another tool calls Codex as a reviewer: without it a plain review request could
start the whole skill.

## Requirements

- Claude Code with the built-in `/code-review` and `/simplify`.
- For the second opinion and the plan check: the `codex@openai-codex` plugin, logged in. Without it `review`
  works with Claude only. The Codex model is pinned in the skills as `gpt-6-astra`; change it there if you use
  another one.
- Projects keep `.tmp/` in `.gitignore`: plans, handoff files and reproduction scripts go there.

## Install

```bash
claude plugin marketplace add ilkruglov/duck_factory
claude plugin install duck-factory@duck-factory
```

Skills that should run by themselves are picked far more reliably when your `CLAUDE.md` names them. Add lines
like these:

```markdown
- A non-trivial task (a new feature or module, a choice between approaches, a change in several places, an
  unclear goal): first the `duck-factory:grill` skill, then code.
- Review: the `duck-factory:review` skill, once after a finished code change, before the report and a commit.
```

## Adjusting

The skills are plain Markdown; after an edit bump the version and reinstall, or keep your own fork.

- **Tier thresholds**: the table in `skills/review/SKILL.md`, step 1.
- **Codex model**: `gpt-6-astra` in `skills/review/SKILL.md` and `skills/grill/SKILL.md`.
- **Where plans and handoff files go**: `.tmp/plans/` and `.tmp/handoff/` in the same two skills and in
  `skills/handoff/SKILL.md`.

## Update and remove

```bash
claude plugin marketplace update duck-factory
claude plugin update duck-factory@duck-factory
claude plugin uninstall duck-factory@duck-factory
```

A new version loads in the next Claude Code session.

## Limits

- Tested on Linux with Claude Code and Opus-class models; the tier measurement used one repository and bugs of
  one kind (path and environment selection logic).
- In a headless run (`claude -p`) the question dialog is not available, and `grill` asks in text instead.
- `review` verifies findings by reproducing them, so a light review takes about two minutes, not one.

## Credits

`grill` and `handoff` are based on the `grilling` and `handoff` skills by Matt Pocock
(https://github.com/mattpocock/skills, MIT).

## License

MIT, see [LICENSE](LICENSE).
