# duck_factory

A plugin for Claude Code and for Codex CLI (`duck-factory`). The sections below describe the Claude Code
version; [Codex](#codex) lists what differs. In Russian: [README.ru.md](README.ru.md). Changes by version: [CHANGELOG.md](CHANGELOG.md).

Three skills that make a small development pipeline for Claude Code: agree on the task before starting, review
the result once with a depth that fits the change, and hand the work over to a fresh session. Two
[hooks](#hooks) keep the plan and the state of the work through a context compaction.

| Skill | When it runs | What it does |
|---|---|---|
| `grill` | by itself, before a non-trivial task, with or without code; or `/duck-factory:grill` | When you approved a list wholesale or the task was the agent's idea, asks first which of it to do at all; then interviews you in short rounds through the question dialog, recommended option first, and writes to `.tmp/plans/` a one-page plan when the work changes code, else a short record of the decisions, steps and acceptance criteria. A large plan that changes code is checked by Codex before any code. |
| `review` | by itself, after a finished code change; or `/duck-factory:review` | Measures the change (code lines, files, call sites, reversibility), picks a tier, runs in parallel the built-in `/code-review`, Codex with the skill's brief and, from the normal tier, Codex's adversarial review (in a final review, a Codex and a Claude reviewer per group of files) plus a check against the plan, verifies every finding, and reports. Also as a final review of all the work before a pull request, a merge or a release; a security pass when you say yes. It only finds; fixes come after you agree. |
| `handoff` | only on `/duck-factory:handoff` | Writes `.tmp/handoff/<slug>.md` so a fresh session can continue: goal, constraints, decisions, what is done and how it was checked, what is in flight, the next step, rollback. The file starts by telling the next session to check it against reality. |

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
- The tests pass - `uvx pytest -q tests`.
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
- **Data the code reads is code**: a table, fixture, schema or prompt that the project's code, tests or checks
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
| none | no code lines changed | - | - | - |
| light | up to 50 code lines, 1 file, up to 5 call sites, reversible | `low` | the brief | no |
| normal | everything else | `medium`; `high` with more than one group | the brief and adversarial, with a focus | yes |
| enhanced | a one-way door, a critical path, over 10 files, over 20 call sites, or you asked | `high` | the brief and adversarial, with a focus | yes |
| final | a final review (below): the tier of the whole change, at least normal | - | per group, and adversarial since the base | yes |
| repeat | after fixes | - | a short brief on the fixes only, Codex and a Claude subagent at `medium` (below) | no |

A one-way door outweighs the other signs; `max` only when you ask for it by name. The tier comes from the table
and nothing else: "this is the core of the system" does not raise it - that is what the list of critical paths
is for. When a measurement is in doubt (is this a one-way door?), the higher tier wins.

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

Why these reviewers. They come from a second measurement, on two real changes from the owner's projects (a Rust
desktop app, about 2,700 changed lines, and a TypeScript service, about 700 lines and 37 new files) with their bugs
known from later fixes; every finding was then checked against the code, and the real bugs sorted into important
ones (a crash, a broken function, lost or wrong data, money, privacy) and minor ones. One run per variant, 22
important bugs in all:

| Reviewers | Important bugs found | Claude tokens | Codex tokens |
|---|---|---|---|
| Codex with the brief + its adversarial review + built-in `high` | 19 | 12.4M | 13.7M + the adversarial review |
| Codex with the brief + a Claude subagent per group (the earlier setup) | 18 | 81.5M | 13.7M |
| Codex's own review + built-in `medium` (the earlier setup for one group) | 12 | 6.4M | 8.7M |
| Codex with the brief alone | 15 | - | 13.7M |
| Codex's own review alone | 10 | - | 8.7M |
| Codex's adversarial review alone | 8 | - | not recorded |

Tokens are counted with cache reads, for both changes together. Codex's come from its session logs
(`total_token_usage`); without cache reads its brief used 0.58M and its own review 0.37M. The plugin runs the
adversarial review as a temporary session and keeps no count of it. Codex spends its own subscription, not Claude's.

The Claude subagents per group found more minor bugs (16 against 9 of 22) at six and a half times the tokens, so
they stay for the final review only. The adversarial review alone is the weakest, but it found an ordering bug no
other reviewer did, in five minutes and without Claude tokens. With one Claude reviewer, effort `xhigh`, `high`
and `medium` found the same important bugs; `medium` used half the tokens.

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

Reviews of single steps miss what only shows when the whole work is in view. In one real session about twenty
step-by-step reviews passed eight bugs that a single review of the whole 35-file change then found, all confirmed
against the code: half of them were two code paths, written in different steps, that disagree.

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

Security scanners are not part of the review. In our runs (November 2026) the scan of changes in OpenAI's Codex
Security plugin refused to start three times out of three, a headless `codex exec` run included; Claude Security
from Anthropic scans only committed changes and asks its own question about the cost. In the last failed run Codex
reviewed the 12 changed files itself instead: 77 seconds in all, two findings (medium and low).

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
On two finished, reviewed changes Codex found 23 real simplifications without Claude tokens (4.4M of its own, 0.26M
without cache reads), a Claude agent with the same directions 14, the two together 31 of 37; `/simplify` found 17
for four times the Claude tokens of the agent (65M against 14M, cache reads included) and in one of the two changed
behaviour.

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

From runs on the three benchmark diffs with an Opus-class model: a light review took 2 to 2.5 minutes and about
$0.70 to $1.00, a normal one about 5 minutes and $1.40. The checks themselves take 1.5 to 2 minutes; the rest is
reproducing the findings. A review in groups takes longer: on a 190-line change in two groups the Codex reviewers
took 4.5 to 5 minutes and the Claude subagents 9 to 14 (one run).

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
| `PreCompact` | a request to keep five things under their own headings (below), and the paths of the active plans and handoff files | into the instructions for the compaction summary |
| `SessionStart` after a compaction | every plan in `.tmp/plans/` with `Status: active`, the newest three in full, as long as the whole output fits both hosts' limits (9500 UTF-16 units for Claude Code, 19,000 bytes of UTF-8 for Codex); while it does not, the largest gives way to its path with a request to read it; the newest three active handoff files in `.tmp/handoff/` by path, with a request to read its traps and decisions again if the session works from it | into the context of the session |
| `SessionStart` of a new or resumed session | one line per active plan and per active handoff file, the newest three of each: its path and when it was last changed, and that the agent reads it only when you ask to continue that work | into the context of the session |

The Codex plugin runs it on `SessionStart` only, with the same output: Codex ignores what a `PreCompact` hook prints
(see [Codex](#codex)).

What the summary is asked to keep, and why. In 24 compactions of one real project the agent went back to the
session transcript 33 times afterwards; this is what it went for, plus what a summary blurs:

- **Exact commands** that produced results still in use or started what is still running. The usual summary
  says what was done, not how: the most frequent thing looked up.
- **Long materials**: texts you pasted, reports of sub-agents, long tool outputs - where each one is.
- **Done, not checked**, and how far a long pass has got: after a compaction "did" and "verified" merge.
- **Waiting on the user**: what you have and have not agreed to. "Next: do X" reads as a permission.
- **Standing corrections**: what you said about how to work, as rules, with the number of repeats.

Not asked for, on purpose: the state of the disk (git can be asked again, and nothing has changed in the seconds
since the summary), the text of the plan (it comes back in full), project rules (reloaded by Claude Code).

- The plans are looked for in every `.tmp/plans/` from the session directory up to the repository root.
- Only the first line of text under the title counts as the `Status:` line, written plainly or in bold; a quote,
  a heading, a list item or a line further down is not the file's own status.
- With your own instructions in `/compact <instructions>` the `PreCompact` hook prints nothing.
- A plan left `active` comes back after every compaction and is named at every start: it is closed when you
  accept the result.
- A resumed session gets only the line, not the plan: its history is intact, and printing the plan on every
  resume would add a copy each time. The hook's output goes to the end of the conversation, so the prompt cache
  is not broken: with and without it a resume read the same 15,080 tokens from the cache.
- If the project has compaction hooks of its own, these run next to them, not instead.
- Checked in a live session: after `/compact` the summary had the extra headings after the standard ones, and
  the model named the plan's path and a marker word from it without reading any file. In a live Codex session
  the model named the active plan and handoff file with their dates, and what it was told to do with each, without
  running a command or reading a file.
- Not measured: whether the extra headings make the work after a compaction better. A repeated correction is
  not cured by keeping its text: in the same project one was in the summary 8 times out of 9 and had to be said
  again anyway.

## Codex

The same pipeline for Codex CLI lives in `plugins/duck-factory-codex` and works entirely inside Codex.

```bash
codex plugin marketplace add ilkruglov/duck_factory
codex plugin add duck-factory@duck-factory
```

Then open `/hooks` in Codex and trust the plugin's hook: Codex does not run it before that, and asks again when an
update changes the script.

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
| Questions in `grill` | the question dialog, up to 4 per round | by mode: in Plan mode `request_user_input` (up to 3 questions, 2-3 options), outside it `request_user_input_async` or `send_message_to_user_async` and always written out in the final message (up to 4), else text |
| The boundary of the work in the plan | a `Not touching` section | a `Scope` section: what the work covers (the Codex model does not write what stays unchanged) |
| Domain skills in `grill` | loaded with the Skill tool | their `SKILL.md` is read |
| Plan check in `grill` | Codex, read-only | a sub-agent with a fresh context |
| The security pass, after your yes | a Codex task (without Codex, a subagent), asked about with AskUserQuestion while the other checks run; in a headless run, at the end of the report | a sub-agent, asked about at the end of the report |
| `handoff` is manual through | `disable-model-invocation` | `agents/openai.yaml`, `allow_implicit_invocation: false` |
| `Critical paths` and `Security paths` are listed in | the project's `CLAUDE.md` | the project's `AGENTS.md` |
| Hooks | `PreCompact` asks the summary to keep five things; `SessionStart` names plans and handoff files and brings the plan back after a compaction | `SessionStart` only, once you trust it in `/hooks`: Codex ignores what `PreCompact` prints; `additionalContextLimit` 5000, as Codex counts a token as 4 bytes of UTF-8 and the default 2500 is too few for a plan in full |

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

To update, install it again: `codex plugin remove duck-factory@duck-factory`, then `codex plugin add
duck-factory@duck-factory`.

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

- Claude Code with the built-in `/code-review`.
- For the second opinion and the plan check: the `codex@openai-codex` plugin, logged in. Without it `review`
  works with Claude only. Codex runs the model and reasoning effort from its own configuration:
  `~/.codex/config.toml` and a trusted project's `.codex/config.toml`.
- `python3` 3.9 or later on PATH: it runs the hooks.
- `timeout` from coreutils (`gtimeout` on macOS): every Codex call runs under it.
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
- **Codex model**: `model` and `model_reasoning_effort` in `~/.codex/config.toml`; the skills pass none.
- **Where plans and handoff files go**: `.tmp/plans/` and `.tmp/handoff/` in the same two skills, in
  `skills/handoff/SKILL.md` and in `scripts/context_hooks.py`.
- **Critical paths** of a project: a `Critical paths` heading in its `CLAUDE.md` (`AGENTS.md` for Codex).
- **Security paths** of a project: a `Security paths` heading in the same file; what counts as a security
  finding there: its `SECURITY.md`.

## Evals

`evals/bench.py` builds a small synthetic project (a notes keeper) and runs the skills on it in either harness
(Linux or macOS: a run that times out is stopped as a process group):

```bash
python3 evals/bench.py list
python3 evals/bench.py review feature --harness claude                       # the installed plugin
python3 evals/bench.py review data --harness claude --plugin-dir plugins/duck-factory   # a working copy
python3 evals/bench.py grill inferred --harness codex
```

- **Review cases** are a repository with an uncommitted change that holds seeded bugs no test of the project
  catches: `small` (one file, one bug, the light tier), `feature` (three code files, one of them new, three
  bugs, the normal tier), `data` (only a CSV table that the code reads, two bugs). The summary prints the tier
  line, which seeded lines the report cites, the time, and whether the working tree stayed untouched.
- **Grill requests** are the ones that should start an interview, the ones that should not (a bug, a typo, a
  question), a list with "do everything" (the first round must ask which of it to do at all), two tasks named
  in the request (no such question) and a task with no code (a plan, but no review of it by another model).

A seeded bug counts as found when the final message cites its line as `file:line` or `file#Lline`, which the skill's report
has to do anyway; both harnesses are judged by the final message alone, not by the trace of commands and sources.
It is still a hint: read the report. A run without a final message (the harness failed, timed out or answered
nothing) is reported as failed, with the end of its error output, not as missed bugs. One run is one sample;
repeat it before comparing two versions of a skill. Runs are kept in `.tmp/evals/`.

The runs are not isolated from your own settings: a global `CLAUDE.md` or `AGENTS.md` that names the skills
makes them start more readily than their descriptions alone would.

## Update and remove

```bash
claude plugin marketplace update duck-factory
claude plugin update duck-factory@duck-factory
claude plugin uninstall duck-factory@duck-factory
```

A new version loads in the next Claude Code session.

## Limits

- Tested on Linux with Claude Code and Opus-class models; the tier measurement used one repository and bugs of
  one kind (path and environment selection logic). The numbers in this file come from those earlier benches, not
  from the synthetic project in `evals/`.
- The Codex hook is not checked on native Windows: Codex may run its command through `cmd.exe`, which does not
  expand `${PLUGIN_ROOT}`.
- The hooks need the plan to carry `Status: active`; a plan written by a version before 0.2.0 has no such line
  and is not brought back until you add it.
- In a headless run (`claude -p`) the question dialog is not available, and `grill` asks in text instead.
- `review` verifies findings by reproducing them, so a light review takes about two minutes, not one.
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
