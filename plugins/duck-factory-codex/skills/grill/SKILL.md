---
name: grill
description: Use BEFORE writing any code for a non-trivial change - a new feature or module, a choice between approaches, a change across several places, or any request whose goal, scope or acceptance check is unclear. Interviews the user in short rounds, recommended option first, until every decision is settled, then writes a one-page plan to .tmp/plans/. Not for bug fixes, small clear edits, or questions that only need an answer.
---

# Grill

Interview the user until you both understand the task the same way. Based on Matt Pocock's `grilling` skill
(github.com/mattpocock/skills, MIT).

Write everything the user reads in the user's language: questions, option labels and descriptions, summaries and
the plan, its headings included. Only "(Recommended)" stays as is.

## First: is it needed?

You may have started this on your own. If the task is already clear - goal, what not to touch and how to check
the result are all known - say so in one line and skip the interview; write the plan only if the change is large.
If only one thing is unclear, ask that one question instead of a full interview.

## Load the skills for the area

Before the first question, look through the skills available in this session. If the task touches an area one of
them covers - the framework or service in use, the kind of system being designed, the project's own design or
domain rules - open that skill's `SKILL.md` and read it in full now, before the interview. Several areas mean
several skills.

A domain skill changes which questions are worth asking and what the plan must contain, so reading it after the
plan is written is too late. Name the skills you read in the plan. If none fits, go on without one; do not read a
skill only because its name looks close.

## The interview

Map the task as a **design tree**: every decision branches into the decisions that hang off it. Ask only about
decisions that change the plan. A decision with an obvious answer (the code, an earlier decision or the user's
rules settle it) is not a question: take it as a default. Defaults are not hidden: they are shown at the
confirmation and listed in the plan, where the user can change them.

**Facts are your job, decisions are the user's.** Never ask what you can look up: code, configs, logs, versions,
how a tool behaves. Look it up or measure it first.

The **frontier** is every decision whose prerequisites are already settled; a question that depends on an answer
you haven't heard yet waits for a later round. Ask the frontier in rounds, the most consequential first.

**With the `request_user_input` tool** (when this session has it):

- at most 3 questions per call, 2-3 options each; the user can always add their own answer;
- put your recommendation first and end its label with "(Recommended)";
- each question stands alone: put the one fact the choice hinges on into the question itself, in a sentence, with
  its source if it is not obvious (`file:line`, a measurement).

**Without it** (the tool is missing or refused, as in a non-interactive run): ask in text by the same rules - at
most 4 numbered questions, each with its options and the recommended one marked, the fact inside the question -
and say plainly that these are questions waiting for the user's answers, not decisions you made.

**From the second round on**, the last question of the round is the way out: "keep asking" or "enough - take your
recommendations for the rest", with roughly how many decisions are left. If the user picks "enough", settle the
remaining decisions by your recommendations, as defaults, and go to the confirmation. There is no other limit on
rounds: never stop asking on your own while real decisions remain.

Each round reshapes the tree: settled decisions push the frontier outward; recompute it and ask the next round.

The interview is done when the frontier is empty or the user chose "enough". Confirm with one more question that
itself holds the summary: the decisions made and the defaults taken, a line each. Options: write the plan, or
change something. Until the user confirms, change nothing.

## The plan

After the confirmation, write the plan to `.tmp/plans/<short-slug>.md` in the project (create the directory if
needed; `.tmp/` must be in `.gitignore` - if it is not, say so instead of editing `.gitignore`). One page at most,
with these sections:

```markdown
# <task>

Goal: <one or two sentences: what changes for the user>

Skills used: <domain skills read for this task, or "none">

Decisions:
- <each decision from the interview, with the reason in a few words>

Taken by default, not asked:
- <decision> - <why it was obvious, or "user chose to stop the questions">

Not touching: <what stays as it is>

Acceptance criteria (each checked by a test or a command):
- <criterion> - <how it is checked>

Risks and open questions: <if any>
```

### Review of the plan by a fresh reader

For a large task - a new module, a choice between approaches that is costly to reverse, or work of more than a
session - have the plan checked before any code. Skip it for smaller plans, and say that you skipped it.

Spawn a sub-agent (`collaboration.spawn_agent`) with **`fork_turns="none"`**, so that it has not seen the
interview and reads the plan as a stranger would, and give it this brief with the absolute paths filled in:

> Review the plan in `<plan path>` against the repository at `<path>`. Do not change any files. Report only:
> decisions that are wrong or contradict the code, missing decisions that would change the implementation, and
> acceptance criteria that cannot be checked as written. Cite file:line. If the plan is sound, say so in one line.

Report its findings as it gave them and say which you checked and agree with. Do not rewrite the plan from them
yourself: each finding that is a decision goes to the user as a question, and the plan is updated from the
answers. A finding that is a fact you got wrong, correct in the plan and say so.

Show the path and the plan. Until the user approves the plan, change no project files.

## Working by the plan

- Before starting the work, and again after the context was compacted or in a new session, read the plan file:
  it, not your memory of the interview, is the source of truth.
- A decision that turns out wrong during the work is not yours to change silently: stop, say what you found, ask.
- When the work is done, go through the acceptance criteria one by one in the report: the command or test you ran
  and its result, or "not checked" with the reason.
