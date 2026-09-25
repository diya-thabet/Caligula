# Caligula

Have you ever questioned your local politician? Ever wondered how they manage their lives, or how their opinions shift from X to Y overnight?

Caligula is a political analytics platform designed to track, measure, and explain these shifts. We analyze a politician's changing stances to determine whether their change of heart was a calculated, strategic move, or just blundering hypocrisy.

## The engine

Under the hood, Caligula is an evidence engine for public-interest allegations,
starting with procurement and public-funds cases in Tunisia. It never asks an
LLM whether something is true. Claude breaks an allegation into checkable
sub-claims and reads documents; code then verifies every quote, hashes every
source, detects official records that were rewritten after the fact, collapses
articles that all trace back to one source, and computes the verdict.

See [docs/architecture.md](docs/architecture.md) for the design and roadmap.

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest

# Offline: replays recorded readings of the synthetic STEG case
caligula run fixtures/steg_synthetic

# Live: Claude decomposes the allegation and reads each document
# (needs ANTHROPIC_API_KEY or an `ant auth login` profile)
caligula run fixtures/steg_synthetic --live
```

The STEG case in `fixtures/` is synthetic: every company, document and amount
is fictional. It exercises the full pipeline: a demand-surge hypothesis gets
falsified, a JORT award rewritten from 120M to 80M TND gets flagged, three
articles citing one leak count as one source, and invented quotes are rejected.

Caligula's output is an evidence assessment, not a finding of guilt. It does not
name individuals; attribution requires human review and a right of reply.
