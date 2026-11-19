---
name: review
description: Use after finishing a code change, before the report and before a commit - the one code review to run. Picks its own depth from measured size, blast radius and reversibility, runs the built-in /code-review and Codex in parallel (on a large change, Codex and a fresh Claude subagent per group of files) plus a check against the plan, verifies each finding, and reports. Also before a pull request, a merge or a release, as a final review of everything since the work started, and for "review this", "check with Codex", a second opinion on a diff. It only finds - fixes come after the user agrees. Not for changes to docs or comments only; a data or config file that the project's code reads counts as code.
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
  disk. It is about what applying this change does to what already exists, not about what a new feature lets users
  do later: adding a delete command is reversible code.
- **Critical paths**: the paths the project names under a `Critical paths` heading in its `CLAUDE.md`, one
  path or glob per line. A change that touches one of them is reviewed at the enhanced tier. No such list:
  nothing is critical, and you do not make one up from how important the code looks.

**Final review.** Before a pull request, a merge - a branch or a worktree merged back included - or a release, and
when the user asks to review all of the work, the change is everything since the commit the work started from,
committed or not. Run it in the worktree of the branch being merged, not in the receiving branch. The base is the
commit named in the plan or the handoff file; else `git merge-base HEAD <the branch the work will be merged into>`
- for a local merge, that local branch; for a pull request, its target as `origin/<target>` after `git
fetch` - and never the branch's own upstream, which after a push is the last pushed commit. If
the base comes out as `HEAD` while the work has commits, ask the user for it. Write the base as the commit hash,
not the word `HEAD`, so that a commit between rounds does not move it. Measure the change with `git diff <base>`
in place of `git diff HEAD`. Reviews of single steps do not replace it: a bug where two paths written in different
steps meet shows only when both are in view.

| Tier | When | Built-in | Codex | Plan check |
|---|---|---|---|---|
| none | no code lines at all | - | - | - |
| light | up to 50 code lines, 1 file, up to 5 call sites, no one-way door | `low` | review | no |
| normal | everything else | `medium` | review | yes |
| enhanced | a one-way door, or a critical path, or over 10 files, or over 20 call sites, or the user asked | `high` | adversarial, with a focus | yes |
| final | a final review (step 1): the tier the table gives for the whole change, at least normal | - (step 2) | per group (step 2) | yes |
| repeat | after fixes from the previous round | as light, aimed (see step 5) | adversarial, aimed | no |

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

### Groups

At the normal and enhanced tiers, and in a final review, split the change into groups and give each group its own
reviewers. Every changed file goes to a group: the code files by subsystem - the same directory or module together
- and each test with the code it tests, or with the nearest group. How many groups, counted by code lines and code
files:

| Change | Groups |
|---|---|
| under 100 code lines, or 1-2 files | 1 |
| under 500 code lines | 2 |
| larger | one per three files, rounded up, from 2 to 4 |

With more than one group, the line after the tier line names them: `Groups: audio (player.rs, asio.rs), ui (gui.rs)`.

## 2. Run the checks, in parallel

Start all of them in one message and wait for the completion notices; do not poll.

**With one group** (light, and normal or enhanced that fit in one group) run the built-in review and Codex as below;
**with several groups, or in a final review**, the reviewers in "Reviewers per group".

**Built-in review.** Skill tool, skill `code-review`, args `<level> <absolute path of the repository root>`.
Never with `--fix`.

**Codex.** Find the plugin (the path changes with its version):

```bash
claude plugin list --json | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{const p=JSON.parse(s).find(x=>x.id==="codex@openai-codex"&&x.enabled);if(!p){console.error("codex@openai-codex is not enabled here");process.exit(1)}process.stdout.write(p.installPath)})'
```

It prints the plugin's path. Shell variables do not survive between Bash calls: put that path in place of
`<CODEX_ROOT>` into every command below. Every Codex command runs under `timeout 900` (15 minutes; `gtimeout` from
coreutils on macOS). When it ends by the timeout, the Codex job may still run behind the helper: find it with
`codex-companion.mjs status` and stop it with `codex-companion.mjs cancel <job-id>`, then report that reviewer as
not finished.

From the repository root, in the background (`run_in_background: true`):

- light, normal: `timeout 900 node "<CODEX_ROOT>/scripts/codex-companion.mjs" review --wait --scope working-tree`
- enhanced, repeat: `timeout 900 node "<CODEX_ROOT>/scripts/codex-companion.mjs" adversarial-review --wait --scope working-tree '<focus>'`
  The focus names what this diff puts at risk, from its content: error handling and silent failures, concurrency
  and ordering, the migration and its rollback, whether the tests would fail without the change, the contracts of
  external APIs and libraries the code relies on. For a repeat, the focus is the list of places just fixed (step 5).
  The focus goes in single quotes, with no single quote, backtick or `$` inside it.

Codex runs the model and reasoning effort from its own configuration (`~/.codex/config.toml`, a trusted project's
`.codex/config.toml`, and `review_model` for its native review); do not pass a model. The
output ends with a `# Codex Review` or `# Codex Adversarial Review` block. A working-tree review covers
every uncommitted file, including changes that are not yours: say so when such files are in `git status`.

**Reviewers per group.** For each group start two reviewers, both with the group brief below, all of them in one
message. Codex: write the brief to `.tmp/review/<group>.md` - never put it into the command line: it has
backticks, and the shell would run them - and run in the background (several such tasks run in parallel):

```bash
timeout 900 node "<CODEX_ROOT>/scripts/codex-companion.mjs" task --fresh --prompt-file .tmp/review/<group>.md
```

Claude: a Claude subagent with a fresh context (Agent tool, `general-purpose`) with the same brief. The built-in
review does not run then: it takes the whole uncommitted diff, not a group and not the commits since a base. If
the user asked for `max`, also run the built-in review at `max` on the whole change; it takes the commits since
the upstream, not since the base, so say in the report when the two differ. `<base>` is the commit hash of `HEAD`
for an ordinary review and the base from step 1 for a final review.

> Review the changes in the repository at `<path>` since `<base>` (`git diff <base>` shows them, uncommitted files
> included; new files: `git ls-files -o --exclude-standard`). Your part is these files: `<files>`; read any other
> file you need. Do not change any files. Do the review yourself: do not start a review skill or other reviewers.
> Read each of your files in full, not only the changed lines. For every new or changed type, value, message or
> command that crosses a function or module boundary, find the code that consumes it - often outside the change -
> and check that it handles it rather than dropping it. Check the code against the contracts of the external APIs,
> operating-system calls and libraries it relies on, from their documentation or source. `<At the enhanced tier:
> This change is reviewed at the enhanced tier because <the reason from the tier line>: try to prove it is broken
> in these directions - <focus> - and reproduce each finding with a script or command, without editing project
> files. For each finding name the test that should have caught it.>` Report each bug separately: what breaks and
> on what input, file:line, and how you verified it. Number the findings. Answer in <the user's language>.

**Plan check** (normal and enhanced). The plan is the one written in this session by `grill`, or named in the
handoff file, or passed as an argument. No such plan, or several and none named: skip the check and say so.

Write this brief to `.tmp/review/plan-check.md` and run in the background:

```bash
timeout 900 node "<CODEX_ROOT>/scripts/codex-companion.mjs" task --fresh --prompt-file .tmp/review/plan-check.md
```

> Compare the uncommitted changes (in a final review: the changes since `<base>`) in the repository at `<path>` with
> the plan in `<plan path>`. Do not change any files. Report only: (a) what the plan asks for that is missing or
> partial; (b) behaviour in the diff the plan did not ask for; (c) acceptance criteria that nothing in the diff or
> the tests checks. Quote the plan line and cite file:line. If the change matches the plan, say so in one line.
> Answer in <the user's language>.

### When Codex is not available

A limit, no login, a model error or `[codex] Turn failed.`: do not retry and never switch the model. Say it in one line with the reason as Codex gave it, and for the rest of this session review
with Claude only:

- the built-in review goes one level up (`low` to `medium`, `medium` to `high`);
- with groups, only the Claude subagents review them;
- the plan check is done by a subagent with a fresh context and the same brief;
- do not call Codex again in this session unless the user says it is back.

If the Codex plugin is not enabled in this project, that is the same case. A Codex reviewer that has given nothing
in 15 minutes is stopped and reported as not finished; that alone does not make Codex unavailable.

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

In this order, and nothing before it but the tier line and, with several groups, the `Groups:` line:

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
   were just fixed and ask them to check those, what depends on them and the contracts they rely on (Codex:
   `adversarial-review` with that list as the focus; built-in: `low`, or `medium` if the original change was a
   one-way door). If the round being repeated ran in groups or was a final review, repeat with the same reviewers
   per group and the same base, the list of fixed places added to the brief; new files the fixes added join the
   group of the code they belong to. If commits were made since that round, repeat it as a final review from the
   base of that round. Drop findings the previous round already reported and the user already
   decided on - except one the fix was meant to remove: if it is still there, it is a bug again.

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
