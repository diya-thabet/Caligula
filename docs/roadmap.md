# Roadmap: from PoC to investigation machine

What Caligula needs to be a real investigation tool and to beat general
assistants such as Grok on X. Grok answers fast from model memory plus a live
search, and nothing it says is checked against its sources. Caligula wins by
being **verifiably right**: every fact traced to a stored, hashed source,
checked **as it is collected**, corroborated independently, and replayable.
Then it closes the speed gap by reusing facts it has already verified.

Task ids (`A1`, `B3`...) are referenced in commits and pull requests.
Research-backed proposals (`R1`…`R36`) on reasoning quality, connecting the
dots and concluding are in [research.md](research.md); the ones chosen get
scheduled here.
Priority: **P0** now, **P1** next, **P2** later.

## Phases

| Phase | Goal | Epics |
|---|---|---|
| 0 | Code that is easy to inspect and change | A |
| 1 | Nothing enters the case unverified | B |
| 2 | Investigate across entities, money and time | C |
| 3 | Measure it, and beat Grok on the same claims | D |
| 4 | Fast answers, proactive cases, real channels | E, F |

---

## A. Engineering foundation (P0)

| Id | Task | Done when |
|---|---|---|
| A1 | Hexagonal layout: `domain` (pure), `application` (use cases + ports), `adapters` (I/O, SDKs, CLI) | Layout in [architecture.md](architecture.md#code-structure); every module in its layer |
| A2 | Dependency-rule test | A test fails if `domain` imports anything outside it, or `application` imports an SDK or I/O library |
| A3 | Tests organised by layer (`tests/domain`, `tests/application`, `tests/adapters`, `tests/e2e`) | Domain tests need no fixtures beyond data |
| A4 | CI: lint (ruff), tests, Postgres service | GitHub Actions green on every push |
| A5 | Small, focused commits with task ids | See [CONTRIBUTING.md](../CONTRIBUTING.md) |
| A6 | Checkpoint and resume a workflow after each phase | A killed run resumes from the last completed round |
| A7 | Structured tracing (per agent, per tool call, tokens, cost) | Trace exported with each case |

## B. Verify on collect (P0 → P1)

Today documents are verified when evidence is *proposed* (quote, dates, hash)
and when it is *reviewed*. The goal: every document is verified **the moment
it is captured**, and agents see the verification status in every search and
read result, so weak material is flagged before anyone builds on it.

```
capture ──► verification pipeline (code, per document, in parallel) ──► VerificationRecord
            │ B1 source authenticity     │ B4 date consistency
            │ B2 archive cross-check     │ B5 origin & near-duplicates
            │ B3 file integrity          │ B6 fact extraction & corroboration
            ▼
   status: verified | unverified | conflicting | suspect  (+ reasons)
            ▼
   shown to agents; weights capped for suspect sources; conflicts become leads
```

| Id | Task | Done when |
|---|---|---|
| B0 | `Verifier` port and pipeline; `VerificationRecord` stored per document and in the ledger | Every ingest runs all verifiers; results visible in `search` / `read` |
| B1 | Source authenticity: allow-list of official domains (JORT, TUNEPS, ministries, STEG...), look-alike domain detection, redirect chain and TLS recorded, verified-account check for social | A page from `j0rt-gov.tn` is flagged `suspect` |
| B2 | Archive cross-check at ingest: for official pages, fetch the nearest archive capture automatically and diff the fields | A rewritten amount is flagged without any agent asking |
| B3 | File integrity: PDF metadata (created/modified, producer), incremental updates after signing, embedded signatures; image EXIF dates and perceptual hash against already-seen images | A recycled photo or a PDF modified after its stated date is flagged |
| B4 | Date consistency: stated date vs first archive capture vs dates in the text vs our capture | A document "published" before its first possible appearance is flagged |
| B5 | Origin tracing at ingest: extract cited links, near-duplicate detection (SimHash/MinHash) so copies cluster even without explicit citations | Five rewrites of one communiqué form one origin cluster automatically |
| B6 | Fact extraction and corroboration: atomic facts (amount, date, decree, party, relation) extracted from each document and matched against facts already stored | New document shows "3 facts corroborated by 2 independent origins, 1 conflicting with `archive-…`"; conflicts posted as leads |
| B7 | Publisher track record: corrections, retcons and conflicts per publisher over time feed source weights (after calibration, D3) | Weight changes are logged and explainable |
| B8 | Scoring uses verification: `suspect` documents cannot support a claim alone; `conflicting` facts lower confidence | Covered by scoring tests |

## C. Investigation capability (P1)

| Id | Task | Done when |
|---|---|---|
| C1 | Fact graph: entities (company, person-in-role, body, contract, decree, project) and relations with provenance per edge | Agents query "other contracts signed by the same authority for this supplier" |
| C2 | Persistent entity registry with alias resolution (French/English/Arabic spellings), human confirmation for people | One company id across all cases and sources |
| C3 | Timeline engine: extract dated events, order them, detect impossible sequences (award before tender, payment before contract) | Timeline contradictions appear as anomalies |
| C4 | Connectors: JORT index, TUNEPS awards, RNE extracts, Cour des comptes reports, EU TED, OpenSanctions (sanctions/PEP), OpenCorporates, INS statistics, news RSS (FR/EN), X official API | Each behind a port with contract tests and recorded fixtures |
| C5 | Numeric tools: currency conversion with historical rates, inflation adjustment of benchmarks, Benford and outlier tests on bulk award data | Financial check compares like with like |
| C6 | OSINT tools: Sentinel-2 before/after, night-lights time series | Tool returns a stored, hashed analysis document |
| C7 | Monitors and triage queue: red-flag screening, retcon monitor, stance monitor open cases | Scheduled runs create triaged cases |
| C8 | Stance-shift claim type (original Caligula idea) | A reversed or deleted statement is detected and fact-checked |
| C9 | Cross-case memory: new claims linked to verified facts and past cases | A new claim reuses evidence from an old case, re-verified |

## D. Quality and evaluation (P1)

| Id | Task | Done when |
|---|---|---|
| D1 | Evaluation set: labelled claims (FR/EN) with gold verdicts and gold evidence | 50+ claims, versioned |
| D2 | Metrics: verdict accuracy, evidence precision/recall, citation validity, time and cost per case | Report per run |
| D3 | Calibrate weights and thresholds on D1 (harness exists) | Brier score tracked |
| D4 | Benchmark against Grok on the same claims | Side-by-side table: accuracy, sources, verifiability, latency |
| D5 | Independent double review with adjudication of disagreements | Disagreement rate reported |
| D6 | Red-team suite: planted fakes, prompt injection in documents, forwarded-leak chains | Robustness score per release |

## E. Speed and scale (P2)

| Id | Task | Done when |
|---|---|---|
| E1 | Verified fact base: fact-checks first answer from facts already verified (seconds), then refresh in the background | Median fact-check on a known topic under 30 s |
| E2 | Job queue and workers for rounds and verification | Many cases in parallel |
| E3 | Prompt caching and model routing per task (planner vs readers) | Cost per case tracked and reduced |

## F. Channels and review (P2)

| Id | Task | Done when |
|---|---|---|
| F1 | Web form + case page | A claim can be submitted and followed |
| F2 | Reviewer UI: evidence board, accept/dispute, publication gate | Human review without the CLI |
| F3 | WhatsApp intake for contributors (hash on receipt, metadata split) | Uploads land in the store with custody records |
| F4 | X bot through the official API | Replies follow the public-reply policy |

## R. Reasoning quality (from [research.md](research.md))

| Id | Task | Status |
|---|---|---|
| R7 | Interest of the source: parties, bearing of each sub-claim, self-serving and against-interest weights | Done |
| R5 | Expected records per sub-claim; searches planned; absence scored by register completeness | Done |
| R4 | Mandatory innocent explanations per claim type, planned tests, verdict cap when one fits | Done |
| R2 | Competing hypotheses matrix computed from predictions; diagnostic evidence; untested apart | Done |
| R3 | Sensitivity: what the conclusion depends on | Done |
| R8 | Likelihood (estimative words) and confidence (with reasons) reported separately | Done |
| R21, R23 | Case file in the analytic format; sentence-level citation check | Next |
| R10, R11, R13 | Entities (FollowTheMoney), cross-referencing, timeline anomalies | Later, with C1-C3 |

## Suggested order

A1 → A2 → A3 → A4 (this refactor), then B0 → B2 → B5 → B4 → B6 → B1 → B3 → B8,
then D1/D2 (to measure what B changed), then C1 → C2 → C3, then D4.
