# Caligula architecture

Caligula is an evidence engine for public-interest allegations: procurement
corruption, misuse of public funds, and politicians' statements that shift or
get quietly rewritten. It started from the investigation-agent draft (STEG
scenario). This document records what we kept, what we changed, and why.

## Core principle

> Never ask the LLM whether an allegation is true. Ask it what evidence would
> settle each part, have it read that evidence, and let code do the
> bookkeeping, hashing, math and verification.

| LLM (Claude) | Code |
|---|---|
| Breaks the allegation into sub-claims and hypotheses | Validates every proposal before it counts |
| Reads documents, proposes edges with exact quotes | Checks quotes verbatim against stored text |
| Proposes amounts with quotes | Re-extracts the amount from the quote |
| (V3) Picks the next search from the evidence gap | Hashes, diffs versions, clusters origins, scores, decides the verdict |

## Decisions taken from the draft

1. **One engine, several claim types.** The README's "stance shift" idea and
   the corruption agent share the same core: timestamped, hashed, versioned
   sources and detection of after-the-fact rewrites. A politician's deleted
   statement is a retcon just like a rewritten JORT award. Both become
   `claim_type`s on the same engine.
2. **Python only for V1.** The draft's Spring Boot + Python + Kafka + MinIO +
   LangGraph stack means two languages and four services before the first
   result. V1 is one Python package. Postgres + pgvector replaces the
   in-memory store in V2 behind the same `EvidenceStore` interface. Kafka and a
   JVM API come back only if ingestion volume or a team needs them.
3. **Any model provider.** The workflow depends on two ports, `ClaimAnalyst`
   and `AgentRunner`. Adapters: Claude (official SDK: structured outputs,
   tool runner, server-side refusal fallbacks and web search) and any
   OpenAI-compatible API (hosted, or open models self-hosted with vLLM or
   Ollama, which keeps case data on our servers). Web search is a port of its
   own (SearXNG, Brave) so it does not depend on the model provider. Each role
   (analyst, collectors, reviewer) can run on a different model. No
   LangGraph: the loop is short and explicit.
4. **Two hashes, field-level diffs.** SHA-256 of raw bytes proves chain of
   custody but changes on any re-render (PDF metadata, HTML template), so on
   its own it would flag almost everything. A second hash over normalized text
   (NFKC, Arabic-Indic digits, tatweel, whitespace, case) detects content
   change, and a retcon is reported only when an extracted field (amount, date,
   decree number) differs. The flag says *what* changed: `120000000 -> 80000000`.
5. **Archives are attestations, not truth.** A Wayback capture proves the
   content existed at capture time. Captures can be missing or excluded on
   request. We fetch captures in raw mode (`id_`) so we hash what the site
   served, not Wayback's replay page.
6. **Uncalibrated weights are labelled as such.** Source weights and
   thresholds are priors in `domain/services/scoring.py`. Before any score is published they
   must be fitted on a labelled set of past cases (for example Cour des comptes
   findings with known outcomes). Every verdict carries a disclaimer saying so.
7. **No automatic naming of people.** The draft's suspect ranker ran with "no
   manual validator". In Tunisia, Decree-law 2022-54 is used to prosecute
   journalists and critics, and a wrong name is a real harm to a real person.
   The engine therefore stops at the evidence: the strongest verdict is
   `high_suspicion`, and it never outputs "corruption proven". The V4 entity
   graph will rank *relationships* for a human reviewer, gated by review and a
   right-of-reply step before anything names a person.
8. **Protect contributors first.** A geotagged WhatsApp photo can locate the
   whistleblower. Uploads are hashed on receipt, their metadata (GPS, device)
   goes into a restricted custody record, and only a metadata-stripped copy
   enters the evidence store. Location is verified internally, never published.
   See Law 2017-10 on whistleblower protection.
9. **Realistic sources.** UN Comtrade gives trade totals by product code, not
   contract prices, so it is a weak benchmark. Prior TUNEPS awards for
   comparable works are the primary benchmark. Much of the JORT is scanned, so
   Arabic/French OCR is needed early (V2). TUNEPS and RNE access must be
   confirmed before we depend on them.

## Code structure

Hexagonal (ports and adapters). The rule: **dependencies point inwards**.

```
             ┌──────────────────────── adapters ────────────────────────┐
             │  cli · presenters · fixtures · llm (Claude) · sources     │
             │  persistence (memory, Postgres, blobs, ledger) · media    │
             │        ┌──────────── application ────────────┐            │
             │        │  use cases · investigation workflow  │            │
             │        │  ports (interfaces the core needs)   │            │
             │        │      ┌────────── domain ─────────┐   │            │
             │        │      │  model · pure services     │   │            │
             │        │      └────────────────────────────┘   │            │
             │        └───────────────────────────────────────┘            │
             └────────────────────────────────────────────────────────────┘
```

```
src/caligula/
├── domain/                     pure: no I/O, no SDK, no clock
│   ├── model/                  documents, claims, evidence, registers, verdict, intake, procurement
│   └── services/               text, extraction, retcon, provenance, validation,
│                               interest, absence, scoring, innocent, ach,
│                               sensitivity, judgment, verdict, names, privacy,
│                               intake_policy, red_flags, ledger_chain
├── application/
│   ├── ports/                  repository, blobs, ledger, sources, extraction, llm
│   ├── usecases/               intake, decompose, evaluate_case, calibration, publication
│   └── investigation/          workspace, plan, toolkit, prompts, brief,
│                               single_agent, team
└── adapters/
    ├── persistence/            memory, postgres (+ schema.sql), blob_fs, ledger_jsonl, search
    ├── sources/                wayback, worldbank, web, web_search, telegram
    ├── media/                  text_extraction (PDF, OCR), image_sanitizer
    ├── llm/                    analyst_base (prompts, schemas), claude_analyst, claude_runner,
    │                           openai_compat, tool_schema
    ├── presenters/             markdown_report, analysis, public_reply, cli_summary
    ├── fixtures/               case_directory
    └── cli/                    main (argument parsing), bootstrap and models (composition root)
```

| Layer | May import | Must not import |
|---|---|---|
| `domain` | standard library, pydantic | `application`, `adapters`, SDKs, I/O libraries |
| `application` | `domain`, its own ports | `adapters`, `anthropic`, `httpx`, `psycopg`, `PIL` |
| `adapters` | anything | nothing is off limits, but each adapter implements one port |

How the pieces meet:

- **Ports** are `typing.Protocol` classes in `application/ports`. The
  investigation workflow asks for an `AgentRunner` and a `ClaimAnalyst`; it
  never sees the Anthropic SDK.
- **The toolkit** (`application/investigation/toolkit.py`) implements what each
  agent tool *does* to the workspace, in plain Python. The Claude adapter only
  binds those methods as tools and translates refusals into tool errors.
- **The composition root** (`adapters/cli/bootstrap.py`) is the only place
  that chooses concrete adapters (memory or Postgres, Claude, live sources).
- **Domain services take data, not repositories**: validation and scoring
  receive the documents and an integrity check, so they are testable with
  plain objects.

## Pipeline (V1)

```
case.json + documents
      │
      ▼
EvidenceStore ── BlobStore (content-addressed, write-once, raw SHA-256)
      │           text SHA-256 over normalized text
      ▼
Allegation ── sub-claims C1..Cn, hypotheses H1..Hm with predictions,
      │        parties, expected records (recorded, or Claude `decompose`)
      │        + code adds every missing standard innocent explanation
      ▼
Readings ── edges {doc, sub-claim, supports|contradicts|qualifies, quote}
      │      figures {doc, allocated|disbursed|benchmark|proven_spend, amount, quote}
      │      absences {sub-claim, register, query, window, capture?}
      │      (recorded, or Claude `read` per document, or agents)
      ▼
validation ── doc exists, blob hash intact, quote verbatim, amount in quote,
      │         known register and a window the search could cover
      │         rejected items are reported, never silently dropped
      ▼
retcon ── versions per canonical URL, field diffs
provenance ── union-find over cites / derived_from / same document / same text
      ▼
scoring ── item weight: source kind, then the publisher's interest
      │        (self-serving x0.5, against interest >= 0.8), then the
      │        penalty for a rewritten version; absence = register completeness
      │        per sub-claim: noisy-OR over independent clusters,
      │        each cluster counted once at its best item's weight
      │        hypotheses: falsified if any prediction is contradicted
      │        financial: committed amount (from the attested version) vs
      │        proven spend / benchmark; flagged if > 20% with >= 2 origins
      ▼
ACH ── every item rated against every competing hypothesis (from predictions);
      │   diagnostic items; ranking by weight of evidence against; untested apart
      ▼
verdict ── contradicted | unverified | partially_supported | high_suspicion
      │     missing evidence, retcon flags, rejected proposals
      ▼
sensitivity ── remove each origin, recompute: what the conclusion depends on
      ▼
judgment ── likelihood of the core facts (estimative words) and
              confidence (low | moderate | high) with every reason that capped it
```

### Source weights (priors)

Inverse to how easily the accused can silently change the source:

| Kind | Weight |
|---|---|
| audit (Cour des comptes, IMF/EBRD) | 0.85 |
| foreign mirror (funder records) | 0.80 |
| archive (Wayback, Common Crawl) | 0.75 |
| statistics, OSINT | 0.70 |
| contributor (hashed upload) | 0.60 |
| official live page | 0.50 (x0.3 if it diverges from an earlier attested copy) |
| news | 0.35 |
| social | 0.15 |

Then the publisher's interest in the point (`domain/services/interest.py`):
what a party to the case (accused or complainant) says in its own favour is
halved; what it concedes against its own interest weighs at least 0.8.
An absence weighs the completeness of the searched register
(`domain/model/registers.py`: TUNEPS 0.8, JORT 0.85, web search 0.05), halved
without a stored capture of the empty result.

### Verdict rule

- Any core sub-claim contradicted: `contradicted`.
- All core sub-claims supported **and** a deterministic signal (financial
  anomaly or retcon) **and** no innocent explanation consistent with the
  evidence: `high_suspicion`.
- Some core sub-claims supported: `partially_supported`.
- Otherwise: `unverified`.

The causal inference ("funds were misappropriated") is never a core
sub-claim; it is what the verdict is about, and it is never marked proven.

### Judgment

Following US intelligence analytic standards (ICD 203), how likely a
conclusion is and how solid its basis is are two statements
(`domain/services/judgment.py`):

- **Likelihood** that every core sub-claim is true, in estimative words
  (unlikely, likely, very likely...), or "cannot be assessed" when a core
  sub-claim has no evidence at all.
- **Confidence** low, moderate or high, capped by each weakness, all listed:
  a core sub-claim unsettled, contested, resting on one origin or on weak
  sources; a verdict that one origin could overturn (sensitivity analysis);
  an innocent explanation untested, open or fitting the evidence; a
  supported sub-claim nobody tried to refute.

Competing hypotheses (`domain/services/ach.py`) are compared as Heuer's ACH
does: evidence that fits every hypothesis is not diagnostic, and the leading
hypothesis is the least contradicted, not the most supported. Ratings follow
from predictions, never from a model. See [research.md](research.md) R2-R8.

## Roadmap

What has been built so far. The forward-looking backlog, with task ids, is in
[roadmap.md](roadmap.md).

- **V1 (done):** store, hashing, retcon diff, provenance clusters,
  validation, scoring, hypotheses, financial check, Wayback and contributor
  ingesters, Claude decomposition and reading, synthetic STEG case.
- **V2 (done):** `EvidenceStore` interface with PostgreSQL + pgvector
  (append-only documents table); PDF text layer with Tesseract `ara+fra` OCR
  fallback (retcons on OCR text need human review); hybrid retrieval (BM25 /
  tsvector + vectors, reciprocal rank fusion, source-kind and date filters);
  temporal validation; Arabic/French name matching (people are proposed for
  review, never merged); `Params` + calibration harness (accuracy, Brier,
  threshold sweep); procurement red-flag screening.
- **V3 (first version done, see [agent.md](agent.md)):** investigator agent
  on the Claude tool runner with fact-check and investigation modes, enforced
  challenge phase, budgets, Wayback / live / World Bank connectors, web search
  for discovery, public-reply policy.
- **V3.1 (done):** team mode with parallel source specialists (official,
  funders/audit, web news, social, public Telegram) proposing evidence and a
  reviewer agent accepting or disputing it and requesting further collection;
  legal safeguards in code (intake policy gate, data minimisation,
  hash-chained ledger, publication gate with right of reply), company-level
  red flags, French/English focus. See [legal.md](legal.md).
- **V3.2 (done):** phased workflow: planner with code-enforced coverage,
  tasks with outcomes (absence as evidence), leads board, automatic challenge
  tasks, stopping rules, Markdown case file, PoC mode.
- **A1-A4 (done):** hexagonal layout, dependency-rule test, tests by layer,
  CI (see [Code structure](#code-structure)).
- **Reasoning, research R2-R5, R7, R8 (done):** interest of the source,
  expected records and scored absence, mandatory innocent explanations,
  competing hypotheses, sensitivity, likelihood and confidence
  (see [Judgment](#judgment)).
  Next: see [roadmap.md](roadmap.md). Earlier notes: retcon and stance monitors, triage queue, access-to-information
  request tracking, RFC 3161 anchoring of the ledger, Sentinel-2 and
  night-lights tools.
- **V4:** relationship graph for reviewers (company, owner, signatory) behind
  human review and right of reply; reviewer UI; report generator; public API
  so others can replicate a verdict.

## Not verified yet

- The live paths (`--live`, `investigate`) have only run against scripted
  stand-ins (Claude SDK objects, a mock OpenAI-compatible server); the first
  real run needs a model API key or a local model server.
- JORT, TUNEPS, RNE, Wayback, World Bank and Telegram were unreachable from the build
  environment, so the connectors are tested against mocked responses only.
- The embedder is a character n-gram baseline; a neural multilingual embedder
  should replace it once chosen.
