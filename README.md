# duck_factory

A plugin for Claude Code and for Codex CLI (`duck-factory`). The sections below describe the Claude Code
version; [Codex](#codex) lists what differs. In Russian: [README.ru.md](README.ru.md). Changes by version:
[CHANGELOG.md](CHANGELOG.md). The measurements behind its choices: [BENCH.md](BENCH.md).

Three skills that make a small development pipeline for Claude Code: agree on the task before starting, review
the result once with a depth that fits the change, and hand the work over to a fresh session. Two
[hooks](#hooks) keep the plan and the state of the work through a context compaction.

| Skill | When it runs | What it does |
|---|---|---|
| `grill` | by itself, before a non-trivial task, with or without code; or `/duck-factory:grill` | When you approved a list wholesale or the task was the agent's idea, asks first which of it to do at all; then interviews you in short rounds through the question dialog, recommended option first, and writes to `.tmp/plans/` a one-page plan when the work changes code, else a short record of the decisions, steps and acceptance criteria. A large plan that changes code is checked by Codex before any code. |
| `review` | by itself, after a finished code change; or `/duck-factory:review` | Measures the change (code lines, files, call sites, reversibility), picks a tier, runs in parallel the built-in `/code-review`, Codex with the skill's brief and, from the normal tier, Codex's adversarial review (in a final review, a Codex and a Claude reviewer per group of files) plus a check against the plan, verifies every finding, and reports. Also as a final review of all the work before a pull request, a merge or a release; a security pass when you say yes. It only finds; fixes come after you agree. |
| `handoff` | only on `/duck-factory:handoff` | Writes `.tmp/handoff/<slug>.md` so a fresh session can continue: goal, constraints, decisions, what is done and how it was checked, what is in flight, the next step, rollback. The file starts by telling the next session to check it against reality. |

## Quick start

In Claude Code:

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

In Codex CLI:

```bash
codex plugin marketplace add ilkruglov/duck_factory
codex plugin add duck-factory@duck-factory
```

Then open `/hooks` in Codex and trust the plugin's hook: Codex does not run it before that, and asks again when an
update changes the script.

`grill` asks through a dialog that waits for the answers only in Plan mode (Shift+Tab switches to it): outside it,
in Codex 0.172, the questions come in text or in a dialog that does not wait.

Lines for your `AGENTS.md`, so the skills run by themselves:

```markdown
- A non-trivial task (a new feature or module, a choice between approaches, a change in several places, an
  unclear goal): first the `grill` skill, then code.
- After your own finished code change, before the report and a commit: the `review` skill, once. When you were
  started as the reviewer of someone else's diff, the skill is not needed: just review.
```

The second sentence matters when another tool calls Codex as a reviewer: without it a plain review request could
start the whole skill.

What else the plugin needs is under [Requirements](#requirements).

## The pipeline

1. `grill` loads the skills for the area, settles the decisions and writes the plan with acceptance criteria: a full
   one for code, a short record otherwise.
2. You approve the plan or the record; the work goes test first.
3. `review` runs once, before the report or a commit.
4. After you agree: a failing test and a fix for each confirmed bug, the tests, and a short repeat review of the
   fixes only; simplification once, at the end, by Codex and the agent.
5. `handoff` when the work continues in another session.

Nothing here replaces your approval: `grill` changes nothing until you confirm, a full plan is not consent to start
the work, and `review` never edits files.

## grill

Runs before a task that is not trivial: a new feature or module, a choice between approaches, a change in several
places, work without code that takes more than a few steps (research, a document, a setup), an unclear goal. For a
bug fix or a small clear edit it says the task is clear and steps aside. Either way, in a git repository it first
looks at `git status`: if accepted work of another task is not committed yet, it asks whether to commit it, so that
the ordinary review of the new task reads only the new change (in a plan mode the commit waits until the mode ends).

How a session goes:

0. **What to do, before how.** When you approved a set of tasks wholesale ("do everything" about a backlog, a
   list of suggestions, someone else's plan), or the task was the agent's own idea, the first round asks only
   which of it to do at all, with the size of each task. Design questions come after you have said to do a task.
   Tasks you named yourself in the request are not asked about.
1. **Skills for the area.** If the task touches something another installed skill covers (a framework, a kind
   of system, the project's design rules), that skill is loaded first: it changes which questions are worth
   asking.
2. **Facts first.** Anything that can be looked up in the code, configs or logs is looked up, not asked. A
   decision already made - in the decisions of an earlier accepted plan, or in the project's rules - is taken from
   there, with its source, not asked again; when two plans disagree, you are asked.
3. **Questions in rounds**, through the question dialog: at most four per round, the most consequential first,
   two to four options each, the recommended one first. Every question carries the fact it hinges on. From the
   second round on, the last question lets you stop: "enough, take your recommendations for the rest".
4. **Confirmation** with the decisions and the defaults taken without asking; for work without code it shows the
   short record itself, and your yes starts the work.
5. **The plan** in `.tmp/plans/<slug>.md`. When the work changes program code - a hook, a service, a script in the repository,
   CI, a config, prompt or data file the code reads - a full plan of one page:

```markdown
# Export notes

Status: active

Source: "add export of the notes to CSV and JSON, the format chosen on the command line"

Goal: `notes export --format csv|json` prints all notes to stdout.

Skills used: none

Decisions:
- CSV through the standard csv module, fields id,title,text - no new dependency.
- An empty store exports an empty set, not an error - same as `list`.

Taken by default, not asked:
- `--format` is required - no obvious default between the two.

Not touching: the storage format, the add and list commands.

Acceptance criteria (each checked by a test, by a command, or by the user looking at a named result):
- `notes export --format csv` prints a header and one row per note - tests/test_cli.py::test_export_csv
- An unknown format exits with an argparse error - tests/test_cli.py::test_export_bad_format

Risks and open questions: none
```

For a skill, a prompt the project's code does not read, a document, slides, research or a setup - also with tests or checks next
to them - the agent writes a short record instead, the plan it works by: the decisions (a default marked as such),
the steps and the acceptance criteria, each with its check. It comes back after a compaction like a full plan, and
the report at the end goes through its criteria.

```markdown
# Review composition from the bench

Status: active

Source: "let's do as you propose"

Decisions:
- Codex always gets the brief, one for the whole change.
- The adversarial review from the normal tier; the agent writes the focus (by default).

Steps:
1. The tier table and step 2 of the review skill.
2. Both READMEs and changelogs.

Acceptance criteria:
- The tests pass - `uv run pytest -q`.
- You accept the list of behaviour changes - you look at it.
```

`Status` is `active` until you accept the result (`done`) or cancel the work (`dropped`); the line stays in
English whatever the language of the plan, because the [hooks](#hooks) read it. `Source` quotes your words that
ask for the task. A criterion only a person can judge - how a text reads, whether a setup is convenient - is
checked by showing you a named result.

For a large task that changes code (a new module, an approach that is costly to reverse, more than a session of
work) the plan is then checked by Codex against the repository, read-only. Its findings that are decisions come
back to you as questions. A plan with no code in it is not sent to Codex.

While working by the plan, the skill does not change a decision silently, redoes without asking what plainly
does not do what the agreed plan says, and ends the report by going through the acceptance criteria one by one.

## review

Runs once after a finished code change. It answers three questions: is there a bug, does the change match the
plan, and can each finding be proved.

### How the tier is picked

The skill measures everything uncommitted (modified, staged and new files) and prints the result in one line:

`Review: normal - 132 code lines, 3 files, 7 call sites, reversible. Decided by: over 50 code lines.`

- **Code lines**: added plus deleted, without tests, docs and data or config files. Lines that only changed
  their indentation are not counted (`git diff -w`): wrapping a block in an `if` is two lines, not the block.
  A file whose whole change is indentation is counted in full: in Python or YAML a shifted line changes behaviour.
- **Assets are not code**, even when the program loads them: images (SVG too), fonts, audio and video, archives,
  PDF. Any other binary file - a `.wasm`, a script saved in UTF-16 - counts as a code file.
- **Text data the code reads is code**: a table, fixture, schema or prompt that the project's code, tests or checks
  load counts line for line. A wrong value there breaks the program like a wrong line of code.
- **Files**: code files changed.
- **Call sites**: places in code (not tests) that use a function, method or class whose behaviour or signature
  changed.
- **One-way door**: something that cannot simply be reverted - a data migration, deleting data or files, a
  release, an external API contract, the format of files already on disk. It is about what applying the change does
  to what already exists, not what a new feature lets users do later: adding a delete command is reversible code.
- **Security paths**: the paths you list under a `Security paths` heading in the project's `CLAUDE.md` (or
  `AGENTS.md` when it has no `CLAUDE.md`) - sign-in, permissions, payments, input from outside. They do not change
  the tier; the review offers a security pass for them (see "Security" below). Without the list there are none.
- **Critical paths**: the paths you list under a `Critical paths` heading in the project's `CLAUDE.md` (or
  `AGENTS.md` when it has no `CLAUDE.md`), one path or glob per line. A change that touches one goes to the enhanced
  tier. Without the list nothing is critical.

| Tier | When | Built-in review | Codex | Plan check |
|---|---|---|---|---|
| none | no code file changed | - | - | - |
| light | up to 50 code lines, 1 file, up to 5 call sites, reversible | `low` | the brief | no |
| normal | everything else | `medium`; `high` with more than one group | the brief and adversarial, with a focus | yes |
| enhanced | a one-way door, a critical path, over 10 files, over 20 call sites, or you asked | `high` | the brief and adversarial, with a focus | yes |
| final | a final review (below): the tier of the whole change, at least normal | - | per group, and adversarial since the base | yes |
| repeat | after fixes | - | a short brief on the fixes only, Codex and a Claude subagent at `medium` (below) | no |

A one-way door outweighs the other signs; `max` only when you ask for it by name. The tier comes from the table
and nothing else: "this is the core of the system" does not raise it - that is what the list of critical paths
is for. When a measurement is in doubt (is this a one-way door?), the higher tier wins.

The tiers follow a measurement on seeded bugs - `medium` and Codex found them all, `high` the same in twice the
time, `low` lost one in a large change - and the call-site thresholds are a cautious guess
([Review tiers](BENCH.md#review-tiers)).

The reviewers follow a bench on two real changes: Codex with the brief, its adversarial review and the built-in
`high` found the most important bugs, while Claude subagents per group found more minor ones for many times the
tokens and so stay for the final review only ([Reviewers](BENCH.md#reviewers)).

### What the checks are

- **Built-in review**: Claude Code's `/code-review` at the tier's level. It also checks the diff against your
  `CLAUDE.md`.
- **Codex**: a second opinion from another model, through the `codex@openai-codex` plugin, as a task with the brief
  below for the whole change. From the normal tier its adversarial review runs alongside, with a focus taken from
  the diff: silent failures, ordering and concurrency, the migration and its rollback, whether the tests would fail
  without the change.
- **Plan check**: what the plan asked for and is missing, what was done beyond the plan, which acceptance
  criteria nothing checks. It uses the plan `grill` wrote in this session, or one named in the handoff file or
  passed as an argument; with no plan it is skipped, and the report says so.

All of them run in parallel. Claude subagents start without a `model`, so they run on the session's model; a
default model for subagents set in Claude Code's settings would replace it.

### Final review and groups

Reviews of single steps miss what only shows when the whole work is in view, most often two code paths, written in
different steps, that disagree ([Final review](BENCH.md#final-review)).

- **Final review.** Before a pull request, a merge (a branch or a worktree merged back included) or a release, and
  when you ask to review all of the work, the change is everything since the commit the work started from,
  committed or not: the base named in the plan or the handoff file, else the merge-base with the branch the work
  will be merged into (never the branch's own upstream: after a push that is the last pushed commit). It is a row of
  the tier table, at least normal, and always runs in groups.
- **Groups.** At the normal and enhanced tiers every changed file goes to a group: code by subsystem, each test with
  the code it tests. One group under 100 code lines or for 1-2 files, two under 500 lines, then one per three files
  rounded up, from two to four. Outside a final review the groups only set the level of the built-in review
  (`high` with more than one group) and the pairs of a repeat round; Codex gets the brief for the whole change. In a
  final review each group gets Codex (a `task` with the brief below) and a fresh Claude subagent with the same brief,
  all in parallel, plus Codex's adversarial review with `--base`, which sees the commits only; the built-in
  `/code-review` does not run then: it takes the whole uncommitted diff, not a group and not the commits since a base
  (with `max` it still runs, on the whole change). Briefs go to Codex as files (`--prompt-file`), never on the command
  line, where the shell would run their backticks. Each review keeps its briefs in a folder of its own, so that two
  reviews in one worktree do not overwrite each other's.
- **The brief** asks each reviewer to read the project's rules (the instruction files Claude Code or Codex would load
  for its files: `CLAUDE.md`, `AGENTS.md`, `.claude/rules/` and the like) and report a change that breaks them; to
  read its files in full, not only the changed lines; to follow every new type, value, message or command across a
  function or module boundary to the code that consumes it, often outside the change; and to check the code against
  the contracts of the external APIs, operating-system calls and libraries it relies on. The last three come from the
  reviewer of [oh-my-pi](https://github.com/can1357/oh-my-pi).

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
Review: light - 9 code lines, 1 file, 1 call site, reversible. Decided by: up to 50 code lines, 1 file.

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

Fix the confirmed bug and simplify?
```

A finding that is a decision rather than a bug goes to you as its own question, not into the fix list.

The review changes nothing but files in `.tmp/`. The tools it runs can still leave files behind (`uv run`
writes `uv.lock`), so before the report it compares `git status` with the one it started from, removes what it
created itself and says so.

### Security

The reviewers above look for where the code does not do what was meant, not for how it can be made to do what was
not meant. A separate security pass looks for that, and it runs only after you say yes. The review offers it in a
final review and when the change touches a security path (see above), even when the change there has no code lines;
you can also ask for it at any review, and then it runs without a question. It is offered once per piece of work, not
again in a repeat round. In Claude Code the question comes right after the other checks start, so the pass runs
alongside them. Without the question dialog (a headless run, and always in Codex) it comes at the end of the report,
numbered apart from the question about fixes, and the pass starts only after your answer; with a yes to both, it runs
first.

The pass is one more reviewer - a Codex task, or a fresh Claude subagent without Codex - with its own brief. It
reads the project's rules and its `SECURITY.md` files, if any (the nearest to the changed file wins), and follows
them where they describe the threat model or what counts as a finding. It says who
can reach the changed code and what input crosses a trust boundary; then checks injection, broken authentication
or authorization, data of one user reaching another, secrets in code or logs, unsafe deserialization, XSS, SSRF,
new or unpinned dependencies. Only reachable findings, each with the path from the input to the harm and a level:
critical, high, medium or low. They go into the bugs of the report, marked as security.

The security plugins of OpenAI and Anthropic are not part of the review ([why](BENCH.md#security-plugins)).

### After you agree

Each round goes like this. For each confirmed bug: a failing test that fails on the bug itself (not on an import
error or a typo), the fix and the tests of that place; a yes covers the places the report named for the finding - the
report names where the same logic repeats, such as the other version of a mirrored file - and the same bug found
anywhere else goes to you first; then the project's full test suite once; then a repeat review of the fixes only. The
agent keeps the list of fixed places, and the repeat has its own short brief: those places, the code that calls them,
the code they call and their tests - not the whole change again. In Claude Code it is one Codex task and one Claude
subagent at effort `medium` for all the fixes (without Codex, the subagent alone); when the fixes are in several groups, that pair goes
to every group where something was fixed. In Codex it is one sub-agent the same way.

When a round leaves nothing to fix, or you accept what is left, the work ends once with a simplification: Codex
lists simplifications without changing anything while the agent goes through the diff itself - reuse, duplication
and dead code, repeated work, special cases where a general rule should change, and in the text of skills and docs
rules repeated or contradicting each other (also between the two versions and the README), rules longer than an
agent needs and needless calls. The agent drops from Codex's list what is only taste and what changes behaviour or
touches code outside the change, and applies the rest with its own; then the tests and one repeat review of what the
simplification changed, checking that the behaviour stayed the same. In Codex the list comes from a fresh sub-agent.
This pair and not `/simplify`: on a bench the pair found more real simplifications, Codex without Claude tokens,
while `/simplify` took more Claude tokens than the agent and once changed behaviour
([Simplification](BENCH.md#simplification)).

Findings the previous round already reported and you already decided on are dropped, except one a fix was meant to
remove and that is still there. If two rounds in a row find only edge cases in the same place, the skill stops and
asks you whether to simplify the approach or accept the limits. After the third repeat round it stops and asks in any
case: go on, simplify the approach or accept what is left, with how many real bugs each round brought. It asks in
plain words: what keeps going wrong, with an example, and for each option what you get and what you lose.

A yes covers only the findings you have seen: findings that come later, such as those of the security pass, are fixed
after you have seen them and said yes.

### Without Codex

A limit, no login or a model error: the skill does not retry and does not switch the model. (A Codex reviewer
that has given nothing in its time limit - 15 minutes, 30 for the brief on the whole change - is only stopped and reported as not finished.) It says so in one line, raises the built-in review one level (`low` to `medium`, `medium` to `high`; `high` stays),
outside a final review adds one Claude subagent with the brief for the whole change when it has more than one group, gives the plan check
to a subagent with a fresh context, and does not call Codex again in that session unless
you say it is back.

### Time and cost

A review takes minutes, most of them spent reproducing the findings, and a review in groups takes longer
([Time and cost](BENCH.md#time-and-cost)).

## handoff

Runs only when you type `/duck-factory:handoff`, optionally with what the next session is for. It writes
`.tmp/handoff/<slug>.md`, or updates the file this work already has:

```markdown
# Empty-file crash in load - handoff, 2026-11-11

Status: active

When the work this file hands over is finished, change the Status line to `done`; when it is dropped, to
`dropped`.

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

`Traps` and `Waiting on the user` hold up to five items each, the costliest trap and the most blocking question
first. When the file you name for it to update does not exist, the skill stops and asks whether the path is right,
naming the active handoff files.

The paragraph that checks the file against reality matters most: the file goes stale as soon as anything changes between sessions, and it can
be wrong itself. In a test where the fix was reverted behind its back, the next session opened with "the
handoff differs from the repository" and asked before doing anything.

The `Status` line works as in a plan: `active` until the work the file hands over is finished (`done`) or dropped
(`dropped`); the sentence under it tells the session that finishes the work to change it. The [hooks](#hooks) name
an active handoff file with its date when a session starts, and the agent reads it only when you ask to continue
that work - "let's continue" is enough; after a compaction they name it again, so that a session working from it
reads its traps and decisions again. A file without a `Status` line, written by an earlier version, is not named.
The decisions of a handoff file marked `done` count for `grill` as earlier decisions, like those of an accepted
plan.

## Hooks

Both plugins carry the same small script (`scripts/context_hooks.py`, Python standard library only, reads files
and writes none). The Claude Code plugin runs it on two events:

| Event | What the script prints | Where it goes |
|---|---|---|
| `PreCompact` | a request to keep five things under their own headings (below), and the paths of the active plans and handoff files; a plan not changed for more than three days is named apart, without the promise that it comes back in full | into the instructions for the compaction summary |
| `SessionStart` after a compaction | the newest three plans in `.tmp/plans/` with `Status: active`: those changed in the last three days in full, as long as the whole output fits both hosts' limits (9500 UTF-16 units for Claude Code, 19,000 bytes of UTF-8 for Codex) - while it does not, the largest gives way to its path with a request to read it; an older one - by the calendar, "4 days ago" or older: likely left - by path, with its date and a request to read it if the session works from it; the newest three active handoff files in `.tmp/handoff/` by path, with a request to read its traps and decisions again if the session works from it | into the context of the session |
| `SessionStart` of a new or resumed session | one line per active plan and per active handoff file, the newest three of each: its path and when it was last changed, and that the agent reads it only when you ask to continue that work | into the context of the session |

The Codex plugin runs it on `SessionStart` only, with the same output: Codex ignores what a `PreCompact` hook prints
(see [Codex](#codex)).

What the summary is asked to keep, and why: what the agent of one real project went back to the session transcript
for after its compactions ([Hooks](BENCH.md#hooks)), plus what a summary blurs:

- **Exact commands** that produced results still in use or started what is still running. The usual summary
  says what was done, not how: the most frequent thing looked up.
- **Long materials**: texts you pasted, reports of sub-agents, long tool outputs - where each one is.
- **Done, not checked**, and how far a long pass has got: after a compaction "did" and "verified" merge.
- **Waiting on the user**: what you have and have not agreed to. "Next: do X" reads as a permission.
- **Standing corrections**: what you said about how to work, as rules, with the number of repeats.

Not asked for, on purpose: the state of the disk (git can be asked again, and nothing has changed in the seconds
since the summary), the text of the plan (it comes back in full, an older one by its path), project rules (reloaded
by Claude Code).

- The plans are looked for in every `.tmp/plans/` from the session directory up to the repository root.
- Only the first line of text under the title counts as the `Status:` line, written plainly or in bold; a quote,
  a heading, a list item or a line further down is not the file's own status.
- With your own instructions in `/compact <instructions>` the `PreCompact` hook prints nothing.
- A plan left `active` comes back after every compaction and is named at every start: it is closed when you
  accept the result.

- A resumed session gets only the line, not the plan: its history is intact, and printing the plan on every
  resume would add a copy each time. The hook's output goes to the end of the conversation, so the prompt cache
  is not broken: a resume read as much from the cache with it as without it ([Hooks](BENCH.md#hooks)).
- If the project has compaction hooks of its own, these run next to them, not instead.
- Checked in a live session: after `/compact` the summary had the extra headings after the standard ones, and
  the model named the plan's path and a marker word from it without reading any file. In a live Codex session
  the model named the active plan and handoff file with their dates, and what it was told to do with each, without
  running a command or reading a file.
- Not measured: whether the extra headings make the work after a compaction better. A repeated correction is
  not cured by keeping its text: one the summary kept had to be said again anyway ([Hooks](BENCH.md#hooks)).

## Codex

The same pipeline for Codex CLI lives in `plugins/duck-factory-codex` and works entirely inside Codex. To install
it, see [Quick start](#quick-start).

What differs from the Claude Code version:

| | Claude Code | Codex |
|---|---|---|
| Who reviews | the built-in `/code-review` and Codex, two models | sub-agents of the same model, started with a fresh context (`fork_turns="none"`) |
| light | `low` + Codex with the brief | one general pass |
| normal | `medium` + Codex with the brief + adversarial Codex + plan check | one general pass + plan check |
| enhanced | `high` + Codex with the brief + adversarial Codex + plan check | one adversarial pass instead of the general one + plan check |
| Large change | `high` + Codex with the brief + adversarial Codex, each on the whole change | one sub-agent per group of files |
| Final review | Codex and a fresh Claude subagent per group of files, same brief, + adversarial Codex | one sub-agent per group of files |
| Simplification at the end | Codex lists, the agent filters the list and adds its own | a fresh sub-agent lists, the agent filters the list and adds its own |
| Questions in `grill` | the question dialog, up to 4 per round | by mode: in Plan mode `request_user_input` (up to 3 questions, 2-3 options); outside it, where Codex 0.172 has no dialog that waits, `request_user_input_async` or `send_message_to_user_async` and always written out in the final message (up to 4), else text; `grill` says once that Shift+Tab switches to Plan mode |
| The boundary of the work in the plan | a `Not touching` section | a `Scope` section: what the work covers (the Codex model does not write what stays unchanged) |
| Domain skills in `grill` | loaded with the Skill tool | their `SKILL.md` is read |
| Plan check in `grill` | Codex, read-only | a sub-agent with a fresh context |
| The security pass, after your yes | a Codex task (without Codex, a subagent), asked about with AskUserQuestion while the other checks run; in a headless run, at the end of the report | a sub-agent, asked about at the end of the report |
| `handoff` is manual through | `disable-model-invocation` | `agents/openai.yaml`, `allow_implicit_invocation: false` |
| `Critical paths` and `Security paths` are listed in | the project's `CLAUDE.md` | the project's `AGENTS.md` |
| Hooks | `PreCompact` asks the summary to keep five things; `SessionStart` names plans and handoff files and brings the plan back after a compaction | `SessionStart` only, once you trust it in `/hooks`: Codex ignores what `PreCompact` prints; `additionalContextLimit` 5000, as Codex counts a token as 4 bytes of UTF-8 and the default 2500 is too few for a plan in full |

The enhanced tier gets one adversarial pass instead of the general one, not both: on a bench a second pass by the
same model found no bug the first had missed, and the adversarial one adds what a change that cannot be reverted
needs - a reproduction for each finding and the gaps in the tests ([Codex](BENCH.md#codex)).

The honest limit: there is no second model here, and on a bench both Codex briefs missed real problems that the
other model found ([Codex](BENCH.md#codex)). If you have both tools, the Claude Code version gives the stronger
review.

On the bench a review here took no longer than in Claude Code and found every seeded bug without changing the tree
([Time and cost](BENCH.md#time-and-cost)).

To update, install it again: `codex plugin remove duck-factory@duck-factory`, then `codex plugin add
duck-factory@duck-factory`.

## Requirements

- Claude Code with the built-in `/code-review`.
- For the second opinion and the plan check: the `codex@openai-codex` plugin, logged in. Without it `review`
  works with Claude only. Codex runs the model and reasoning effort from its own configuration:
  `~/.codex/config.toml` and a trusted project's `.codex/config.toml`.
- `python3` 3.12 or later on PATH: it runs the hooks.
- `timeout` from coreutils (`gtimeout` on macOS): every Codex call runs under it.
- On native Windows, Git for Windows: Claude Code then runs its commands in Git Bash, which has GNU `timeout`;
  without it Claude Code uses PowerShell, where the Codex commands of `review` do not run
  ([setup](https://code.claude.com/docs/en/setup)). The hooks need `python3` on PATH there too. In WSL everything
  works as on Linux. Not checked on Windows.
- Projects keep `.tmp/` in `.gitignore`: plans, handoff files and reproduction scripts go there.

## Adjusting

The skills are plain Markdown; after an edit bump the version and reinstall, or keep your own fork.

- **Tier thresholds**: the table in `skills/review/SKILL.md`, step 1.
- **Codex model**: `model` and `model_reasoning_effort` in `~/.codex/config.toml`; the skills pass none.
- **Where plans and handoff files go**: `.tmp/plans/` and `.tmp/handoff/` in the same two skills, in
  `skills/handoff/SKILL.md` and in `scripts/context_hooks.py`.
- **Critical paths** of a project: a `Critical paths` heading in its `CLAUDE.md` (`AGENTS.md` for Codex).
- **Security paths** of a project: a `Security paths` heading in the same file; what counts as a security
  finding there: its `SECURITY.md`.

## Development

The tests check the skills, the hooks and the texts of this repository; run them from its root:

```bash
uv run pytest -q
```

`pyproject.toml` pins pytest and ruff, and `uv.lock` locks them. GitHub Actions
(`.github/workflows/tests.yml`) run `uv run --locked pytest -q`, `ruff check` and `ruff format --check` on Python
3.12 and 3.14 on every push to main and every pull request.

`evals/bench.py` runs the skills on a small synthetic project in either harness; how to run it and how it judges a
run: [Evals](BENCH.md#evals).

## Update and remove

```bash
claude plugin marketplace update duck-factory
claude plugin update duck-factory@duck-factory
claude plugin uninstall duck-factory@duck-factory
```

A new version loads in the next Claude Code session.

## Limits

- Tested on Linux with Claude Code and Opus-class models; what the measurements cover and what not:
  [BENCH.md](BENCH.md#limits).
- The Codex hook is not checked on native Windows: Codex may run its command through `cmd.exe`, which does not
  expand `${PLUGIN_ROOT}`.
- The hooks need the plan to carry `Status: active`; a plan written by a version before 0.2.0 has no such line
  and is not brought back until you add it.
- In a headless run (`claude -p`) the question dialog is not available, and `grill` asks in text instead.
- `review` verifies findings by reproducing them, so even a light review takes minutes
  ([Time and cost](BENCH.md#time-and-cost)).
- `review` counts lines without indentation changes, so a change that mixes re-indented lines with real edits can
  be counted smaller than it is and get the lighter tier. The reviewers still read the whole diff; only the depth
  is chosen from the count.
- The tests of the skills check that each rule is in the text, not that it is worded right; what a rule makes an
  agent do is checked by the reviews and the bench.

## Credits

`grill` and `handoff` are based on the `grilling` and `handoff` skills by Matt Pocock
(https://github.com/mattpocock/skills, MIT).

## License

MIT, see [LICENSE](LICENSE).
