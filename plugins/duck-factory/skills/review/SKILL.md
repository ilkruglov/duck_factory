---
name: review
description: Use after finishing a code change, before the report and before a commit - the one code review to run. Picks its own depth from measured size, blast radius and reversibility, runs the built-in /code-review and Codex in parallel plus a check against the plan, verifies each finding, and reports. Also for "review this", "check with Codex", a second opinion on a diff. It only finds - fixes come after the user agrees. Not for changes to docs or comments only; a data or config file that the project's code reads counts as code.
argument-hint: "[enhanced | max] [path to the plan]"
---

# Review

One review for a finished change. It finds problems and proves them; it changes no files. Write everything the
user reads in the user's language, the tier names, marks and section titles below included.

Run it once, when the change is finished: before the report and before a commit, not after every intermediate
edit.

## 1. Measure the change and pick the tier

The change is everything uncommitted: modified, staged and new files. Measure, do not estimate:

```bash
git status --short
git diff HEAD --numstat                 # tracked files: added, deleted, path
git diff HEAD -w --numstat              # the same without lines that only changed their indentation
git ls-files -o --exclude-standard      # new files; count lines of the ones that belong to this change
```

- **Code lines**: added plus deleted, without tests (`tests/`, `test_*`, `*_test.*`, `*.spec.*`), docs (`*.md`,
  `docs/`) and data or config files (`*.json`, `*.yaml`, `*.toml`, `*.csv`, `*.lock`). Take the count
  from the `-w` run, so that wrapping a block in an `if` is two lines and not the whole block. A file that shows
  changes in the plain run and none with `-w` is counted from the plain run: where indentation is syntax (Python,
  YAML) a shifted line changes behaviour, and such a change must not come out as "no code lines".
- **Data the code reads is code.** A data or config file that the project's code, tests or checks load - a table
  the pipeline reads, a fixture, a schema, a prompt - counts line for line, and its bugs are bugs: a wrong value
  there breaks the program like a wrong line of code. `git grep -n <file name>` shows whether anything reads it.
- **Files**: code files changed.
- **Call sites**: for each function, method or class whose behaviour or signature changed, the places that use
  it (LSP find-references; else `git grep -nw <name>`), summed. Count uses in code only, not in tests and not
  the definition itself. New code that nothing calls yet counts as 0.
- **One-way door**: the change does something that cannot simply be reverted - a data migration, deleting
  data or files, a release or publication, an external API or webhook contract, the format of files already on
  disk.
- **Critical paths**: the paths the project names under a `Critical paths` heading in its `CLAUDE.md`, one
  path or glob per line. A change that touches one of them is reviewed at the enhanced tier. No such list:
  nothing is critical, and you do not make one up from how important the code looks.

| Tier | When | Built-in | Codex | Plan check |
|---|---|---|---|---|
| none | no code lines at all | - | - | - |
| light | up to 50 code lines, 1 file, up to 5 call sites, no one-way door | `low` | review | no |
| normal | everything else | `medium` | review | yes |
| enhanced | a one-way door, or a critical path, or over 10 files, or over 20 call sites, or the user asked | `high` | adversarial, with a focus | yes |
| repeat | after fixes from the previous round | as light, aimed (see step 5) | review | no |

A one-way door outweighs every other sign. In doubt between two tiers, take the higher. `max` only when the user
asks for it by name.

The tier comes from this table and from nothing else. A reason the table does not hold - the code "is the core
of the system", the change "feels risky" - does not move the tier. If you think the table is wrong for this
change, say so in one line after the tier line and let the user decide. "In doubt" is doubt about a measurement
(is this a one-way door?), not about importance.

Before starting, say the choice in one line: the numbers, then the row of the table that decided it. The same
line is the first line of the final report, before any heading:
`Review: normal - 132 code lines, 3 files, 7 call sites, reversible. Decided by: over 50 code lines.`

For tier "none" say so in one line and stop.

## 2. Run the checks, in parallel

Start all of them in one message and wait for the completion notices; do not poll.

**Built-in review.** Skill tool, skill `code-review`, args `<level> <absolute path of the repository root>`.
Never with `--fix`.

**Codex.** Find the plugin (the path changes with its version):

```bash
CODEX_ROOT="$(claude plugin list --json | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{const p=JSON.parse(s).find(x=>x.id==="codex@openai-codex"&&x.enabled);if(!p){console.error("codex@openai-codex is not enabled here");process.exit(1)}process.stdout.write(p.installPath)})')"
```

From the repository root, in the background (`run_in_background: true`):

- light, normal, repeat: `node "$CODEX_ROOT/scripts/codex-companion.mjs" review --wait --model gpt-6-astra --scope working-tree`
- enhanced: `node "$CODEX_ROOT/scripts/codex-companion.mjs" adversarial-review --wait --model gpt-6-astra --scope working-tree "<focus>"`
  The focus names what this diff puts at risk, from its content: error handling and silent failures, concurrency
  and ordering, the migration and its rollback, whether the tests would fail without the change.

Always pass `--model gpt-6-astra`. The output ends with a `# Codex Review` block. A working-tree review covers
every uncommitted file, including changes that are not yours: say so when such files are in `git status`.

**Plan check** (normal and enhanced). The plan is the one written in this session by `grill`, or named in the
handoff file, or passed as an argument. No such plan, or several and none named: skip the check and say so.

```bash
node "$CODEX_ROOT/scripts/codex-companion.mjs" task --fresh --model gpt-6-astra "Compare the uncommitted changes in this repository with the plan in <path>. Do not change any files. Report only: (a) what the plan asks for that is missing or partial; (b) behaviour in the diff the plan did not ask for; (c) acceptance criteria that nothing in the diff or the tests checks. Quote the plan line and cite file:line. If the change matches the plan, say so in one line. Answer in <the user's language>."
```

### When Codex is not available

A limit, no login, a model error, `[codex] Turn failed.`, or no result within 5 minutes: do not retry and never
switch the model. Say it in one line with the reason as Codex gave it, and for the rest of this session review
with Claude only:

- the built-in review goes one level up (`low` to `medium`, `medium` to `high`);
- the plan check is done by a subagent with a fresh context and the same brief;
- do not call Codex again in this session unless the user says it is back.

If the Codex plugin is not enabled in this project, that is the same case.

## 3. Verify the findings

Reviewers are wrong in the same confident tone they are right in. Before the report, check every finding that
claims a bug:

- read the code at the cited lines and the code around it;
- where it is cheap, reproduce it: a short script in `.tmp/` of the project, or an existing test with changed
  input. Do not edit project files for this.

Mark each one: **confirmed** (how: the command and its result, or the lines that prove it), **not
confirmed** (why), or **not checked** (why not). Merge duplicates from different reviewers into one finding
and name who found it. Findings about style or simplification need no proof; keep them apart from bugs.

## 4. Report

In this order, and nothing before it but the tier line:

1. **Bugs**: confirmed and unchecked ones, the most damaging first. Each: what breaks and on what input,
   `file:line`, the mark from step 3, who found it.
2. **Plan check**: missing, extra, unchecked criteria - or that it was skipped and why.
3. **Quality notes**: briefly; `/simplify` will take most of them.
4. **Not confirmed**: one line each, so the user can disagree.

Then what was not covered: tests not run, platforms not checked, Codex unavailable.

End with one question, when there is anything to fix or simplify: fix the confirmed bugs and run `/simplify`?
A finding that is a decision rather than a bug (a trade-off, a change of behaviour) goes to the user as its own
question, not into the fix list.

## 5. After the user agrees

In this order:

1. Each confirmed bug: a failing test, the fix, the test run.
2. `/simplify` (Skill tool, skill `simplify`). It edits by itself; look at its `git diff` afterwards.
3. The project's tests.
4. A **repeat** review of the whole change at the light tier, aimed: tell the reviewers which functions and files
   were just fixed and ask them to check those and what depends on them (Codex: `adversarial-review` with that
   list as the focus; built-in: `low`). If the original change was a one-way door, repeat at the normal tier.
   Drop findings the previous round already reported and the user already decided on.

If two rounds in a row find only edge cases in the same place, stop and ask the user: simplify the approach or
accept the limits. Do not fix in circles.

Ask it in plain words, for someone who has not read the diff and does not know the review's terms. First what
keeps going wrong, in one sentence with an example of an input. Then the options, and for each one what they get
and what they lose: which behaviour goes away and what stops breaking if the approach is simplified; which
inputs will keep failing, listed, if it stays as it is. The same goes for every other question this skill asks.

## Rules

- During the review change nothing but files in `.tmp/`.
- The tools you run write into the project too: `uv run` leaves `uv.lock` and `.venv`, a test run leaves caches.
  Before the report compare `git status --short` with the one from step 1, remove what the review itself created
  outside `.tmp/`, and name it in the report. Leave alone everything that was there before.
- Commit and push only on the user's command; a clean review is not that command.
- Do not lower the tier to save time, do not raise it for a reason the table does not hold, and never go to
  `max` on your own.
