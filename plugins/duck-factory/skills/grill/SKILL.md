---
name: grill
description: Use BEFORE starting any non-trivial task - a new feature or module, a choice between approaches, a change across several places, work without code that takes more than a few steps (research, a document, a setup), or any request whose goal, scope or acceptance check is unclear. Interviews the user in short rounds through the AskUserQuestion dialog, recommended option first, until every decision is settled, then writes a one-page plan to .tmp/plans/. Not for bug fixes, small clear edits, or questions that only need an answer.
argument-hint: "What are we planning?"
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

You may have started this on your own. If the task is already clear - goal, what not to touch and how to check
the result are all known - say so in one line and skip the interview; write the plan only if the change is large.
If only one thing is unclear, ask that one question instead of a full interview.

**Settle what to do before how.** The first round asks only about scope - whether to do it at all, and for
several tasks which of them - when either is true:

- the user approved a set of tasks wholesale: "do everything", "all of it", "yes to all" about a backlog, a list
  of your suggestions or someone else's plan;
- the wording of the task is yours: you proposed it, or derived it from your own analysis.

Tasks the user named one by one in the request itself ("add export and a search command") are settled: do not
ask whether to do them.

List the tasks as the options of one multi-select question and say in it that picking none means doing none of
them; with more than four tasks, group the small ones or add a second scope question to the same round. A single
task gets the options do it, postpone it, drop it. For every task say what the user gets and roughly how much work
it is - an hour, a day, a new subsystem - and which one you would postpone. No design question goes into that
round, however consequential: how to build a task is asked only after the user has said to build it. Twenty
questions about work nobody wanted is the most expensive mistake this skill makes.

## Load the skills for the area

Before the first question, look through the skills available in this session. If the task touches an area one of
them covers - the framework or service in use, the kind of system being designed, the project's own design or
domain rules - call the Skill tool for it now, before the interview. Several areas mean several skills.

A domain skill changes which questions are worth asking and what the plan must contain, so loading it after the
plan is written is too late. Name the skills you loaded in the plan. If none fits, go on without one; do not load
a skill only because its name looks close.

## The interview

Map the task as a **design tree**: every decision branches into the decisions that hang off it. Ask only about
decisions that change the plan. A decision with an obvious answer (the code, an earlier decision or the user's rules
settle it) is not a question: take it as a default. Defaults are not hidden, even when only one question is asked:
put them into the text of the next question you ask or, when no question is left, into the confirmation; and list
them in the plan, where the user can change them.

**Facts are your job, decisions are the user's.** Never ask what you can look up: code, configs, logs, versions,
how a tool behaves. Look it up or measure it first. When a lookup is long, start it in a subagent and ask the
questions that do not depend on it meanwhile.

**Decided before.** A decision the user already made is not asked again. Before the first round, search once, by key
words and without reading every file, for the decisions this task needs: in the earlier plans in every `.tmp/plans/`
from the current folder up to the root of the repository (outside a repository, in the current folder), and in the
project's rules: the instruction files Claude Code would load for the files this task touches (`CLAUDE.md`,
`AGENTS.md`, `.claude/rules/` and the like) not already in your context, and the files they point to that cover those
files. From a plan, take a decision only from the `Decisions:` section of a plan with `Status: done`, never from its
`Taken by default, not asked` section (those were your own picks) and never from a plan that was dropped. Plans are
written in the user's language, so look for these sections under a translated heading too; only the `Status:` line is
always in English. When two plans disagree, ask the user which one holds, quoting both. If nothing the decision
rested on has changed, it is a default like any other, shown with the plan or file it came from.

Ask with the **AskUserQuestion** tool, never as a numbered list in text. If the tool is not available in this
session (a headless run), ask in text by the same rules: at most 4 questions, each standing alone, your
recommendation marked, and say plainly that these are questions waiting for the user's answers.

- **At most 4 questions per call**, the most consequential first. The **frontier** is every decision whose
  prerequisites are already settled; a question that depends on an answer you haven't heard yet waits for a later
  round.
- **Each question stands alone.** While the dialog is open, the user may not see any text from the same turn, so
  nothing they need may live only in that text. Put the one fact the choice hinges on into the question itself, in
  a sentence, with its source if it is not obvious (`file:line`, a measurement).
- **2-4 options per question**, each a real choice with its consequence in the description. Put your
  recommendation first and end its label with "(Recommended)". The user can always pick "Other" and type.
- A short header per question (up to 12 characters) naming the decision.
- **From the second round on**, make the last question of the call the way out: "keep asking" or "enough - take
  your recommendations for the rest". Say in it roughly how many decisions are left. If the user picks "enough",
  settle the remaining decisions by your recommendations, as defaults, and go to the confirmation. There is no
  other limit on rounds: never stop asking on your own while real decisions remain.

Each round reshapes the tree: settled decisions push the frontier outward; recompute it and ask the next round. If
the next call follows in the same turn, start its first question with one line on what the last round settled.

The interview is done when the frontier is empty or the user chose "enough". Confirm with one more
AskUserQuestion whose question text itself holds the summary: the decisions made and the defaults taken, a line
each. Options: write the plan, or change something. Until the user confirms, change nothing.

## The plan

After the confirmation, write the plan to `.tmp/plans/<short-slug>.md` in the project (create the directory if
needed; `.tmp/` must be in `.gitignore` - if it is not, say so instead of editing `.gitignore`). One page at most,
with these sections:

```markdown
# <task>

Status: active

Source: <the user's words that ask for this, quoted; for a task you proposed, the words that confirmed it>

Goal: <one or two sentences: what changes for the user>

Skills used: <domain skills loaded for this task, or "none">

Decisions:
- <each decision from the interview, with the reason in a few words>

Taken by default, not asked:
- <decision> - <why it was obvious, or "user chose to stop the questions">

Not touching: <what stays as it is>

Acceptance criteria (each checked by a test, by a command, or by the user looking at a named result):
- <criterion> - <the test or command; or "the user looks at <what you will show them>">

Risks and open questions: <if any>
```

Write the `Status:` line in English, exactly as shown, whatever the language of the plan: the plugin's hook looks for it to show the plan again after a compaction.
Its values are `active`, `done` and `dropped`. A criterion that only a person can judge - how a text reads, how a
picture looks, whether a setup is convenient - is checked by showing it to the user: name what you will show.

### Review of the plan by Codex

This step applies only when the plan changes code in a repository. A plan with no code in it - research, a
document, a setup - is not sent to Codex, and the skipped review is not mentioned.

For a large task - a new module, a choice between approaches that is costly to reverse, or work of more than a
session - have Codex check the plan before any code. Skip it for smaller plans, and say that you skipped it.

Find the plugin path as the `review` skill does (step 2 there) and put it in place of `<CODEX_ROOT>`, then from
the project root:

```bash
timeout 900 node "<CODEX_ROOT>/scripts/codex-companion.mjs" task --fresh "Review the plan in .tmp/plans/<slug>.md against this repository. Do not change any files. Report only: decisions that are wrong or contradict the code, missing decisions that would change the implementation, and acceptance criteria that cannot be checked as written. Cite file:line. If the plan is sound, say so in one line. Answer in <the user's language>."
```

Use `gtimeout` on macOS (from coreutils) in place of `timeout`. It takes a few minutes: run it in the background
and wait for the completion notice. Without `--write` Codex cannot edit files. Report its findings as it gave them
and say which you checked and agree with. Do not rewrite the plan from them yourself: each finding that is a
decision goes to the user as a question, and the plan is updated from the answers.

Show the path and the plan. The plan is not consent to start: changing code or anything else still needs the
user's explicit go-ahead for this plan.

## Working by the plan

- Before starting the work, and again after the context was compacted or in a new session, read the plan file:
  it, not your memory of the interview, is the source of truth.
- A decision that turns out wrong during the work is not yours to change silently: stop, say what you found, ask.
  When the user changes a decision during the work, update the plan so that it keeps saying what was decided: the
  decision under `Decisions:` (a default from `Taken by default` that the user changed moves there), and the
  acceptance criteria and the `Not touching:` section that followed from the old one.
- A defect in work the user already agreed to is different: the result does not do what the plan says, and you
  can see that yourself. Redo it without asking and say what was wrong and what you changed. Ask only when the fix
  needs a decision the plan does not hold.
- When the work is done, go through the acceptance criteria one by one in the report: the command or test you ran
  and its result, what you are showing the user to look at, or "not checked" with the reason.
- When the user has accepted the result, change the plan's `Status: active` to `Status: done`; when the work is
  cancelled, to `Status: dropped`. The plugin's hook puts every active plan of the project back into
  context after a compaction and names it when a session starts, so a plan left active keeps coming back.
