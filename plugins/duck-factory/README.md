# duck-factory

Three skills that make a small development pipeline for Claude Code: agree on the task before code, review
the result once with a depth that fits the change, and hand the work over to a fresh session.

| Skill | When it runs | What it does |
|---|---|---|
| `grill` | by itself, before a non-trivial change; or `/duck-factory:grill` | Interviews you in short rounds through the question dialog, recommended option first, then writes a one-page plan to `.tmp/plans/`. For large tasks the plan is checked by Codex before any code. |
| `review` | by itself, after a finished code change; or `/duck-factory:review` | Measures the change (code lines, files, call sites, reversibility), picks a tier, runs the built-in `/code-review` and Codex in parallel plus a check against the plan, verifies every finding, and reports. It only finds; fixes come after you agree. |
| `handoff` | only on `/duck-factory:handoff` | Writes `.tmp/handoff/<slug>.md` so a fresh session can continue: goal, constraints, decisions, what is done and how it was checked, what is in flight, the next step, rollback. The file starts by telling the next session to check it against reality. |

## The pipeline

1. `grill` settles the decisions and writes the plan with acceptance criteria.
2. You approve the plan; the work goes test first.
3. `review` runs once, before the report or a commit.
4. After you agree: a failing test and a fix for each confirmed bug, `/simplify`, the tests, and a repeat review
   aimed at the fixed places.
5. `handoff` when the work continues in another session.

## Review tiers

| Tier | When | Built-in review | Codex | Plan check |
|---|---|---|---|---|
| none | no code lines changed | - | - | - |
| light | up to 50 code lines, 1 file, up to 5 call sites, reversible | `low` | review | no |
| normal | everything else | `medium` | review | yes |
| enhanced | a one-way door, over 10 files, over 20 call sites, or you asked | `high` | adversarial, with a focus | yes |
| repeat | after fixes | as light, aimed at the fixes | review | no |

The tiers come from a measurement on three diffs with seeded bugs (9, 16 and 581 lines; one run per cell):
`medium` and Codex found every seeded bug, `high` took twice as long as `medium` for the same bugs, and `low`
missed one of three on the largest diff. The call-site thresholds are a cautious guess, not a measurement.

When Codex is unavailable (a limit, no login, a model error), the skill does not retry: it says so, raises the
built-in review one level and stays with Claude for the rest of the session.

## Requirements

- Claude Code with the built-in `/code-review` and `/simplify`.
- For the second opinion and the plan check: the `codex@openai-codex` plugin, logged in. Without it `review`
  works with Claude only. The Codex model is pinned in the skills as `gpt-6-astra`; change it there if you use
  another one.
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

## Limits

- Tested on Linux with Claude Code and Opus-class models; the tier measurement used one repository and bugs of
  one kind (path and environment selection logic).
- In a headless run (`claude -p`) the question dialog is not available, and `grill` asks in text instead.
- `review` verifies findings by reproducing them, so a light review takes about two minutes, not one.

## Credits

`grill` and `handoff` are based on the `grilling` and `handoff` skills by Matt Pocock
(https://github.com/mattpocock/skills, MIT).

## License

MIT, see [LICENSE](https://github.com/ilkruglov/duck_factory/blob/main/LICENSE).
