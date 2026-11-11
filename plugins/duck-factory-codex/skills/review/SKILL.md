---
name: review
description: Use after finishing a code change, before the report and before a commit - the one code review to run. Picks its own depth from measured size, blast radius and reversibility, runs the review and a check against the plan in sub-agents with a fresh context, verifies each finding, and reports. It is for a change you made in this session, or when the user asks for this skill by name. It only finds - fixes come after the user agrees. Not for changes to docs, configs or comments only, and not when you were started as the reviewer of someone else's diff (a `codex review` run, a request to check changes): then just review.
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
git ls-files -o --exclude-standard      # new files; count lines of the ones that belong to this change
```

- **Code lines**: added plus deleted, without tests (`tests/`, `test_*`, `*_test.*`, `*.spec.*`), docs (`*.md`,
  `docs/`) and data or config files (`*.json`, `*.yaml`, `*.toml`, `*.lock`).
- **Files**: code files changed.
- **Call sites**: for each function, method or class whose behaviour or signature changed, the places that use
  it (`git grep -nw <name>`), summed. Count uses in code only, not in tests and not the definition itself. New
  code that nothing calls yet counts as 0.
- **One-way door**: the change does something that cannot simply be reverted - a data migration, deleting
  data or files, a release or publication, an external API or webhook contract, the format of files already on
  disk.

| Tier | When | Review pass | Plan check |
|---|---|---|---|
| none | no code lines at all | - | - |
| light | up to 50 code lines, 1 file, up to 5 call sites, no one-way door | general | no |
| normal | everything else | general | yes |
| enhanced | a one-way door, or over 10 files, or over 20 call sites, or the user asked | adversarial, instead of general | yes |
| repeat | after fixes from the previous round | general, aimed (see step 5) | no |

A one-way door outweighs every other sign. In doubt between two tiers, take the higher.

Before starting, say the choice in one line, with the numbers. The same line is the first line of the final
report, before any heading:
`Review: normal - 132 code lines, 3 files, 7 call sites, reversible.`

When the review is a step of a larger task, the tier line and the review's results go into that task's report,
as its review section.

For tier "none" say so in one line and stop.

## 2. Run the checks in sub-agents

The author of a change reviews it badly: it reads what it meant to write. Every check runs in a sub-agent that has
not seen this conversation.

Spawn each one with the sub-agent tool (`collaboration.spawn_agent`) and **`fork_turns="none"`**: by default a
sub-agent inherits the whole conversation, and then it is not a fresh reader. Give it a brief that stands alone:
the absolute path of the repository and the brief below, word for word. Start the checks of one tier together and
wait for all of them.

Do not run `codex review` from inside the session: in the session's sandbox it fails to start.

**General pass** (light, normal, repeat):

> Review the uncommitted changes in the repository at `<path>` (modified and new files) for bugs. Do not change any
> files. Report each bug separately: what breaks and on what input, file:line, and how you verified it. Number the
> findings.

**Adversarial pass** (enhanced; it replaces the general pass, it is not added to it):

> Assume the uncommitted changes in the repository at `<path>` (modified and new files) are broken and try to
> prove it. Do not change any files. Attack in these directions: `<directions>`. Reproduce each finding (a script
> or command, without editing project files) rather than only reading. For each finding name the test that should
> have caught it and why it did not. Report each bug separately: what breaks and on what input, file:line, and the
> reproduction. Number the findings.

Take the directions from what this diff puts at risk: error handling and silent failures; stale or missing state;
ordering and precedence; concurrency; the migration and its rollback; places where the docs promise what the code
does not do; whether the tests would still pass if the change were wrong.

On measured diffs the adversarial pass found the same bugs as the general one and took two to two and a half
times longer; what it adds is a reproduction for every finding and the gaps in the tests. That is what a one-way
door needs, and why it is not run on everything.

**Plan check** (normal and enhanced). The plan is the one written in this session by `grill`, or named in the
handoff file, or given by the user. No such plan, or several and none named: skip the check and say so.

> Compare the uncommitted changes in the repository at `<path>` with the plan in `<plan path>`. Do not change any
> files. Report only: (a) what the plan asks for that is missing or partial; (b) behaviour in the diff the plan did
> not ask for; (c) acceptance criteria that nothing in the diff or the tests checks. Quote the plan line and cite
> file:line. If the change matches the plan, say so in one line.

### When sub-agents are not available

No sub-agent tool in this session, or it fails: say so in one line, do the pass yourself by the same brief, and
put in the report that the review was not independent. Do not retry in a loop.

## 3. Verify the findings

Reviewers are wrong in the same confident tone they are right in. Before the report, check every finding that
claims a bug:

- read the code at the cited lines and the code around it;
- where it is cheap, reproduce it: run the sub-agent's reproduction, or a short script of your own - in memory
  or in `.tmp/` of the project. Do not edit project files for this.

Mark each one: **confirmed** (how: the command and its result, or the lines that prove it), **not confirmed**
(why), or **not checked** (why not). Findings about style or simplification need no proof; keep them apart from
bugs.

## 4. Report

In this order, and nothing before it but the tier line:

1. **Bugs**: confirmed and unchecked ones, the most damaging first. Each: what breaks and on what input,
   `file:line`, the mark from step 3.
2. **Plan check**: missing, extra, unchecked criteria - or that it was skipped and why.
3. **Quality notes**: briefly; the simplification step will take most of them.
4. **Not confirmed**: one line each, so the user can disagree.

Then what was not covered: tests not run, platforms not checked, and that every pass was made by the same model,
so a class of bugs it does not see stays unseen.

End with one question, when there is anything to fix or simplify: fix the confirmed bugs and simplify? A finding
that is a decision rather than a bug (a trade-off, a change of behaviour) goes to the user as its own question,
not into the fix list.

## 5. After the user agrees

In this order:

1. Each confirmed bug: a failing test, the fix, the test run.
2. Simplify what this change touched: remove duplication, abstractions that have one user, dead code and
   leftovers of the fixes. Do not change behaviour and do not widen the diff to code the change did not touch.
3. The project's tests.
4. A **repeat** review of the whole change: one general pass whose brief also lists the functions and files just
   fixed and asks to check those and what depends on them. If the original change was a one-way door, repeat at
   the normal tier instead. Drop findings the previous round already reported and the user already decided on.

If two rounds in a row find only edge cases in the same place, stop and ask the user: simplify the approach or
accept the limits. Do not fix in circles.

## Rules

- During the review change nothing but files in `.tmp/`.
- Commit and push only on the user's command; a clean review is not that command.
- Do not lower the tier to save time.
