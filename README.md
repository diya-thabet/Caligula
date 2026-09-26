# Caligula

Have you ever questioned your local politician? Ever wondered how they manage their lives, or how their opinions shift from X to Y overnight?

Caligula is a political analytics platform designed to track, measure, and explain these shifts. We analyze a politician's changing stances to determine whether their change of heart was a calculated, strategic move, or just blundering hypocrisy.

## The engine

Under the hood, Caligula is an evidence engine for public-interest allegations,
starting with procurement and public-funds cases in Tunisia. It never asks an
LLM whether something is true. A language model (Claude, or any
OpenAI-compatible model, hosted or running on your own server) breaks an
allegation into checkable sub-claims and reads documents; code then verifies
every quote, hashes every
source, detects official records that were rewritten after the fact, collapses
articles that all trace back to one source, and computes the verdict.

See [docs/architecture.md](docs/architecture.md) for the design and roadmap.

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest                                   # Postgres tests run when CALIGULA_TEST_DSN is set

# Offline: replays recorded readings of the synthetic STEG case, writes the case file
caligula run fixtures/steg_synthetic --report out/steg.md

# Same case on PostgreSQL + pgvector
docker compose up -d
caligula run fixtures/steg_synthetic --db postgresql://caligula:caligula@localhost:5432/caligula

# Rank procurement awards by red flags
caligula screen fixtures/awards_synthetic.json

# Score labelled cases and sweep the thresholds
caligula calibrate fixtures

# Agents on Claude (needs ANTHROPIC_API_KEY or an `ant auth login` profile)
caligula investigate "Le taux de chômage est tombé à 12 % en 2026" --mode factcheck
caligula investigate "$(jq -r .allegation.text fixtures/steg_synthetic/case.json)" \
    --mode investigate --team --case-dir fixtures/steg_synthetic

# Agents on any OpenAI-compatible API, with our own web search
export CALIGULA_BASE_URL=https://api.mistral.ai/v1 CALIGULA_API_KEY=...
caligula investigate "..." --llm openai:MODEL --search brave          # BRAVE_API_KEY

# ...or on a local open model (Ollama here), so case data stays on your server
caligula investigate "..." --llm openai:qwen3:32b@http://localhost:11434/v1 --search searxng

# Mixed: local collectors, a stronger hosted reviewer
caligula investigate "..." --team --collector-llm openai:qwen3:32b@http://localhost:11434/v1 \
    --reviewer-llm claude --search searxng
```

Model specs are `claude[:MODEL]` or `openai:MODEL[@BASE_URL]`; defaults come
from `CALIGULA_LLM`, `CALIGULA_BASE_URL`, `CALIGULA_API_KEY` and
`CALIGULA_SEARCH` (SearXNG address in `CALIGULA_SEARXNG_URL`). Weaker models
propose more material that code rejects and may miss evidence; they cannot
make anything count that fails validation.

OCR needs `tesseract-ocr` with the `fra` and `eng` models (`ara` optional) and `poppler-utils`.

The STEG case and award records in `fixtures/` are synthetic: every company,
document and amount is fictional. The STEG case exercises the full pipeline: a
demand-surge hypothesis gets falsified, a JORT award rewritten from 120M to 80M
TND gets flagged, three articles citing one leak count as one source, and
invented quotes are rejected.

Caligula's output is an evidence assessment, not a finding of guilt. It does not
name individuals; attribution requires human review and a right of reply.
See [docs/agent.md](docs/agent.md) for the agents and [docs/legal.md](docs/legal.md)
for the legal framework the design follows.
