---
name: handoff
description: Write a handoff file so a fresh session can continue this work - goal, decisions, what is done and how it was checked, what is left, the next step. Run only when the user asks for it by name.
---

# Handoff

Write a handoff document from this conversation so that a new session, which knows nothing of it, can continue the
work. Based on Matt Pocock's `handoff` skill (github.com/mattpocock/skills, MIT).

Write it in the user's language.

## Where

`.tmp/handoff/<short-slug>.md` in the project (create the directory; `.tmp/` must be in `.gitignore` - if it is
not, say so instead of editing `.gitignore`). If this work already has a handoff file - the user named one, or the
session started from one - update that file in place instead of creating a second one.

## What goes in

Only what the next session cannot get faster from the repository. Point to plans, specs, commits and files by path
(`.tmp/plans/...`, `file:line`, a commit hash) instead of copying them. Keep it to a page or two.

```markdown
# <work> - handoff, <date>

First, check this file against reality: `git status` and `git log -3`, whether the processes under "In flight"
still run, whether the files named here exist. Tell the user what differs before doing anything else.

Goal: <what we are doing and why, one or two sentences>

Constraints: <what must not be touched; rules that apply to this work beyond AGENTS.md>

Read first: <the plan in .tmp/plans/, key files with file:line>

Decisions and why: <the ones not written in the plan; what was tried and dropped, with the reason>

Done and checked:
- <what> - <command or test and its result>

Done, not checked: <what, and why not>

In flight: <background processes, running jobs, uncommitted changes, branches, worktrees - with ids and paths>

Left to do: <in order>

Next step: <the single first action for the new session>

Traps: <what cost time here and how to avoid it; the user's corrections in this session>

Waiting on the user: <open questions and decisions>

Rollback: <the commit this work started from; what to delete or revert to get back to it>
```

If the user passed arguments, they say what the next session is for: shape "Left to do" and "Next step" around
that.

## Rules

- State facts with their source, and mark what you did not verify: the next session will act on this file.
- Keep the "First, check this file against reality" paragraph in every handoff, translated into the user's
  language: the file goes stale as soon as anything changes between sessions.
- Do not write secrets: tokens, keys, passwords, personal data.
- Change nothing but the handoff file.
- End your reply with the path and one line the user can paste into the new session to start from it.
