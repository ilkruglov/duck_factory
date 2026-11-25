# duck_factory: measurements

The measurements behind the choices in [README.md](README.md): the tiers and the reviewers of `review`, the final
review, the security plugins left out, the simplification, time and cost, the Codex version, the hooks, and the
bench in `evals/` that runs the skills on a synthetic project. The README keeps the conclusions; the numbers are
here. In Russian: [BENCH.ru.md](BENCH.ru.md).

## Review tiers

The tiers of `review` come from a measurement on three diffs with seeded bugs (9, 16 and 581 lines, one run per
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

## Reviewers

The reviewers come from a second measurement, on two real changes from the owner's projects (a Rust desktop app,
about 2,700 changed lines, and a TypeScript service, about 700 lines and 37 new files) with their bugs known from
later fixes; every finding was then checked against the code, and the real bugs sorted into important ones (a
crash, a broken function, lost or wrong data, money, privacy) and minor ones. One run per variant, 22 important
bugs in all:

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

## Final review

Reviews of single steps miss what only shows when the whole work is in view. In one real session about twenty
step-by-step reviews passed eight bugs that a single review of the whole 35-file change then found, all confirmed
against the code: half of them were two code paths, written in different steps, that disagree.

## Security plugins

Why the security plugins are not part of the review. In our runs (November 2026) the scan of changes in OpenAI's
Codex Security plugin refused to start three times out of three, a headless `codex exec` run included; Claude
Security from Anthropic scans only committed changes and asks its own question about the cost. In the last failed
run Codex reviewed the 12 changed files itself instead: 77 seconds in all, two findings (medium and low).

## Simplification

Why Codex and the agent simplify, not `/simplify`. On two finished, reviewed changes Codex found 23 real
simplifications without Claude tokens (4.4M of its own, 0.26M without cache reads), a Claude agent with the same
directions 14, the two together 31 of 37; `/simplify` found 17 for four times the Claude tokens of the agent (65M
against 14M, cache reads included) and in one of the two changed behaviour.

## Time and cost

From runs on the three benchmark diffs with an Opus-class model: a light review took 2 to 2.5 minutes and about
$0.70 to $1.00, a normal one about 5 minutes and $1.40. The checks themselves take 1.5 to 2 minutes; the rest is
reproducing the findings. A review in groups takes longer: on a 190-line change in two groups the Codex reviewers
took 4.5 to 5 minutes and the Claude subagents 9 to 14 (one run).

In Codex, from runs on the same three benchmark diffs: a light review took about 2 minutes, a normal one about 2.5,
and every seeded bug was found without changing the tree.

## Codex

Why one pass and not two in the enhanced tier. On two benchmarks (three seeded bugs in a 581-line diff, four
seeded bugs of other kinds in a 4-line diff) the adversarial brief found exactly the bugs the general brief
found, in every run, and took 2 to 2.5 times longer. What it adds is a reproduction for each finding and the
gaps in the tests, which is what a change that cannot be reverted needs. A second pass by the same model did
not find bugs the first one missed.

The Codex version has no second model: on the larger benchmark both Codex briefs missed two real problems that the
`high` level of the other model had found.

## Hooks

In 24 compactions of one real project the agent went back to the session transcript 33 times afterwards; the
request to the summary covers what it went for, most often the exact commands, plus what a summary blurs. A
repeated correction is not cured by keeping its text: in the same project one was in the summary 8 times out of 9
and had to be said again anyway.

The hook's output goes to the end of the conversation, so the prompt cache is not broken: with and without it a
resume read the same 15,080 tokens from the cache.

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

A seeded bug counts as found when the final message cites its line as `file:line` or `file#Lline`, which the
skill's report has to do anyway; both harnesses are judged by the final message alone, not by the trace of
commands and sources. It is still a hint: read the report. A run without a final message (the harness failed,
timed out or answered nothing) is reported as failed, with the end of its error output, not as missed bugs. One
run is one sample; repeat it before comparing two versions of a skill. Runs are kept in `.tmp/evals/`.

The runs are not isolated from your own settings: a global `CLAUDE.md` or `AGENTS.md` that names the skills
makes them start more readily than their descriptions alone would.

## Limits

Tested on Linux with Claude Code and Opus-class models; the tier measurement used one repository and bugs of one
kind (path and environment selection logic). The numbers in this file come from those earlier benches, not from
the synthetic project in `evals/`.
