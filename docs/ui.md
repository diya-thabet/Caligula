# Interface specification

The investigation interface for Caligula, adapted from a generic
claims/legal/financial investigation spec to what the engine actually does.
Every surface below is backed by an existing feature and an endpoint of the
HTTP API ([api.md](api.md)). Surfaces with nothing behind them yet are
listed at the end as deferred, so the interface never shows a view the engine
cannot fill.

## 1. Design principles

- **Evidence first.** No conclusion without a path to its evidence. Every
  judgment and every summary sentence cites evidence ids (E1, E2...); each id
  opens the exact quote in its stored document, or the register search that
  found nothing.
- **Code decides, models propose.** The interface shows which is which.
  Statuses, likelihoods, confidence, the ranking of explanations and what the
  verdict depends on are *computed*; agents *propose* evidence, tasks and
  suspicions, and propose only. Computed values carry a small "computed" mark
  and never an agent's name.
- **Calm authority.** Closer to a legal research tool than a chatbot: no
  emoji, illustrations or gradients; plain sentences.
- **A person decides at each checkpoint.** Legal review, plan approval, a
  suspicion that widens the scope, and sign-off are each a person's act,
  recorded with their name. Nothing is approved by default.
- **Honest uncertainty.** Likelihood and confidence are two statements
  ("very likely, moderate confidence"), always shown together, always with
  the reasons that cap the confidence. Gaps, untested explanations and
  single-origin conclusions are shown as prominently as findings.
- **Nothing publishes by itself.** Investigations and anything pointing at
  wrongdoing are held for human review and a right of reply. In PoC mode,
  every screen of the case carries the internal-document banner.

## 2. Visual identity

**Palette.** Slate neutrals, one restrained accent (muted blue) for primary
actions and for "pending" outlines. Light and dark themes are both first
class.

**Semantic colours**, reserved for status and never used decoratively:

| Meaning | Colour | Used for |
|---|---|---|
| Established | green | sub-claim `supported`; hypothesis `consistent`; suspicion `confirmed`; sentence `supported` |
| Contradicted | red | sub-claim `contradicted`; hypothesis `falsified`; suspicion `refuted`; sentence `unsupported` / `uncited` (removed) |
| Disputed | amber | sub-claim `contested` (credible evidence both ways); sentence `partial` |
| Too weak to settle | amber outline, hatched | sub-claim `partially_supported` (kept distinct from contested: a lawyer reads them differently) |
| Unknown | grey | sub-claim `unverified`; hypothesis `open`; suspicion `open`; sentence `unjudged` |
| Pending a person or the reviewer | accent outline | proposal `pending`; suspicion `awaiting_scope`; any checkpoint |

The **verdict** (`high_suspicion`, `partially_supported`, `contradicted`,
`unverified`) is shown in words on a neutral badge, not in a status colour:
"high suspicion" must never read as a green "proven" or a red "guilty".
**Confidence** (low / moderate / high) is a three-step neutral meter, not red
to green.

**Typography.** IBM Plex Sans for the interface, IBM Plex Sans Arabic for
Arabic document text (right to left), IBM Plex Mono for case ids, evidence
ids, document ids, hashes, register queries and decree or market numbers.
Tabular numerals wherever amounts appear; amounts in TND with thin-space
thousands separators, as in the sources.

**Density.** Medium-high, thin borders, 6 px radius, no heavy shadows.

**Icons.** One line set (Lucide). One icon per source kind, the same
everywhere a source is cited, with its reliability tier beside it:

| Source kind | Reliability tier (shown with the icon) | Weight |
|---|---|---|
| `audit` | independent audit | 0.85 |
| `foreign_mirror` | independent record (lender, foreign register) | 0.80 |
| `archive` | archived copy | 0.75 |
| `statistics` | official statistics | 0.70 |
| `osint` | measurement (satellite, sensors) | 0.70 |
| `contributor` | field contributor | 0.60 |
| `official_live` | live official page (editable by its publisher) | 0.50 |
| `news` | press | 0.35 |
| `social` | social media (unverified) | 0.15 |

Two more item icons: **absence** (a register searched, nothing found) and
**amount** (a figure in TND). A self-serving source (a party speaking in its
own favour) carries a "party" mark; an against-interest concession, a
"concession" mark.

**Language.** Interface in English and French; case content in the
language of the claim (French, English, Arabic).

## 3. Global layout

A three-pane workspace under a persistent case header.

**Case header** (`GET /cases/{id}`):

- case id (mono), the claim as title, **status**, mode (fact-check or
  investigation), claim type, parties with their role (accused, complainant);
- the **assessment**: verdict · likelihood in words · confidence, marked
  "so far" while the case runs and "final" once it stops;
- rounds, tool calls, last activity, stop reason once stopped;
- run controls (pause, resume, stop) while running;
- the PoC banner on every page of a PoC case;
- sign-off state: draft, or approved by a named person at a time.

There is no assignee, priority or jurisdiction field: the engine has none
(jurisdiction is Tunisia by design). The header shows who opened the case.

**Left rail.** The case list (filter by status and by what waits for me),
then, inside a case:

| Section | What it shows | Endpoint |
|---|---|---|
| Overview | the judgment part of the case file: bottom line, key judgments, alternatives, key assumptions, dependencies, gaps, indicators | `/report`, `/claims` |
| Plan | the plan card | `/plan` |
| Activity | the live step tracker | `/events`, `/events/stream` |
| Claims | the claims board and claim cards | `/claims` |
| Hypotheses | competing explanations and the ACH matrix | `/claims` |
| Evidence | every item by evidence id, and every proposal | `/evidence` |
| Documents | documents with their chain of custody | `/documents` |
| Timeline | dated events, rewritten records flagged | `/timeline` |
| Suspicions | what the reviewer suspected and how it was tested | `/suspicions` |
| Summary | the reviewer's summary and its sentence check | `/summary` |
| Case file | the full case file, for review and sign-off | `/report` |
| Audit log | the ledger | `/audit` |

**Centre.** The selected section.

**Right panel.** Context for whatever is selected: a document with the
cited quote highlighted, an absence (register, query, window, capture), an
amount with the financial check, a hypothesis, a suspicion. It can be
collapsed.

## 4. Components

**Plan card** (status `awaiting_plan_approval`). Tasks grouped by
specialist (official, funders_audit, web_news, social, telegram), each with
its objective, purpose (support, challenge, explore), sub-claims, queries,
URLs, and the expected record it searches for (`C5.E1`). Budgets per
specialist. The investigator can edit, remove or add tasks, then approve.
There is no reordering: specialists work in parallel, so order means
nothing. After an edit, **what code put back** is listed (from
`plan.fixes`): for example "added a challenge task for C9 (innocent
explanation emergency)". The guarantees cannot be edited away, and the
interface says why.

**Live step tracker** (Activity). Events grouped by round, then by agent
(the five specialists and the reviewer), then tool calls in order: tool,
arguments (query, document, quote), outcome. Phases (collect, review,
citations, verdict) mark the round's progress. A tool call **refused by
code** (a quote not found in the document, "search harder before 'not
found'", an editable page used as proof of an earlier date) is shown as the
engine working, in neutral grey with the reason, not as a failure. Task
outcomes: found, partial, not_found (information, not failure), blocked.

**Claim cards** (one per sub-claim):

- statement, core badge, and bearing: *against* the accused or *for* them.
  A card *for* them tests an innocent explanation; when code added it, it
  says "added by code";
- status colour, likelihood in words, confidence meter and the reasons that
  cap it;
- three columns of evidence chips: for, against, qualifying, with the number
  of independent origins under each (documents sharing an origin count once);
- expected records: what should exist in which register, whether it was
  searched, whether its absence counted;
- "never challenged" when nobody has looked for evidence against it.

**Evidence chips** (`[E13]`). They are inline in summaries, judgments and
cards, with the source icon and reliability tier. A click opens the right
panel on the exact quote, highlighted in the stored document text; for an
absence, the register search; for an amount, the figure and the financial
check. A disputed or withdrawn item never appears as a chip.

**How this was concluded** (an expander on every judgment). It is written
from computed values only:

- the items for and against, with their weights;
- the independent origins;
- the interest of each publisher;
- any single origin the conclusion depends on ("without `benchmark`, the
  verdict drops to partly supported").

Percentages appear here, not in the headline.

**Checkpoints.** These are blocking cards, each routed to a role, saying
what happens, why and with what data:

| Checkpoint | Role | Actions | Endpoint |
|---|---|---|---|
| Legal review of the claim | lawyer | Approve (with a note) | `POST /legal-approval` |
| Plan approval | investigator | Edit, Approve | `PUT /plan`, `POST /plan/approve` |
| Wider scope (a suspicion naming new people or companies) | lawyer | Approve, Reject (with a note) | `POST /suspicions/{sid}/scope` |
| Sign-off of the case file | editor | Sign off (with a note) | `POST /sign-off` |

There is no checkpoint for paid data providers: the engine uses public
sources only.

**Alerts** are shown where they apply and gathered in the Overview:

- **record rewritten**: a document that changed between versions, with what
  changed (`120 000 000 → 80 000 000 TND`), and a warning when the text came
  from OCR;
- **financial anomaly**: the award against the benchmark, with the gap;
- **contested**: credible evidence on both sides;
- **absence counted**: a register searched properly and found empty,
  weighted by the register's completeness;
- **not searched yet**: an expected record nobody looked for;
- **single origin**: a conclusion one source could overturn;
- **innocent explanation open, or fitting the evidence**;
- **proposals rejected by validation** (count): quotes not found, dates
  incompatible.

## 5. Views

**Claims board.** All sub-claims as a table or as columns by status.
Filters: core only, bearing (against, for), confidence, has evidence, never
challenged.

**Hypotheses.** Each explanation (allegation, innocent, alternative) with
its status and the evidence against it, least contradicted first, untested
ones apart. The ACH matrix: rows are independent origins, columns are
hypotheses, cells C / I / –. Diagnostic rows (evidence that tells
explanations apart) come first. Explanations ruled out are listed with the
reason given.

**Suspicions.** Each suspicion the reviewer raised: statement, round, the
sub-claim that tests it, what would confirm and refute it, its two tasks,
status, and people or companies outside the case (with the scope
checkpoint).

**Timeline.** Documents used, events the claim dates, and rewritten records.
It flags a document first seen long after the date it claims to predate,
and a record whose later version differs.

**Document viewer.** Stored text (PDF text or OCR, marked as such) with the
cited quotes highlighted and their evidence ids. Arabic is shown right to
left. It also shows the document's chain of custody (section 6). For a
document with several versions (same canonical URL: a live page and its
archive), versions are compared side by side with the changed fields marked.

**Summary.** The reviewer's summary as published after the citation check,
then the sentence table: each sentence, what it cites, its status and why.
Removed sentences are listed there, never silently dropped.

**Case file.** The full case file in its analytic order (bottom line first,
annexes after), rendered from Markdown, with evidence ids as chips. It is the
object of sign-off.

## 6. Trust and compliance surfaces

- **Audit log.** The case's ledger:
  - every action (captures, proposals, reviews, tasks, suspicions, plan and
    scope decisions, stops, the citation check, sign-off) with who, when and
    its hash;
  - filters by action and actor;
  - an integrity badge ("chain intact", or "broken at entry N");
  - export as JSON.
- **Chain of custody**, per document: raw and text SHA-256, when and by whom
  it was captured, the URL and canonical URL, the extraction method (plain,
  PDF text, OCR), whether the stored bytes still match their hash, what it
  cites or derives from, and the evidence items that use it.
- **Source reliability.** The tier and icon from section 2, wherever a source
  appears.
- **Personal data.** The engine does not name individuals in its outputs, and
  identifiers in press, social and contributor documents are masked when
  stored (emails, phone numbers, national ids). Because the unmasked data is
  never kept, there is no "reveal" control. Suspicions that bring in people
  go through the scope checkpoint.
- **PoC banner** on every page of a case run without legal review.
- **History.** How the case evolved, round by round: new evidence,
  suspicions raised and resolved, verdict and confidence after each round,
  and the stop reason.

## 7. System states

| Case status | What the interface shows |
|---|---|
| `preparing` | a progress line from the events (intake, decomposition, planning) |
| `refused` | the policy's reasons; nothing else is possible |
| `awaiting_legal_review` | the legal checkpoint, for a lawyer |
| `awaiting_plan_approval` | the plan card |
| `running` | the running indicator in the header, pause and stop, the live tracker; the assessment marked "so far" |
| `paused` | agents hold at their next tool call; resume or stop |
| `in_review` | the stop reason in words ("settled", "exhausted", "stopped by the investigator"...), the sign-off checkpoint |
| `approved` | approved by whom, when |
| `failed` | the error as recorded; open a new case to retry |

- **Needs attention.** A queue across cases (`GET /approvals`): each item
  says what waits (legal review, plan approval, scope, sign-off) and for
  which role.
- **Empty state.** "Describe the claim to investigate", with the mode
  (fact-check or investigation) and the PoC switch. When the server has no
  model (`can_investigate: false`), new cases are disabled with that reason,
  and replayed cases stay open for review.
- **Errors** say what happened and what can be done:
  - a checkpoint in the wrong state: the server's message ("case is running,
    not in_review");
  - a lost live connection: it reconnects and resumes after the last event
    seen;
  - an agent's connector failure: shown in the tracker as the agent saw it.

## 8. Case file and sign-off

The case file is built by code from the evidence, not written by an agent,
so it is **not edited by hand**: an edit would break the trace from each
line to its evidence. The only prose is the reviewer's summary, which is
checked sentence by sentence. The editor reviews the case file and signs it
off with a note. That records their name, the time and the ledger head, so
any later change to the record is detectable.

- **Draft or approved** is shown on every page of the case.
- **Export:** Markdown now, evidence ids preserved; PDF later.
- **Public reply:** only fact-checks that point at no wrongdoing get a
  short reply with sources. Everything else gets the holding message.

## 9. Features and their surfaces

| Existing feature | Surface | Interaction |
|---|---|---|
| Intake classification and legal policy | case creation, legal checkpoint | refused with reasons, or held for a lawyer |
| Decomposition into sub-claims and hypotheses; mandatory innocent explanations | claims board, claim cards, hypotheses | read; code-added tests marked |
| Planner and plan normalisation | plan card | edit, approve; code's additions explained |
| Specialists and reviewer (team loop) | live step tracker | watch; pause, resume, stop |
| Validation of quotes, dates, bytes | step tracker (refusals), evidence | read |
| Review of proposals | evidence (proposal and review note) | read |
| Evidence ids | evidence chips everywhere | open the quote |
| Source interest (self-serving, against interest) | evidence chip marks | read |
| Expected records and scored absence | claim cards, absence alerts, right panel | read |
| Retcon detection (rewritten records) | alerts, timeline, document version compare | compare versions |
| Financial check | alert on the financial sub-claim, right panel | read |
| Origin clusters (echo chambers count once) | "independent origins" on claim cards | read |
| ACH matrix | hypotheses | read |
| Sensitivity (what the conclusion depends on) | "How this was concluded", overview | read |
| Likelihood and confidence per judgment and overall | header, claim cards | read, with reasons |
| Suspicions (tested both ways) and scope checks | suspicions, scope checkpoint | lawyer approves or rejects |
| Stop rules and round history | header, history | read |
| Analytic case file | overview, case file | sign off |
| Sentence-level citation check | summary | read which sentences were removed and why |
| Hash-chained ledger | audit log | filter, verify, export |
| Chain of custody | document viewer | read |
| Privacy masking | document viewer (masked fields) | read |
| PoC mode | banner | read |
| Red-flag screening of procurement awards | not in the interface yet (a CLI command) | see below |

## 10. Deferred, and what the API still needs

These are deferred because the engine has nothing behind them yet:

- **entity graph** and **money-flow view**: wait for entities and
  cross-referencing (R10, R11);
- **triage queue from red-flag screening**: needs an API endpoint over
  `caligula screen`;
- **roles and sign-in**: F0b. Until then the interface asks for the user's
  name once, keeps it in the browser and sends it with each act.

Small backend additions the interface needs, to make as it is built:

- rounds and their summaries in the case views (for History);
- document versions by canonical URL, with the changed fields (for the
  compare view);
- evidence ids rendered as links in the Markdown case file;
- serving the built interface from `caligula serve` (same origin, no CORS
  in production).

## 11. Build

**Status:** every surface in sections 3 to 8 is built, except the entity graph
and money-flow views (deferred, section 10). The four API additions in
section 10 are done: rounds in the history view, document versions, evidence
ids as chips in the case file, and serving the interface from `caligula
serve`.

```bash
cd web && npm ci && npm run build            # then: caligula serve --replay fixtures/steg_synthetic
npm run dev                                  # development, with the API on 127.0.0.1:8000
npm test                                     # the interface's tests (vitest)
```

The interface's tests run on `web/src/test/steg.json`, taken from the real
API by `tests/adapters/test_web_fixture.py`. When a view changes shape that
Python test fails first; regenerate with `UPDATE_GOLDEN=1 pytest
tests/adapters/test_web_fixture.py`, then run `npm test`.

- **Stack:** React with TypeScript, built with Vite, in `web/`.
  - Server data via TanStack Query, the live stream via `EventSource`.
  - Lucide icons, IBM Plex fonts (bundled, no external requests).
  - CSS variables for the two themes.
- **Development:** `caligula serve --replay fixtures/steg_synthetic` and
  `npm run dev` (the Vite dev server forwards `/api` to port 8000). The
  synthetic STEG case fills every surface without a model.
- **Order:**
  1. shell and case header;
  2. overview and claims;
  3. evidence chips and the document viewer;
  4. plan card and checkpoints;
  5. step tracker;
  6. hypotheses, suspicions, timeline;
  7. summary, case file and sign-off;
  8. audit log.
