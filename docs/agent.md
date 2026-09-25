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

## Suspecting shady cases proactively

Waiting for someone to ask misses most cases. Three monitors can open cases on
their own, each feeding the same agent through a triage queue:

1. **Procurement red flags** (`caligula screen`, `redflags.py`): score every
   new award for non-competitive procedure, missing notice, single bidder,
   rushed deadline, newly created supplier, price above estimate, inflating
   amendments, splitting under thresholds, supplier dominance, timeline
   inconsistencies. High scores open an investigation.
2. **Retcon monitor**: re-fetch watched official pages (JORT, TUNEPS, ministry
   communiqués) on a schedule, archive each version, and alert when an amount,
   date or decree number changes silently.
3. **Stance monitor** (the original Caligula idea): archive politicians'
   public statements and flag reversals or deletions, then fact-check the new
   position against the old one.

## Open questions

These are product and policy decisions, listed in `README`/chat for discussion:

1. Which channel first: web page, WhatsApp, or X mentions?
2. Who reviews held findings (in-house, partner newsroom, watchdog NGO)?
3. Who can be investigated: public bodies and public money only?
4. Reply language: French, Modern Standard Arabic, Tunisian Darija, or match the asker?
5. Which data feeds can we actually get (TUNEPS exports, JORT archive, RNE)?
