# Contributing

## Code layout

Hexagonal (ports and adapters). See [docs/architecture.md](docs/architecture.md#code-structure).

- `domain/`: pure logic and data. No I/O, no SDKs, no clock reads.
- `application/`: use cases and the ports (interfaces) they need.
- `adapters/`: everything that touches the outside world, and the CLI.

A test enforces the dependency rule; run `pytest` before every commit.

## Commits

- One concern per commit. A move is one commit, a behaviour change is another.
- Keep commits reviewable: aim for under ~300 changed lines, excluding pure renames.
- Subject line: `<type>(<scope>): <what>`, 72 characters max.
  Types: `feat`, `fix`, `refactor`, `test`, `docs`, `ci`, `chore`.
  Scopes: `domain`, `app`, `adapters`, `agents`, `cli`, `docs`...
- Reference the roadmap task in the body when there is one: `Task: B2`.
- Every commit leaves the test suite green.

## Tests

- `tests/domain`: pure functions, no fixtures beyond data.
- `tests/application`: use cases with in-memory adapters and scripted agents.
- `tests/adapters`: one adapter at a time, against mocks or local services
  (Postgres tests run when `CALIGULA_TEST_DSN` is set).
- `tests/e2e`: the synthetic cases end to end.

Guards against hidden regressions:

- `support.assert_invariants(ws)`: properties every run must satisfy (counted
  evidence is valid and exactly the accepted proposals, the ledger is intact,
  the verdict obeys its rules, ACH ratings follow predictions, suspicions are
  tested both ways...). Call it at the end of every new workflow test.
- `tests/e2e/golden/steg_case_file.md`: the offline case file, compared line by
  line. When a change to it is intended, regenerate with
  `UPDATE_GOLDEN=1 pytest tests/e2e/test_golden_case_file.py` and commit the
  golden file with the change, so the diff shows in review.
- `tests/e2e/test_determinism.py`: the verdict must be identical across Python
  hash seeds; anything built from a set must be sorted before it is output.
- Scripted agents (`support.ScriptedAgentRunner`, `support.scripted_team`)
  drive the real tools; `scripted_team` keys scripts by the round in the brief.
