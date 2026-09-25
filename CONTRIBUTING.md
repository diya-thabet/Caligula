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
