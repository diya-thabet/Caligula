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

## Team mode: parallel source specialists + reviewer

`caligula investigate ... --mode investigate --team` runs the case as a team
(`agent/team.py`):

```
intake gate (policy.py) ──► refuse | lawyer approval | accept
        │
decompose ──► sub-claims + hypotheses
        │
round 1 ─┬─ official       JORT, TUNEPS, ministries; archive every page; compare versions
         ├─ funders_audit  World Bank records, audit reports, statistics
         ├─ web_news       articles (web search), trace what each one relies on
         ├─ social         public posts of officials and institutions
         └─ telegram       public channels only, forwards traced to their origin
                 │  each stores documents (hashed, ledgered, minimised) and PROPOSES evidence
                 ▼
         reviewer ──► accept / dispute each proposal, look for contradictions,
                 │    request_collection(specialist, instructions, purpose)
                 ▼
round 2  only the specialists the reviewer asked for, with its instructions
                 ▼
verdict  computed by code from ACCEPTED evidence only
```

- Specialists run in parallel threads on one workspace (locked writes). Each
  has its own tool set and budget: the telegram specialist cannot fetch web
  pages, the reviewer cannot collect.
- The reviewer cannot close while proposals are pending or while a supported
  sub-claim has not been challenged (or a challenge collection queued).
- The reviewer's behaviour takes an expert rubric (`--rubric file.txt`), so
  lawyers, auditors or procurement specialists can write the checklist it
  applies without code changes.
- Every capture, proposal, review decision and approval is appended to the
  hash-chained ledger (`--ledger`).

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
