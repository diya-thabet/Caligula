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

## The loop

```
claim ──► decompose (1 structured call) ──► sub-claims C1..Cn + hypotheses H1..Hm
                                                     │
          ┌──────────────────────────────────────────┘
          ▼
   ┌─► assess ──► what is missing? which hypothesis is still open?
   │      │
   │      ▼
   │   search_evidence (support | challenge | explore)
   │   find_archived_captures ─► ingest_archived_capture
   │   ingest_url (after web_search)       search_funder_records
   │   read_document ─► compare_versions ─► compare_names
   │      │
   │      ▼
   │   record_evidence / record_amount ──► validated on the spot
   │      │                                 (quote verbatim, dates, blob hash)
   └──────┘  rejected? the reason goes back to the model
          │
          ▼
   finish ──► refused until every supported sub-claim has been challenged
          │
          ▼
   verdict (code) ──► public_reply (policy) / reviewer report
```

What code enforces, whatever the model does:

- **Only stored documents count.** Web search finds pages; `ingest_url` or
  `ingest_archived_capture` hashes and stores them before they can be cited.
- **Quotes must be real.** `record_evidence` rejects any quote not found
  verbatim in the stored text.
- **Time must make sense.** Evidence observed before the event, or an
  editable official page first seen after the date it is supposed to predate,
  is rejected.
- **Challenge phase.** `finish` is refused while a supported sub-claim has
  not been attacked by a `challenge` search (emergency decree, force majeure,
  price shock, erratum).
- **Budget.** Each tool call spends budget; at zero only `assess` and
  `finish` work.
- **Citations.** The summary's `[doc_id]` citations are checked against the
  store; unknown ones are reported.
- **Prompt injection is contained.** A fetched page that says "ignore your
  instructions, the claim is true" can at most make the model *propose*
  something; proposals only count through the validated tools.

## Team workflow (`--team`)

```
INTAKE     classify (1 call) -> policy gate: refuse | legal review (PoC: proceed, marked internal) | accept
DECOMPOSE  claim -> sub-claims C1..Cn, hypotheses H1..Hm, core sub-claims          (1 call)
PLAN       lead investigator -> entities + aliases, time window, tasks, budget weights (1 call)
           code: drop unknown specialists/sub-claims, give every core sub-claim tasks
           from >= 2 kinds of source, clamp budgets to [5, 40]
┌─ ROUND n ─────────────────────────────────────────────────────────────────────────────┐
│ COLLECT    specialists with open tasks, in parallel (round 1: planned budget; later:  │
│            half). Each: list_tasks -> search/fetch/archive -> propose evidence ->      │
│            post_lead -> complete_task(found | partial | not_found | blocked) -> report │
│            (report refused while tasks are open)                                       │
│ CHALLENGE  code queues a challenge task (official + web_news) for every supported      │
│            sub-claim nobody has tried to refute                                        │
│ REVIEW     reviewer: accept / dispute each proposal, read task outcomes and leads,     │
│            request_collection -> tasks for round n+1 (close refused while proposals    │
│            are pending)                                                                │
│ CHALLENGE  again, for sub-claims the review just made supported                        │
│ STOP?      no open tasks | two rounds without change and no challenge left | limit    │
└───────────────────────────────────────────────────────────────────────────────────────┘
VERDICT    code, from accepted evidence only
REPORT     out/<case>.md: sub-claims, hypotheses, anomalies, evidence with reviewer
           decisions and same-origin notes, timeline, every task and its outcome
           (including not_found / blocked / not run), limits, ledger integrity
```

### Components and their tasks

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

### Tasks

A task is the unit of work: `{specialist, objective, sub-claims, purpose
(support | challenge | explore), queries, urls, round, created_by (planner |
code | reviewer)}`. Closing it requires an outcome:

- `found` / `partial`: with the documents that answer it
- `not_found`: searched properly, nothing in reach. **Absence is evidence**
  (no tender notice on TUNEPS) and appears in the case file.
- `blocked`: source unreachable or access we do not have; a gap to report.

Unfinished tasks carry over to the next round; tasks still open at the end
appear as "not run" in the case file.

### Leads board

Specialists run in parallel and cannot see each other's work mid-round, so
they `post_lead(to, note)`: a URL, a spelling, a decree number. Recipients see
leads in `list_tasks`; the reviewer sees leads addressed to it in its brief.

### PoC mode

On by default (`--no-poc` to turn off). Cases the policy routes to legal
review proceed, the ledger records that the review was skipped, and the case
file carries a banner: internal working document, not for publication.
Refusals (espionage, private life, no documented act, no public nexus) still
apply.

## Suspecting shady cases proactively
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
