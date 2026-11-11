# duck_factory

A Claude Code plugin with three skills for a small development pipeline: `grill` (clarify and plan before
code), `review` (one code review with measured depth) and `handoff` (continue the work in a fresh session).

Documentation: [plugins/duck-factory/README.md](plugins/duck-factory/README.md).

```bash
claude plugin marketplace add ilkruglov/duck_factory
claude plugin install duck-factory@duck-factory
```

MIT, see [LICENSE](LICENSE). `grill` and `handoff` are based on skills by Matt Pocock
(https://github.com/mattpocock/skills, MIT).
