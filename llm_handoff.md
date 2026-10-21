# LLM Handoff — Caligula

> **Purpose**: institutional memory for the Caligula project. What exists, why it is
> shaped that way, what was decided, what broke, and what is next. A new session or a
> new agent should be able to continue from here without re-deriving any of it.
>
> **Scope note**: this file is for Caligula only. An unrelated `llm_handoff.md` exists at
> `~/Desktop/llm_handoff.md` for the Hiring Platform project; do not merge them.
>
> **Last updated**: 2026-10-07 — Phase 1 (durability) shipped and verified.

---

## 1. What this project is

Caligula is an **evidence engine for public-interest allegations**, starting with
procurement and public-funds cases in Tunisia. The design rule that governs everything:
**models propose, code decides.** A model never asserts anything that is not verified —
every quote is checked verbatim against a stored document, every amount against the quoted
text, every conclusion recomputed by domain code. Design rationale: `docs/architecture.md`,
`docs/legal.md`.

---

## 2. Environment (all of it, so a fresh session does not go looking)

| Thing | Where / value |
|---|---|
| Project root | `/home/mohamed/Desktop/data2/Caligula-claude-focused-fermat-28tudk` |
| Python venv | `.venv` (3.12 host; containers use 3.11) |
| Frontend | `web/` — React 19 + Vite 8 + TypeScript 7, Node 22 |
| Postgres | container `pgvector/pgvector:pg16`, user/pass/db = `caligula`/`caligula`/`caligula`, port 5432 |
| Test DSN | `postgresql://caligula:caligula@localhost:5432/caligula_test` |
| Persistent data | `~/Desktop/data2/caligula-docker/{pgdata,blobs,cases,out,images}` |
| Credentials | `.env` in the project root (git-ignored). **Never paste its contents into chat or docs.** |
| OCR (no sudo) | tesseract 5.3.4 extracted to `~/.local/tessroot`, wrapper at `~/.local/bin/tesseract`. Needs `export PATH="$HOME/.local/bin:$PATH"` in a fresh shell. |
| Compose | system `docker-compose` is **v1.29.2 and broken** (`KeyError: 'ContainerConfig'`). Use the v5 plugin: `/usr/libexec/docker/cli-plugins/docker-compose -f docker-compose.full.yml …` |

**Container names are namespaced** `caligula-claude-focused-fermat-28tudk_{db,api,web,search}_1`.
An unrelated stack (langfuse, grafana, loki, tempo, prometheus, …) shares this Docker
daemon — **never** `docker stop`/`rm`/`prune` anything that is not namespaced with
`28tudk`.

### Running it

```bash
cd /home/mohamed/Desktop/data2/Caligula-claude-focused-fermat-28tudk
alias dc=/usr/libexec/docker/cli-plugins/docker-compose
dc -f docker-compose.full.yml up -d          # db, api, web, search
dc -f docker-compose.full.yml logs -f api     # real-time task evolution
dc -f docker-compose.full.yml logs -f api | grep -iE 'error|429|timeout|traceback'
UI  http://127.0.0.1:8080     API http://127.0.0.1:8000/api     docs /docs
```

---

## 3. Providers (this bit us; read before testing agents)

| Provider | Status | Note |
|---|---|---|
| **NVIDIA NIM** (`nvidia/nemotron-3-ultra-550b-a55b`) | **primary**, in `.env` | Key was recovered from `~/.local/share/opencode/auth.json`. ~40 rpm free tier, very slow on big calls. |
| Fanar (QCRI) | analyst-only | Its 3 models **cannot emit function calls** (verified by probe). Structure without evidence — 0 tool calls. |
| OpenRouter | exhausted | `sk-or-v1-…`: `free_model_daily_requests {used:52, limit:50}`. `stealth/space-bunny-alpha` now 404s. |
| SearXNG | self-hosted, containerised | `searxng-settings.yml` needed (stock config 403s API clients). Upstream engines get captchas in waves, so occasional empty results are normal. |

Agent-mode knobs added to `src/caligula/adapters/cli/models.py`:
`CALIGULA_MAX_TOKENS`, `CALIGULA_HTTP_TIMEOUT`, `CALIGULA_MIN_INTERVAL` (request pacing),
plus the pre-existing `CALIGULA_MAX_TOKENS_FIELD`, `CALIGULA_OUTPUT_MODE`.

---

## 4. The data model, and the one rule behind it

Three layers with **different rules** — this distinction is the spine of the design:

```
LAYER 1 — the world (facts, append-only, IMMUTABLE)
  documents   id · canonical_url · observed_at · text · raw_sha256 · text_sha256
              MANY rows share canonical_url = versions of one logical page
              guarded by trigger documents_no_update (UPDATE/DELETE raises)
  blobs       filesystem, content-addressed by raw_sha256
  custody_records

LAYER 2 — the record of authority (hash chain, append-only)
  ledger entries  seq · at · action · actor · data · prev → prev hash, hash → next prev
                  ONE CHAIN PER CASE, 27 action types
                  entry_hash() covers [seq, at, action, actor, data, prev]
                  verify_chain() recomputes; None = intact

LAYER 3 — the reasoning (derived, recomputable, snapshotted)
  cases · case_ledger · (planned: case_attempts, case_evidence, case_documents,
                         entities, document_assessments, case_reassessments)
```

**The spine: authoritative vs derived.**
- *Immutable and authoritative*: `documents`, blobs, ledger entries.
- *Derived and recomputable*: E-id mapping, `Verdict`, ACH, likelihood, sensitivity.
- *Snapshots (jsonb)*: convenience copies — never the record.

> ### ⚠ THE TIMESTAMP TRAP (cost real debugging time)
> `Entry.at` is a **string** and is **an input to the entry hash**
> (`domain/services/ledger_chain.py:34`). If it is stored in a `timestamptz` column,
> Postgres normalises it (`T`→space, offsets folded to UTC), the re-read hash differs,
> and `verify_chain()` reports a **false tamper** on a chain nobody touched. psycopg
> also returns a `datetime` object, not the original string, compounding it.
> **`at` is stored as `text` on purpose.** A regression test
> (`test_the_hashed_timestamp_comes_back_exactly_as_written`) exists solely to hold this.

### Citations are version-bound — never "latest"
A finding points at a **specific capture** (`case_evidence.doc_id`), and all versions of
one page collapse to **one origin** (`provenance.py:41-44`, `origin_clusters` unions on
`canonical_url`). A newer version **never replaces** an older one: `retcon.py` walks
versions oldest→newest and emits a `RetconFlag` naming what changed
(`120 000 000 → 80 000 000 TND`). Only a raw-hash change is not a finding; extracted
fields (amounts, dates, decree numbers) must actually differ, and `needs_review` is set
when OCR text is involved. **The user was corrected on this point explicitly and agreed:**
"always reference the latest version" would delete the v1 quote the moment v2 landed —
exactly the retcon the engine exists to expose.

---

## 5. Phase 1 (durability) — SHIPPED and verified

Goal: **a case survives a process restart, exactly as it stood.** Delivered in three
slices, all additive, all reversible by flag.

### Slice 1 — ledger in PostgreSQL
- `schema.sql`: `case_ledger` + `case_ledger_append_only` trigger.
- `adapters/persistence/ledger_postgres.py` — `PostgresLedger` over the existing `Ledger`
  port. Reuses `entry_hash`/`verify_chain` (no second hashing implementation).
  Appends serialised with `pg_advisory_xact_lock(hashtext(case_id))` and read the chain
  tail **inside** the transaction, so 5 parallel specialists cannot fork the chain.
- `bootstrap.open_ledger_factory()` picks Postgres when `--db` is set; the factory
  **memoises per case id** (two ledgers over one chain would each number from their own list).
- New flag: `--ledger-store {auto,postgres,jsonl}`.

### Slice 2a — case snapshots (write-only)
- `schema.sql`: `cases` table (identity columns + jsonb reasoning graph + `status_history`).
- `application/cases/snapshot.py` — `CaseSnapshot`, `workspace_to_dict` / `workspace_from_dict`,
  `snapshot_of`, `as_datetime`. Pure data; the repository never sees a live `Case`.
- `adapters/persistence/cases_pg.py` — `PostgresCaseRepository` (last write wins, whole row).
- `CaseService._persist()` called at every status transition; best-effort (a store failure
  never takes an investigation down).
- New flag: `--cases-store {auto,postgres,none}`.

### Slice 2b — full-fidelity restore
- `CaseService.hydrate()` runs at startup **before** any new case is opened.
- Workspace rebuilt with **E-ids in stored order**; the verdict is **recomputed**
  (`ws.verdict()`), never trusted from jsonb — and asserted equal in tests.
- Events replayed in **chronological order** with their real timestamps, so "last
  activity" stays true instead of looking seconds old.
- `Case.restored` → mutating acts (`sign_off`, `pause`, `resume`, `stop`, `edit_plan`,
  `decide_scope`, `approve_plan`) raise `CaseError` → **409**. Nothing is lost; a future
  attempt inherits it.
- In-flight statuses (`preparing`/`running`/`paused`) restore as **`failed`** with note
  `interrupted by a restart` + a `failure` ledger entry. A half-run is not a result.
- One unreadable snapshot → that case marked failed, **startup continues**.
- `add_reviewed` is idempotent: a replay no longer collides with a restored case, and the
  fixture's recorded chain is imported once into the durable ledger.

### Verification actually run (not asserted)
- `ruff check src tests` → clean
- `pytest -q` with `CALIGULA_TEST_DSN` + OCR → **279 passed** (was 258)
- `npm run typecheck` clean, `vitest` **25/25**
- **Docker acceptance**: case listed after `restart api`, `report` byte-identical except the
  render-time `Generated …` line, `audit` → `integrity: {entries: 27, intact: true}`
- `persist-proof-1` created via API, killed mid-`preparing`, came back `failed` — by design.

### Bugs found and fixed *during* Phase 1 (all regression-tested)
1. `RejectedEvidence` is **pydantic**, not a dataclass — `_plain()` missed it.
2. `ws.trace` was not restored → `tool_calls` read 0 after restart.
3. `_status()` took **two clock readings** (history + event), so they disagreed by µs.
4. Replayed cases lost their audit chain once hydration won over replay.
5. `PostgresDocumentRepository` held one connection forever — a db restart 500'd the API
   permanently. Now self-heals (`postgres.py` `conn` property).

---

## 6. Known limitations right now

1. **Replayed cases' `case_opened` entry is ephemeral** (27 durable entries vs 28 live) —
   it lived only in a volatile in-memory ledger. Findings are unaffected.
2. **Restored cases are read-only.** A case that died at `awaiting_plan_approval` keeps that
   checkpoint but cannot be approved yet; Drop 3 (attempts) is what unblocks it.
3. `investigations` table is still only written by the CLI `run` path, never by `serve`.
4. **HTML pages are stored as raw markup** (`extraction='plain'`). Live runs captured
   541 KB of `<meta>`/ad-script boilerplate; article text is *inside* it but quote
   validation matches against the markup. This is the highest-value remaining defect.
5. NVIDIA free tier throttles: 5 parallel specialists hit 429 even with pacing.

---

## 7. Roadmap agreed with the user (not yet built)

Deliberately truncated into digestible drops; each ships and is validated alone.

| Drop | Slices | Outcome |
|---|---|---|
| **1 — durability** | 1, 2a, 2b | ✅ **done** |
| **2 — hygiene** | HTML→text extraction; `document_assessments` side table; search demotion; human-only quarantine | corpus stops accumulating parasitic data |
| **3 — lineage** | `case_attempts`; a re-run **adds to** the case and never overwrites the archive; carry-over brief; attempt history | "build a stronger case" on prior findings |
| **4 — reach** | cross-case links + entity graph; `reassess`; backfill existing ledgers | reuse across cases; evolving verdicts |

**Standing decisions taken with the user:**
- Restore fidelity: **full** (every endpoint + recomputed verdict).
- A re-run is **additive on top of** prior findings; archives are immutable.
- Only **accepted, reviewer-approved evidence** and the documents backing it carry forward.
  Rumors/proven-fraudulent material is archived for audit, labelled "previously rejected —
  not evidence", and never carried as a finding.
- **Nothing is auto-quarantined.** Agent behaviour derives signals; only a named person
  quarantines a document. Otherwise one bad model poisons the corpus forever.
- Quarantined documents stay reachable by id and stay in the audit trail — hidden, never deleted.
- Sign-off is **per attempt**; an earlier sign-off is archived with `superseded_by`.
- E-ids are **case-scoped and monotonic**, never reused → an archived report keeps its meaning.

---

## 8. Commands a fresh session will want

```bash
cd /home/mohamed/Desktop/data2/Caligula-claude-focused-fermat-28tudk
export PATH="$HOME/.local/bin:$PATH"          # tesseract, for the OCR test
export CALIGULA_TEST_DSN=postgresql://caligula:caligula@localhost:5432/caligula_test

.venv/bin/ruff check src tests
.venv/bin/python -m pytest -q                  # needs the DSN + OCR; expect 279
(cd web && npm run typecheck && npm test)

# watch a running investigation
tail -f /tmp/caligula-blind*.log
tail -f out/<case>-ledger.jsonl | python3 -c "import json,sys;[print(json.loads(l)['seq'],json.loads(l)['action']) for l in sys.stdin]"
curl -s :8000/api/cases | jq
curl -N :8000/api/cases/<id>/events/stream     # live SSE
```

## 9. Unresolved questions carried forward
- Was the entity graph (`entities`/`case_entities`/`document_entities`) wanted in Drop 4? **Not answered.**
- Backfill of `blind-olive-api-1/2/4.jsonl` + the STEG fixture into Postgres as real cases: **Drop 4, not answered.**
- A Brave API key was requested for search reliability: **not provided**; SearXNG only.