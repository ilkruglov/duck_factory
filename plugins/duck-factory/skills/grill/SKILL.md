---
name: grill
description: Use BEFORE writing any code for a non-trivial change - a new feature or module, a choice between approaches, a change across several places, or any request whose goal, scope or acceptance check is unclear. Interviews the user in short rounds through the AskUserQuestion dialog, recommended option first, until every decision is settled, then writes a one-page plan to .tmp/plans/. Not for bug fixes, small clear edits, or questions that only need an answer.
argument-hint: "What are we planning?"
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

## The interview

Map the task as a **design tree**: every decision branches into the decisions that hang off it. Ask only about
decisions that change the plan. A decision with an obvious answer (the code, an earlier decision or the user's
rules settle it) is not a question: take it as a default. Defaults are not hidden: they are shown at the
confirmation and listed in the plan, where the user can change them.

**Facts are your job, decisions are the user's.** Never ask what you can look up: code, configs, logs, versions,
how a tool behaves. Look it up or measure it first. When a lookup is long, start it in a subagent and ask the
questions that do not depend on it meanwhile.

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

Goal: <one or two sentences: what changes for the user>

Decisions:
- <each decision from the interview, with the reason in a few words>

Taken by default, not asked:
- <decision> - <why it was obvious, or "user chose to stop the questions">

Not touching: <what stays as it is>

Acceptance criteria (each checked by a test or a command):
- <criterion> - <how it is checked>

Risks and open questions: <if any>
```

### Review of the plan by Codex

For a large task - a new module, a choice between approaches that is costly to reverse, or work of more than a
session - have Codex check the plan before any code. Skip it for smaller plans, and say that you skipped it.

Find the plugin path as the `review` skill does (step 2 there, `CODEX_ROOT`), then from the project root:

```bash
node "$CODEX_ROOT/scripts/codex-companion.mjs" task --fresh --model gpt-6-astra "Review the plan in .tmp/plans/<slug>.md against this repository. Do not change any files. Report only: decisions that are wrong or contradict the code, missing decisions that would change the implementation, and acceptance criteria that cannot be checked as written. Cite file:line. If the plan is sound, say so in one line. Answer in <the user's language>."
```

It takes a few minutes: run it in the background and wait for the completion notice. Without `--write` Codex
cannot edit files. Report its findings as it gave them and say which you checked and agree with. Do not rewrite
the plan from them yourself: each finding that is a decision goes to the user as a question, and the plan is
updated from the answers.

Show the path and the plan. The plan is not consent to edit code: changing code still needs the user's explicit
go-ahead for this plan.

## Working by the plan

- Before starting the work, and again after the context was compacted or in a new session, read the plan file:
  it, not your memory of the interview, is the source of truth.
- A decision that turns out wrong during the work is not yours to change silently: stop, say what you found, ask.
- When the work is done, go through the acceptance criteria one by one in the report: the command or test you ran
  and its result, or "not checked" with the reason.
