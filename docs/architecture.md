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
3. **Claude as the LLM**, called through the official SDK with structured
   outputs (`client.beta.messages.parse`) and server-side refusal fallbacks
   (`fallbacks="default"`). No LangGraph in V1: the loop is short and explicit.
   V3's iterative search loop will use the SDK's tool runner.
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
   thresholds are priors in `scoring.py`. Before any score is published they
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

## Pipeline (V1)

```
case.json + documents
      │
      ▼
EvidenceStore ── BlobStore (content-addressed, write-once, raw SHA-256)
      │           text SHA-256 over normalized text
      ▼
Allegation ── sub-claims C1..Cn, hypotheses H1..Hm with predictions
      │        (recorded, or Claude `decompose`)
      ▼
Readings ── edges {doc, sub-claim, supports|contradicts|qualifies, quote}
      │      figures {doc, allocated|disbursed|benchmark|proven_spend, amount, quote}
      │      (recorded, or Claude `read` per document)
      ▼
validate.py ── doc exists, blob hash intact, quote verbatim, amount in quote
      │         rejected items are reported, never silently dropped
      ▼
retcon.py ── versions per canonical URL, field diffs
provenance.py ── union-find over cites / derived_from / same document / same text
      ▼
scoring.py ── per sub-claim: noisy-OR over independent clusters,
      │        each cluster counted once at its best document's weight;
      │        rewritten versions penalized
      │        hypotheses: falsified if any prediction is contradicted
      │        financial: committed amount (from the attested version) vs
      │        proven spend / benchmark; flagged if > 20% with >= 2 origins
      ▼
verdict.py ── contradicted | unverified | partially_supported | high_suspicion
               confidence, missing evidence, retcon flags, rejected proposals
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

### Verdict rule

- Any core sub-claim contradicted: `contradicted`.
- All core sub-claims supported **and** a deterministic signal (financial
  anomaly or retcon): `high_suspicion`.
- Some core sub-claims supported: `partially_supported`.
- Otherwise: `unverified`.

The causal inference ("funds were misappropriated") is never a core
sub-claim; it is what the verdict is about, and it is never marked proven.

## Roadmap

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
  for discovery, public-reply policy. Next: retcon and stance monitors,
  triage queue, Sentinel-2 and night-lights tools.
- **V4:** relationship graph for reviewers (company, owner, signatory) behind
  human review and right of reply; reviewer UI; report generator; public API
  so others can replicate a verdict.

## Not verified yet

- The live paths (`--live`, `investigate`) have only run against a scripted
  stand-in for Claude; the first real run needs API credentials.
- JORT, TUNEPS, RNE, Wayback and World Bank were unreachable from the build
  environment, so the connectors are tested against mocked responses only.
- The embedder is a character n-gram baseline; a neural multilingual embedder
  should replace it once chosen.
