Tunisia Corruption/Mismanagement Investigation Agent - Technical Draft (Updated Aug 2026)
==================================================================================
Based on prior architecture (RAG+X) but repurposed for investigative chaining
for corruption/mismanagement in Tunisia. Focus: STEG case as reference scenario.

CORE PRINCIPLE (preserved)
---------------------------
Never ask the LLM to know whether a claim is true. Ask it to determine what
evidence would establish whether the claim is true, retrieve that evidence,
compare competing evidence, detect retconning, and construct a provenance-backed
conclusion.

Code = bookkeeping / verification / math. LLM = investigator / planner.

==================================================================================
1. PROBLEM SHIFT: Trivial Fact vs Investigative Allegation
==================================================================================

Old (trivial): "STEG cut power in Nabeul on 2026-07-21" -> direct lookup in
STEG communique. Low value, easily retconned.

New (investigative): Corruption/mismanagement allegations are MULTI-HOP, have no
admitting primary source, and require linking pertinence across sources.

Example allegation (STEG scenario):
"State-funded STEG infrastructure expansion project (funded X TND) was awarded
to contractor Z via bypassed TUNEPS tender through intermediary W linked to
official V, with inflated tariff vs market, and no real-world capacity added
despite funds disbursed - funds misappropriated."

This decomposes to:
C1: STEG experienced outage on 2026-07-21 (event)
C2: Production deficiency is cause (not consumption surge)
C3: State-funded expansion project existed, funded with amount X, initiated at date D
C4: No real-world change since initiation (no capacity added)
C5: Contractor Z was paid amount Y, procedure bypassed competitive tender
C6: Amount Y is inflated vs market benchmark
C7: Link W between contractor Z and official V who signed/awarded
C8: Causal inference: discrepancy + link + lack of output => high suspicion of corruption

Different parts have different truth values (prj: causal C8 may be unsubstantiated
even if C1-C7 supported). System must score each separately.

==================================================================================
2. ARCHITECTURE OVERVIEW (adapted from prior Spring Boot/Python/pgvector/Kafka/LangGraph)
==================================================================================

                         ┌──────────────┐
                         │  Frontend /  │
                         │  WA Bot      │
                         └──────┬───────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Investigation   │
                       │ Case API        │  Spring Boot
                       └────────┬────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Agent Orchestr. │
                       │   LangGraph     │  Python - hypothesis-driven loop
                       └────────┬────────┘
                                │
              ┌─────────────────┼──────────────────┐
              ▼                 ▼                  ▼
       Claim Analyzer    Hypothesis Generator  Entity Agent
       (decomposition)    (H1/H2/H3)          (resolution)
              │                 │                  │
              └─────────────────┼──────────────────┘
                                ▼
                       ┌─────────────────┐
                       │ Retrieval Layer │  Specialists (parallel)
                       │                 │
                       │  Official curr. │-> JORT / TUNEPS / STEG site (UNTRUSTED)
                       │  Immutable Arch.│-> Wayback / archive.is / Common Crawl (TRUSTED ANCHOR)
                       │  Foreign Mirror │-> World Bank Projects / EU TED / UN Comtrade (by exporter)
                       │  Contributor    │-> WA upload -> MinIO + SHA256 (TRUSTED GROUND TRUTH)
                       │  OSINT Sensor   │-> Sentinel-2 / NASA Black Marble / weather
                       │  Audit          │-> Cour des comptes / EBRD / IMF Art IV
                       └────────┬────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Evidence Store  │
                       │ PostgreSQL      │
                       │ + pgvector      │
                       │ + graph tables  │
                       │ + version hist. │
                       └────────┬────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Reranker +      │
                       │ Provenance      │  Collapses fake 5-source consensus
                       └────────┬────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Falsification   │
                       │ Evaluator       │  Tests H1 vs H2 vs H3
                       └────────┬────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Financial Anomaly│  Deterministic math: allocated - proven spend
                       │ Detector        │
                       └────────┬────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Suspect Ranker  │  Graph traversal: Project -> Company -> Owner -> Official
                       └────────┬────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Report Generator│  Structured verdict + confidence + missing evidence
                       └─────────────────┘

==================================================================================
3. CLAIM MODEL (for corruption)
==================================================================================

Don't start with user question -> embedding. Start with structured allegation:

{
  "claim": "State-funded STEG expansion project funds misappropriated",
  "subject": "STEG / Ministry of Energy",
  "predicate": "misappropriated / bypassed tender",
  "object": "infrastructure expansion project",
  "beneficiary": "Contractor Z",
  "intermediary": "W",
  "official": "V",
  "amount_claimed": "X TND",
  "time_range": ["project_initiation", "2026-07-21"],
  "location": "Tunisia",
  "claim_type": "corruption_procurement",
  "hypotheses": ["H1 production deficiency", "H2 consumption surge", "H3 corruption"]
}

Decomposition agent (first LLM call, not answering) produces:

{
  "claims": [
    {"id": "C1", "statement": "Outage occurred 2026-07-21 6000MW", "entities": ["STEG"], "time_range": ["2026-07-21"], "verification_questions": ["Was outage documented by independent source?"]},
    {"id": "C2", "statement": "Consumption did not surge vs 2025", "verification_questions": ["What was 2025 vs 2026 peak MW from INS/STEG reports?"]},
    {"id": "C3", "statement": "Expansion project funded by state exists", "verification_questions": ["Is there JORT/TUNEPS record of award? Amount? Date?"]},
    {"id": "C4", "statement": "No capacity added since initiation", "verification_questions": ["Progress reports? Satellite? Field photo?"]},
    {"id": "C5", "statement": "Award bypassed competitive tender", "verification_questions": ["Was tender published in TUNEPS before JORT award?"]},
    {"id": "C6", "statement": "Price inflated vs market", "verification_questions": ["Market benchmark for same works?"]},
    {"id": "C7", "statement": "Link W between Z and V exists", "verification_questions": ["RNE ownership? Signature? Kinship/board?"]},
    {"id": "C8", "statement": "Causal: funds misappropriated", "verification_questions": ["Does financial discrepancy + link support causal? What exonerating procedure exists?"]}
  ]
}

Each C has different verification source set. System investigates each independently.

==================================================================================
4. RETRIEVAL: MULTI-SOURCE WITH ANTI-RETCON DESIGN
==================================================================================

Prior trap: rely solely on vector search over current official site. Corrupt official
can retcon PDF after fact.

New retrieval specialists (parallel):

   Official Current (UNTRUSTED)      Immutable Anchor (TRUSTED)      Foreign Mirror (TRUSTED)
   ---------------------------       ---------------------------     ---------------------------
   JORT live PDF                    Wayback snapshot of same JORT    World Bank disbursement
   TUNEPS live award                 Common Crawl of TUNEPS          EU TED (if co-funded)
   STEG communique live             archive.is copy                 UN Comtrade exporter data
                                                               (mirrors import of turbines)

   Contributor Pool (TRUSTED)        OSINT (TRUSTED)                 Audit (TRUSTED)
   ---------------------------       ---------------------------     ---------------------------
   WA upload: field photo           Sentinel-2 imagery              Cour des comptes PDF
   leaked invoice PDF               NASA night lights               EBRD/IMF reports
   payslip / delivery log           weather API (falsify excuse)    (distributed, can't silently edit)

Retrieval modes per claim (avoid semantic trap "resigned vs denies resignation"):
 - lexical/BM25 (exact decree number)
 - semantic/vector (pgvector)
 - entity search (Company Z aliases)
 - phrase + date filtering + domain filtering
 - URL/citation traversal

Every document stored with:
  hash = SHA256(raw_bytes)
  published_at (from doc)
  first_seen_at (ingestion time)
  last_seen_at
  version_history = [{hash, seen_at, url}]
If current hash != archived hash -> flag retcon_detected automatically.
Contributor upload immediately hashed + pinned to MinIO + logged first_seen; later
official "updated PDF" cannot overwrite contributor version.

Scoring: source_quality weight is INVERSE to mutability.
  foreign mirror + archived + anchored contributor photo > current ministry PDF

==================================================================================
5. RERANKING + PROVENANCE (collapsing fake consensus)
==================================================================================

300 candidates -> reranker before LLM.

score =
    0.25 * semantic_relevance
  + 0.15 * claim_coverage
  + 0.25 * source_quality (mutability-inverse + authority: Cour des comptes > FB)
  + 0.15 * temporal_relevance (published_at vs event_time)
  + 0.10 * entity_match
  + 0.10 * independence

Provenance graph (not pile of docs):
  Source
   ├── authored_by
   ├── published_by
   ├── cites -> Source D
   ├── version_of -> prior hash
   └── derived_from

Critical: 5 articles saying same thing but all cite single leaked JORT -> collapse to
  Independent evidence clusters = 1, not 5 confirmations.
System collapses citation chain: A->B->C->D->E into one cluster before confidence.

==================================================================================
6. EVIDENCE GRAPH FOR CORRUPTION (pertinence linking)
==================================================================================

                     ALLEGATION (C8)
                       │
          ┌────────────┼────────────┬──────────────┐
          ▼            ▼            ▼              ▼
      supports     contradicts   qualifies     implicates
          │            │            │              │
          ▼            ▼            ▼              ▼
     JORT award   TUNEPS gap   Audit: non-    Entity graph:
     (winner,     (no tender   conforme       Company Z --owned_by--> W --related_to--> V
      tariff)      found)                     Project --awarded_to--> Z
          │                                   V --signed--> JORT
          ├── cites -> Contract PDF
          └── version_of -> archived v1 (tariff 120M vs retconned 80M)

Example STEG chain:
C5 supports: JORT award states winner Z at 80M (current)
   but contradicts: Wayback v1 states 120M + TUNEPS shows no pre-publication
   -> retcon flag + procedural bypass evidence

C6: World Bank disbursement 110M vs JORT 80M (current) vs contributor invoice 30M
    vs market benchmark 60M -> discrepancy = 50M unexplained -> anomaly

C7: RNE: Z gerant = W ; News: W board with V (entity resolution handles Arabic/French aliases:
      W / و / Officiel V / V. family name variations)

C4: Satellite: no construction + contributor photo geotagged 2026-08-10 empty lot

==================================================================================
7. ITERATIVE INVESTIGATION LOOP (agentic, not RAG)
==================================================================================

Naive RAG: query -> retrieve 10 -> LLM -> answer (one shot)

Investigator:
  query
   ↓
  retrieve (parallel specialists)
   ↓
  reason (LLM)
   ↓
  identify missing evidence / hypothesis to falsify
   ↓
  generate new query
   ↓
  retrieve
   ↓
  inspect source + version history
   ↓
  follow citation
   ↓
  compare evidence (support vs contradict)
   ↓
  detect retcon (hash mismatch)
   ↓
  search again
   ↓
  falsify H2, strengthen H3
   ↓
  reason
   ↓
  answer (structured)

STEG walkthrough implemented as hypothesis testing:

Step1: Event ingestion -> Case created
Step2: Generate H1 deficiency / H2 consumption surge / H3 corruption
Step3: Test H2: Search INS 2025 vs 2026 peak MW -> result: no variance -> H2 FALSIFIED (edge weight -)
Step4: H2 falsified -> generate query: "STEG expansion project funded by state"
Step5: Find project doc (JORT) -> Test H3 sub-claim C4: Search progress/satellite/contributor -> no output -> H3 weight +
Step6: Financial forensics -> extract allocated (JORT v1 120M) vs disbursed (WorldBank 110M) vs proven spend (market 60M) -> discrepancy 50M -> anomaly flagged (deterministic)
Step7: Only after anomaly -> Entity tracing: RNE + JORT signatures -> rank suspects
Step8: Challenge phase: Search exonerating evidence: "emergency procedure decree?" If not found, keep suspicion; if found, lower confidence.

Tools exposed to LLM (investigator chooses):
  search_news(query, date_range)
  search_tunisia_official(query, date_range)  // JORT/TUNEPS live
  search_archived(query, date_range)          // Wayback
  search_foreign_mirror(query)                // WorldBank/UN Comtrade/TED
  search_contributor_evidence(claim_id)
  search_entity(entity) + get_timeline(entity, start, end)
  get_document(url) + get_source_metadata(url) + get_citations(url) + get_version_history(url)
  get_satellite_comparison(lat, lon, date_before, date_after)
  compare_sources(source_a, source_b)  // hash + amount + date diff
  find_contradictions(claim)

Next search generated from prior evidence gap, not pre-planned.

==================================================================================
8. CHALLENGE HYPOTHESIS PHASE (anti-confirmation bias)
==================================================================================

Phase1: Find supporting evidence for H3
Phase2: Find contradicting evidence (emergency decree, force majeure, market price spike)
Phase3: Find primary sources (archived JORT v1, WorldBank mirror, anchored photo)
Phase4: Resolve contradictions (is retconned 80M credible vs 120M archived + 110M disbursed?)
Phase5: Determine confidence

Without Phase2, system is propaganda tool.

==================================================================================
9. FINANCIAL ANOMALY DETECTOR (deterministic, not LLM)
==================================================================================

LLM extracts amounts (with citation), code computes:

allocated = from JORT v1 (archived, trusted) = 120M
disbursed = from WorldBank mirror = 110M
proven_spend = market_benchmark*quantity + sum(contributor invoices if verified)
discrepancy = allocated - proven_spend

IF discrepancy > 20% AND independent clusters >=2 supporting anomaly AND no exonerating primary doc
THEN flag high_suspicion

Market benchmark from UN Comtrade exporter prices + prior TUNEPS awards for similar works.

==================================================================================
10. SUSPECT RANKER (after anomaly, not before)
==================================================================================

Graph traversal:
Project --awarded_to--> Company Z --owned_by--> Person W --related_to--> Official V
                    --signed_by--> Official V

Score(V) = 0.4*is_signatory + 0.3*link_strength(W-V) + 0.2*repeat_pattern(V awards to Z network across N projects) + 0.1*temporal_proximity

RNE handles aliases: Arabic/French, with/without middle name, company transliterations.
No manual validator; ranking is deterministic over graph, display with provenance.

==================================================================================
11. TEMPORAL REASONING (essential for retcon detection)
==================================================================================

Every source carries:
  published_at (from doc)
  updated_at (from HTTP header / JORT version)
  event_time (when outage/project occurred)
  first_seen_at (our ingestion)
  retrieval_time

Agent understands: Article published Aug 8 cannot confirm event Aug 7 as causal if
project initiation was July 1 but JORT award dated Aug 10 (after outage) -> timeline inconsistency.

==================================================================================
12. FINAL VERDICT (structured, code-verified)
==================================================================================

LLM NOT allowed to free-text "this is corruption". Must produce:

{
  "allegation_id": "STEG-2026-07-21",
  "verdict": "high_suspicion", // supported / contradicted / partially_supported / unverified / high_suspicion
  "confidence": 0.82, // evidence-derived, not LLM arbitrary
  "by_subclaim": {
    "C1 outage": "supported",
    "C2 consumption surge": "contradicted (INS 2025 5250MW vs 2026 6000MW claimed but weather-adjusted no variance)",
    "C3 project exists": "supported (JORT v1 120M, Wayback 2026-03-01)",
    "C4 no output": "supported (satellite + contributor photo + no progress report)",
    "C5 tender bypass": "supported (TUNEPS gap + JORT award without prior publication)",
    "C6 inflated": "supported (discrepancy 50M)",
    "C7 link W-V": "partially_supported (RNE link W-Z strong, W-V kinship weak, needs more)",
    "C8 corruption causal": "high_suspicion (C1-C6 + retcon flag, but C7 weak)"
  },
  "supporting_evidence": ["JORT v1 hash abc", "Wayback snap", "WorldBank 110M", "Sentinel diff"],
  "contradicting_evidence": ["JORT v2 retconned 80M"],
  "retcon_flags": ["JORT hash changed 2026-08-05"],
  "suspects": [{"name": "V", "score": 0.82, "role": "signatory"}, {"name": "W", "score": 0.71}],
  "missing_evidence": ["contractor delivery receipts", "activity logs for V", "beneficial ownership of W offshore"],
  "provenance_graph_url": "..."
}

Code verifies: Do E1/E4 exist? Hashes match? Dates consistent? If not, reject.

Confidence derived from:
 + primary archived source exists
 + independent foreign mirror corroborates
 + ground photo corroborates
 + dates align
 + claim directly stated
 - retcon detected
 - sources derive from same origin
 - primary unavailable
 => evidence score math, not LLM 0.97 hallucination.

==================================================================================
13. SYSTEM STACK (from prior experience)
==================================================================================

Frontend: WA bot + Web (French/Arabic)
API: Spring Boot (Case/Claim/Document CRUD, hash service)
Investigator: Python + LangGraph (claim analyzer, hypothesis generator, search agent, entity agent)
Store: PostgreSQL + pgvector + graph tables (claims, documents, evidence_edges, entities, version_history)
Queue: Kafka for ingester -> store -> reranker pipeline
Storage: MinIO for PDFs/photos with SHA256
Search: BM25 (lexical) + pgvector (semantic) + entity index

Tools table above implemented as LangGraph tools with deterministic wrappers.

==================================================================================
14. BUILD ORDER (ground-up, retcon-resistant first)
==================================================================================

V1 (minimal but retcon-proof):
 Claim -> Decomposition -> Wayback+Mirror+Contributor ingesters (before live crawlers) -> Retrieve 20-50 -> Rerank -> Evidence Graph -> Falsification loop -> Citations
 No satellite, no suspect ranker. Goal: prove STEG H2 falsified + JORT retcon flagged with 2 hashes.

V2: Add financial detector + version history UI + temporal reasoning + entity resolution (Arabic/French)

V3: Full PLAN->SEARCH->READ->GAP->SEARCH AGAIN->COMPARE->CHALLENGE->VERIFY loop + satellite + provenance collapse

V4: Entity graph + suspect ranker + report generator + API for external replication

Principle: Ingest archives before live; hash everything before judging; never trust current official doc alone.

==================================================================================
END OF UPDATED DRAFT - Tunisian Investigative Agent (STEG hypothesis-driven)
==================================================================================
Core sentence to keep on diagram:
Never ask the LLM to know whether corruption occurred. Ask it to determine what evidence would establish whether funds were misappropriated, retrieve that evidence from retcon-resistant sources, compare competing evidence, detect hash/version contradictions, and construct a provenance-backed suspicion score with missing evidence pointers.

