# The investigator agent

A Grok-style assistant that people can ask "is this true?", with one difference
that matters: Grok answers from what the model knows plus a live search, while
Caligula answers only from documents it has fetched, hashed and stored, and the
verdict is computed by code. Slower, but every answer can be replayed and
defended.

## Two modes, one engine

| | Fact-check | Investigation |
|---|---|---|
| Question | "Did the minister say X?" "Is the 12% figure right?" | "Were the expansion funds misused?" |
| Budget | 25 tool calls | 80 tool calls |
| Output | Short public reply with sources | Report for a human reviewer |
| Public reply | Verdict + sources + what is missing | Only "case opened, published after review" |
| Anything suggesting wrongdoing | Held for review (same as investigation) | Held for review |

## Workflow graph

The graphs below are the orchestration as implemented (`cli.py`,
`agent/team.py`, `agent/runner.py`, `agent/tools.py`). Node shapes:

| Shape | Meaning |
|---|---|
| parallelogram | one structured model call |
| double-sided box | an agent: a model-driven tool loop |
| box | deterministic code |
| diamond | a decision taken by code |
| hexagon | parallel fan-out or join |
| stadium | start or end state |
| cylinder | shared state |

### 1. End to end

```mermaid
flowchart TD
    REQ(["Claim or allegation (fr / en)"]) --> CLS[/"Intake classifier"/]
    CLS --> GATE{"Policy gate<br/>policy.decide"}
    GATE -- refuse --> REF(["Refused and logged"])
    GATE -- "legal review" --> LR{"Lawyer approved?<br/>PoC mode?"}
    LR -- "lawyer approved" --> DEC
    LR -- "PoC mode" --> POC["Ledger: poc_unreviewed<br/>case file marked internal"]
    POC --> DEC
    LR -- neither --> HALT(["Stopped until a lawyer approves"])
    GATE -- accept --> DEC[/"Decomposer<br/>sub-claims, hypotheses, core set"/]
    DEC --> MODE{"Team mode?"}
    MODE -- no --> SINGLE[["Single investigator<br/>budget 25 fact-check / 80 investigation<br/>(graph 3)"]]
    MODE -- yes --> PLAN[/"Planner<br/>entities, window, tasks, budget weights"/]
    PLAN --> NORM["normalize_plan<br/>2 kinds of source per core sub-claim<br/>budgets clamped to 5-40"]
    NORM --> ROUND[["Collection round n<br/>(graph 2)"]]
    ROUND --> STOP{"Stop rule"}
    STOP -- "continue with n + 1" --> ROUND
    STOP -- "no_open_tasks, no_progress, round_limit" --> VER
    SINGLE --> VER["Verdict<br/>code, from accepted evidence only"]
    VER --> REP["Case file out/CASE.md<br/>report.py"]
    REP --> REPLY{"Public reply policy"}
    REPLY -- "fact-check, not accusatory" --> PUB(["Short reply with sources"])
    REPLY -- "investigation or high_suspicion" --> HOLD(["Held: publication gate<br/>editor, lawyer, right of reply"])
```

### 2. One collection round (team mode)

```mermaid
flowchart TD
    START(["Round n"]) --> ACT{"Specialists with open tasks<br/>of round n or earlier?"}
    ACT -- none --> NONE(["stop: no_open_tasks"])
    ACT -- some --> FORK{{"Fan out<br/>budget: planned in round 1, half later"}}
    FORK --> PAR
    subgraph PAR["Specialists in parallel (only those with open tasks)"]
        direction LR
        OFF[["official<br/>JORT, TUNEPS,<br/>ministries, archives"]]
        FUN[["funders_audit<br/>World Bank, audits,<br/>statistics"]]
        WEB[["web_news<br/>articles"]]
        SOC[["social<br/>public posts"]]
        TG[["telegram<br/>public channels"]]
    end
    PAR <-. "store, propose, close tasks, leads" .-> WS[("Shared workspace<br/>documents, proposals, tasks, leads, ledger")]
    PAR --> JOIN{{"All specialists reported"}}
    JOIN --> CH1["Queue challenge tasks for round n+1<br/>supported and unchallenged sub-claims<br/>routed to official and web_news"]
    CH1 --> REV[["Reviewer<br/>accept or dispute each proposal<br/>request_collection: tasks for round n+1"]]
    REV <-. "decisions, new tasks" .-> WS
    REV --> CH2["Queue challenge tasks<br/>for sub-claims the review made supported"]
    CH2 --> SUM["Round summary<br/>statuses, accepted, disputed, tasks closed"]
    SUM --> RULE{"Stop rule"}
    RULE -- "no open task for rounds up to n+1" --> S1(["no_open_tasks"])
    RULE -- "2 rounds unchanged, no challenge pending" --> S2(["no_progress"])
    RULE -- "n = max_rounds" --> S3(["round_limit"])
    RULE -- otherwise --> NEXT(["Round n+1"])
```

| Stop reason | Condition (checked after the review) |
|---|---|
| `no_open_tasks` | no open task for the next round, new or carried over |
| `no_progress` | two consecutive rounds with the same sub-claim statuses and accepted count, and no challenge task pending |
| `round_limit` | `max_rounds` reached (default 3); tasks still open appear as "not run" in the case file |

### 3. Inside an agent (tool loop)

The same loop (`agent/loop.py`) runs the single investigator, each
specialist and the reviewer; only the tool set, the brief and the wrap-up
tool differ.

```mermaid
flowchart TD
    B["Brief: case, entities, your tasks, leads"] --> M[/"Claude turn"/]
    WEBS[/"web_search<br/>server tool, discovery only"/] -.-> M
    M -- "tool calls" --> G{"Metered gate<br/>agent done? budget left?"}
    G -- no --> ERR["ToolError back to the model"]
    ERR --> M
    G -- yes --> T{"Tool kind"}
    T -- "search, read, compare, assess" --> RES["Tool result"]
    T -- "fetch: URL, archive, funders, telegram" --> STORE["store_document<br/>hash, minimise personal data, ledger capture"]
    STORE --> RES
    T -- "record_evidence, record_amount" --> VAL{"Validate<br/>quote verbatim, dates, blob hash, known sub-claim"}
    VAL -- invalid --> REJ["Rejected with reason<br/>logged in the ledger"]
    REJ --> M
    VAL -- valid --> PROP["Accepted (single agent)<br/>or proposal pending (team)"]
    PROP --> M
    T -- "complete_task, post_lead, review, request_collection" --> RES
    RES --> M
    T -- "report, complete_review, finish" --> W{"Wrap-up gate"}
    W -- "open tasks, pending proposals<br/>or unchallenged sub-claims" --> ERR
    W -- ok --> DONE(["Agent done"])
    M -- "no tool call" --> END(["Turn ends; pause_turn is resumed"])
```

Wrap-up gates, each lifted only when the agent's budget is spent: `report`
(specialist) needs no open tasks, `complete_review` (reviewer) needs no
pending proposals, `finish` (single investigator) needs every supported
sub-claim challenged.

Tool sets per agent:

| Agent | Collect | Propose / decide | Coordinate | Wrap up |
|---|---|---|---|---|
| official | web search, `ingest_url`, archive captures | `record_evidence`, `record_amount` | tasks, leads | `report` |
| funders_audit | web search, `ingest_url`, `search_funder_records` | same | tasks, leads | `report` |
| web_news, social | web search, `ingest_url`, archive captures | same | tasks, leads | `report` |
| telegram | `fetch_telegram_channel` (public only) | same | tasks, leads | `report` |
| reviewer | none | `review_proposal`, own records (auto-accepted) | `request_collection`, leads | `complete_review` |
| single investigator | all collect tools | `record_*` (auto-accepted) | none | `finish` |

All agents can also search, read, compare versions and names, and `assess`.

### 4. Task lifecycle

```mermaid
stateDiagram-v2
    [*] --> Open: created by planner, code or reviewer
    Open --> Open: unfinished at round end, carried over
    Open --> found: complete_task
    Open --> partial: complete_task
    Open --> not_found: complete_task
    Open --> blocked: complete_task
    Open --> not_run: workflow stopped
    found --> [*]
    partial --> [*]
    not_found --> [*]
    blocked --> [*]
    not_run --> [*]
```

Who creates tasks: the **planner** (round 1); **code** in `normalize_plan`
(coverage by two kinds of source) and around each review (challenge tasks);
the **reviewer** through `request_collection` (next round).

### 5. Evidence lifecycle

```mermaid
stateDiagram-v2
    [*] --> Validation: record_evidence or record_amount
    Validation --> Rejected: quote not found, dates incompatible, unknown sub-claim, blob changed
    Validation --> Accepted: single-agent mode
    Validation --> Pending: team mode
    Pending --> Accepted: reviewer accepts
    Pending --> Disputed: reviewer disputes
    Accepted --> Disputed: reviewer revises
    Disputed --> Accepted: reviewer revises
    Accepted --> Scored: verdict, code
    Rejected --> [*]
    Scored --> [*]
```

Scoring counts each independent origin once (citation chains, copies and
versions of one document collapse), weights it by how hard the source is to
falsify, and applies the verdict rules in [architecture.md](architecture.md).

## What code enforces

Whatever the models do:

- **Only stored documents count.** Web search finds pages; `ingest_url` or
  `ingest_archived_capture` hashes and stores them before they can be cited.
- **Quotes must be real.** Evidence whose quote is not found verbatim in the
  stored text is rejected.
- **Time must make sense.** Evidence observed before the event, or an
  editable official page first seen after the date it is supposed to predate,
  is rejected.
- **Challenge phase.** Supported sub-claims get challenge tasks (team) or
  block `finish` (single agent) until someone has looked for the innocent
  explanation.
- **Budgets.** Each tool call spends the agent's budget; at zero only the
  wrap-up tools work.
- **Citations.** `[doc_id]` citations in summaries are checked against the
  store; unknown ones are reported.
- **Prompt injection is contained.** A page that says "ignore your
  instructions" can at most make a model *propose* something; nothing counts
  unless it passes validation and, in team mode, review.

## Components and their tasks

| Component | Kind | Decides | Cannot |
|---|---|---|---|
| Intake classifier | 1 model call | how to describe the request | accept or refuse it (code does) |
| Decomposer | 1 model call | sub-claims, hypotheses, core set | invent ids later used by code (filtered) |
| Planner | 1 model call | entities, window, tasks, budget weights | leave a core sub-claim on one kind of source |
| Specialists (x5) | tool loops, parallel | what to search, fetch, propose; task outcomes | make evidence count; use other specialists' tools |
| Reviewer | tool loop | accept / dispute; new tasks | collect; close with pending proposals |
| Orchestrator | code | rounds, budgets, challenge tasks, stopping | be overridden by any model |
| Validator / scorer | code | what is valid, statuses, verdict | be skipped |
| Report | code | the case file | include anything not traceable |

## Tasks

A task is the unit of work: `{specialist, objective, sub-claims, purpose
(support | challenge | explore), queries, urls, round, created_by (planner |
code | reviewer)}`. Closing it requires an outcome:

- `found` / `partial`: with the documents that answer it
- `not_found`: searched properly, nothing in reach. **Absence is evidence**
  (no tender notice on TUNEPS) and appears in the case file.
- `blocked`: source unreachable or access we do not have; a gap to report.

Unfinished tasks carry over to the next round; tasks still open at the end
appear as "not run" in the case file.

## Leads board

Specialists run in parallel and cannot see each other's work mid-round, so
they `post_lead(to, note)`: a URL, a spelling, a decree number. Recipients see
leads in `list_tasks`; the reviewer sees leads addressed to it in its brief.

## PoC mode

On by default (`--no-poc` to turn off). Cases the policy routes to legal
review proceed, the ledger records that the review was skipped, and the case
file carries a banner: internal working document, not for publication.
Refusals (espionage, private life, no documented act, no public nexus) still
apply.

## Suspecting shady cases proactively

Waiting for someone to ask misses most cases. Three monitors can open cases on
their own, each feeding the same workflow through a triage queue:

1. **Procurement red flags** (`caligula screen`, `redflags.py`): score every
   new award for non-competitive procedure, missing notice, single bidder,
   rushed deadline, newly created supplier, price above estimate, inflating
   amendments, splitting under thresholds, supplier dominance, timeline
   inconsistencies; and companies for low capital against the award, address
   clusters, and bidders sharing people or addresses. High scores open an
   investigation.
2. **Retcon monitor**: re-fetch watched official pages (JORT, TUNEPS, ministry
   communiqués) on a schedule, archive each version, and alert when an amount,
   date or decree number changes silently.
3. **Stance monitor** (the original Caligula idea): archive politicians'
   public statements and flag reversals or deletions, then fact-check the new
   position against the old one.

## Decisions taken

1. Channels: to be decided; the engine is channel-agnostic.
2. Reviewer: an agent for now (above); expert rubrics later.
3. Scope: companies, public bodies, public officials in their public role, and
   private individuals only through a documented link. No espionage
   accusations, no "could be planning". See [legal.md](legal.md), section 3.
4. Language: French and English (prompts, OCR default `fra+eng`, replies in the
   language of the claim).
5. Sources: every lawful source, including formal access-to-information
   requests; official claims stored as published as proof. See
   [legal.md](legal.md), section 4.
