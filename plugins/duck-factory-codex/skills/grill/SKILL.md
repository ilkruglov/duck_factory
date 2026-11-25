---
name: grill
description: Use BEFORE starting any non-trivial task - a new feature or module, a choice between approaches, a change across several places, work without code that takes more than a few steps (research, a document, a setup), or any request whose goal, scope or acceptance check is unclear. Interviews the user in short rounds, recommended option first, until every decision is settled, then writes the plan to .tmp/plans/: a one-page plan when the work changes code, else a short record of the decisions, steps and acceptance criteria. Not for bug fixes, small clear edits, or questions that only need an answer.
---

# Grill

Interview the user until you both understand the task the same way. Based on Matt Pocock's `grilling` skill
(github.com/mattpocock/skills, MIT).

Write everything the user reads in the user's language: questions, option labels and descriptions, summaries and
the plan, its headings included. Only "(Recommended)" stays as is.

## First: is it needed, and whose task is it?

**Finished work first.** Before anything else - also when the interview is skipped - in a git repository look at
`git status`. If the working tree holds the work of another task that the user has accepted but not committed - its
plan says `Status: done`, or the user said so - first ask whether to commit it: otherwise the review of the new task
reads both. Commit only on the user's command; in a plan mode that forbids changes, commit after leaving it.

You may have started this on your own. If the task is already clear - goal, scope and how to check the
result are all known - say so in one line and skip the interview; still write the record that "The plan" gives it and confirm it as below.
If only one thing is unclear, ask that one question instead of a full interview.

**Settle what to do before how.** The first round asks only about scope - whether to do it at all, and for
several tasks which of them - when either is true:

- the user approved a set of tasks wholesale: "do everything", "all of it", "yes to all" about a backlog, a list
  of your suggestions or someone else's plan;
- the wording of the task is yours: you proposed it, or derived it from your own analysis.

Tasks the user named one by one in the request itself ("add export and a search command") are settled: do not
ask whether to do them.

List the tasks in one question with the options all of them, only some (the user names them), none of them; with a
long list, group the small ones. A single task gets the options do it, postpone it, drop it. For every task say
what the user gets and roughly how much work it is - an hour, a day, a new subsystem - and which one you would
postpone. No design question goes into that round, however consequential: how to build a task is asked only after
the user has said to build it. Twenty questions about work nobody wanted is the most expensive mistake this skill
makes.

## Load the skills for the area

Before the first question, look through the skills available in this session. If the task touches an area one of
them covers - the framework or service in use, the kind of system being designed, the project's own design or
domain rules - open that skill's `SKILL.md` and read it in full now, before the interview. Several areas mean
several skills.

A domain skill changes which questions are worth asking and what the plan must contain, so reading it after the
plan is written is too late. Name the skills you read in the full plan. If none fits, go on without one; do not read a
skill only because its name looks close.

## The interview

Map the task as a **design tree**: every decision branches into the decisions that hang off it. Ask only about
decisions that change the plan. A decision with an obvious answer (the code, an earlier decision or the user's rules
settle it) is not a question: take it as a default. Defaults are not hidden, even when only one question is asked:
put them into the text of the next question you ask (in Plan mode, where a question is one sentence, into the final
message) or, when no question is left, into the confirmation; and list them in the plan, where the user can change
them.

**Facts are your job, decisions are the user's.** Never ask what you can look up: code, configs, logs, versions,
how a tool behaves. Look it up or measure it first.

**Decided before.** A decision the user already made is not asked again. Before the first round, search once, by key
words and without reading every file, for the decisions this task needs: in the earlier plans in every `.tmp/plans/`
from the current folder up to the root of the repository (outside a repository, in the current folder), and in the
project's rules: the instruction files Codex would load for the files this task touches (`AGENTS.md`,
`AGENTS.override.md` and the like) not already in your context, and the files they point to that cover those files.
From a plan, take a decision only from the `Decisions:` section of a plan with `Status: done`, never from its
`Taken by default, not asked` section, never from a line marked (by default) - both were your own picks - and never
from a plan that was dropped. Handoff files in `.tmp/handoff/` of the same folders count too: take decisions from
the `Decisions and why` section of one with `Status: done`, not the options it lists as tried and dropped. Plans and
handoff files are written in the user's language, so look for these headings and the (by default) mark in
translation too; only the `Status:` line is always in English. When two plans or handoff files disagree, ask the
user which one holds, quoting both. If nothing the decision rested on has changed, it is a default like any other,
shown with the plan or file it came from.

The **frontier** is every decision whose prerequisites are already settled; a question that depends on an answer
you haven't heard yet waits for a later round. Ask the frontier in rounds, the most consequential first.

**How to ask.** These questions are required, never optional: the interview exists because the decisions are the
user's. Elapsed time is not an answer, no default is taken because nobody replied, and no work that depends on an
open question is done. Outside Plan mode, say once, as the interview starts, that only in Plan mode (Shift+Tab
switches to it) do the questions come as a dialog that waits for the answers; otherwise they come in text or in a
dialog that does not wait. Codex gives different question tools in different modes; use the row for this session:

| Tool | When | Per call, and how the answers arrive |
|---|---|---|
| `request_user_input` | in Plan mode, the only mode that has it: Codex itself asks for it there | at most 3 questions, 2-3 options each; each question one sentence with a header of up to 12 characters, the fact it hinges on in the option descriptions; the call waits for the answers |
| `request_user_input_async` | outside Plan mode, if the session has it | up to 4 questions, 2-4 options each; the call returns at once and the answers come in the user's next message |
| `send_message_to_user_async` | outside Plan mode, when there is no `request_user_input_async` | up to 4 numbered questions in text; the answers come in the user's next message |
| none, or the tool fails | | up to 4 numbered questions in the final message; say plainly that these are questions waiting for the user's answers, not decisions you made |

Outside Plan mode, whatever tool you use, end the turn with the open questions written out in your final message:
that message is what the user always sees. A question tool not in this table follows its own description of how
the answers arrive; the questions stay required.

For every question: put your recommendation first and end its label with "(Recommended)"; the user can always add
their own answer; put the one fact the choice hinges on into the question itself, in a sentence, with its source if
it is not obvious (`file:line`, a measurement).

**From the second round on**, the last question of the round is the way out: "keep asking" or "enough - take your
recommendations for the rest", with roughly how many decisions are left. If the user picks "enough", settle the
remaining decisions by your recommendations, as defaults, and go to the confirmation. There is no other limit on
rounds: never stop asking on your own while real decisions remain.

Each round reshapes the tree: settled decisions push the frontier outward; recompute it and ask the next round.

The interview is done when the frontier is empty or the user chose "enough". Confirm with one more question that
itself holds the summary. For work that changes program code ("The plan") the summary is the decisions made and the
defaults taken, a line each, and the options are: write the plan, or change something. For work without code the
summary is the short record itself, and the options are: start, or change something; in Plan mode, where a
question is one sentence, the record goes into the final message and the question asks about it. Until the user
confirms, change nothing.

## The plan

Which form depends on whether the work changes program code: code that runs, such as a hook, a service, a script
in the repository or a CI workflow, and a config, prompt or data file the code reads. A skill, a prompt the project's
code does not read, a document, slides, research or a setup take the short record, also with tests or checks next to them and
with scripts in `.tmp/`. Both go to
`.tmp/plans/<short-slug>.md` in the project (create the directory if needed; `.tmp/` must be in `.gitignore` - if it
is not, say so instead of editing `.gitignore`). Plan mode allows no edits: in Plan mode, give the plan or the record
in your final answer and write the file once the user has left Plan mode.

**With code**, after the confirmation write the full plan, one page at most:

```markdown
# <task>

Status: active

Source: <the user's words that ask for this, quoted; for a task you proposed, the words that confirmed it>

Goal: <one or two sentences: what changes for the user>

Skills used: <domain skills read for this task, or "none">

Decisions:
- <each decision from the interview, with the reason in a few words>

Taken by default, not asked:
- <decision> - <why it was obvious, or "user chose to stop the questions">

Scope: <what the work covers: the parts of the project it changes and the deliverables>

Acceptance criteria (each checked by a test, by a command, or by the user looking at a named result):
- <criterion> - <the test or command; or "the user looks at <what you will show them>">

Risks and open questions: <if any>
```

**Without code**, write the short record once the user has said yes to it in the confirmation, and start.

```markdown
# <task>

Status: active

Source: <the user's words that ask for this, quoted; for a task you proposed, the words that confirmed it>

Decisions:
- <each decision from the interview; a default you took, marked (by default)>

Steps:
1. <what you will do, in order>

Acceptance criteria:
- <criterion> - <how it is checked: a test, a command, or what the user looks at>
```

Write the `Status:` line in English, exactly as shown, right under the title, whatever the language of the plan: it marks the plan to re-read after a compaction or in a new session.
Its values are `active`, `done` and `dropped`. A criterion that only a person can judge - how a text reads, how a
picture looks, whether a setup is convenient - is checked by showing it to the user: name what you will show.

### Review of the plan by a fresh reader

This step applies only to a full plan. A short record is not sent to a sub-agent, and the skipped review is not mentioned.

For a large task - a new module, a choice between approaches that is costly to reverse, or work of more than a
session - have the plan checked before any code. Skip it for smaller plans, and say that you skipped it.

Spawn a sub-agent (`collaboration.spawn_agent`) with **`fork_turns="none"`**, so that it has not seen the
interview and reads the plan as a stranger would, and give it this brief with the absolute paths filled in (in
Plan mode, where the file is not written yet, put the plan's text into the brief in place of its path):

> Review the plan in `<plan path>` against the repository at `<path>`. Do not change any files. Report only:
> decisions that are wrong or contradict the code, missing decisions that would change the implementation, and
> acceptance criteria that cannot be checked as written. Cite file:line. If the plan is sound, say so in one line.

Report its findings as it gave them and say which you checked and agree with. Do not rewrite the plan from them
yourself: each finding that is a decision goes to the user as a question, and the plan is updated from the
answers. A finding that is a fact you got wrong, correct in the plan and say so.

Show the path and the plan. Until the user approves a full plan, change no project files and start nothing the plan
describes.

## Working by the plan

- Before starting the work, and again after the context was compacted or in a new session, read the plan file:
  it, not your memory of the interview, is the source of truth. If you do not remember which plan is current, it
  is the one in `.tmp/plans/` with `Status: active`.
- A decision that turns out wrong during the work is not yours to change silently: stop, say what you found, ask.
  When the user changes a decision during the work, update the plan so that it keeps saying what was decided: the
  decision under `Decisions:` (a default from `Taken by default` that the user changed moves there; in a short
  record, drop its (by default) mark), and the acceptance criteria and, in a full plan, the `Scope:` section that followed from the old one.
- A defect in work the user already agreed to is different: the result does not do what the plan says, and you
  can see that yourself. Redo it without asking and say what was wrong and what you changed. Ask only when the fix
  needs a decision the plan does not hold.
- When the work is done, go through the acceptance criteria one by one in the report: the command or test you ran
  and its result, what you are showing the user to look at, or "not checked" with the reason.
- When the user has accepted the result, change the plan's `Status: active` to `Status: done`; when the work is
  cancelled, to `Status: dropped`. A plan left active will be taken for current work in a later session.
