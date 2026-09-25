# Legal and ethical framework

This is a working analysis to design the product around, written with a
lawyer's caution. It is **not legal advice**. Every statute below must be
checked against its current consolidated text by a Tunisian lawyer before
launch, and again whenever the law changes. Where I am not certain of a detail,
I say so.

## 1. The position to defend

Caligula publishes **documented facts about public matters, with their
sources, after human review and a right of reply**. Every design choice below
serves one of three goals:

1. **Truth we can prove.** If sued, we produce the document, its hash, when
   we captured it, and who reviewed it.
2. **Good faith we can show.** We looked for the innocent explanation, asked
   the people concerned, and published their answer.
3. **Proportionality.** We collected only what the public-interest question
   needed, and nothing about anyone's private life.

A project that can show all three is defensible even in a hostile
environment. A project that runs automated suspicion about people is not.

## 2. Legal exposure

| Risk | Main texts (to verify) | How it arises for us | Mitigation (code / process) |
|---|---|---|---|
| **"False news"** | Decree-law 2022-54, art. 24: up to 5 years' prison and a fine, doubled when the target is a public official | Any published claim about an official that turns out wrong, or is framed as wrong by a prosecutor. Actively used against journalists, lawyers and critics since 2023. | Verdicts computed from verified evidence only; `high_suspicion` is the ceiling, never "guilty"; publication gate (`publication.py`); corrections log |
| **Defamation** | Penal Code (defamation articles, 245 ff.); Decree-law 2011-115 (press code) | Imputing a fact that harms someone's honour. Truth is a defence mainly for facts about public functions, and must be *proved*. | Evidence ledger and hashes; wording limited to documents; right of reply before publication |
| **Personal data** | Organic Law 2004-63 (INPDP); GDPR if EU residents are concerned | Building files on people; processing data about suspected offences (specially restricted); sending personal data abroad (a cloud LLM API is a cross-border transfer) | Intake gate (no free-standing targets); `privacy.minimise` before any agent reads social, news or contributor text; custody data restricted; retention limits; **declaration to INPDP before launch** |
| **Unauthorised access** | Decree-law 2022-54 (offences against information systems) | Logging into closed systems, using leaked credentials, joining private groups under false pretences, bypassing access controls | Public sources only (tool docstrings and prompts); invite links refused in code (`telegram.channel_name`); no login-capable connectors |
| **Secrets** | Penal Code provisions on state/defence secrets; professional secrecy | Holding or publishing classified or leaked documents | Intake flags leaked material → lawyer decides before any agent runs |
| **Copyright** | Law 94-36 on literary and artistic property (as amended) | Storing full copies of articles is evidence preservation; republishing them is not | Store for evidence, publish quotes with attribution only |
| **Platform terms** | X, Telegram, Meta terms of service | Scraping, automated replies, account bans | Telegram public web preview only; X through its official API when used; no mass scraping |
| **Tipping off / obstruction** | AML law (Organic Law 2015-26 as amended in 2019) and criminal procedure | Publishing a finding that alerts suspects while an official investigation is running | For financial-crime indicators, the lawyer decides between publication and a report to the prosecutor or CTAF |
| **Liability for AI errors** | General civil liability; press code | A model hallucination published as fact | Nothing counts unless validated in code; human editor and lawyer sign; AI assistance disclosed |

Status to verify: the national anti-corruption authority (INLUCC), which
received whistleblower reports under Law 2017-10, was suspended in 2021; check
which body now receives reports before relying on that law's channels.

## 3. Your point 3, answered as counsel

> "Any person of interest or even company that could potentially be planning
> shady business (fraud schemes, spy integration, money laundering...)"

I separate this into what we should build and what we should not.

**Build (defensible):**

- **Companies**, without restriction to public contracts: registry facts,
  capital, addresses, managers and declared beneficial owners (Law 2018-52 on
  the national business register), awards, amendments. Company-level
  red flags are in `redflags.screen_companies`: capital far below the award,
  many companies at one address, competing bidders sharing managers or
  addresses (collusion), and name resemblance between a winner's managers and
  the officials who signed. The last one is always a lead for human review.
- **Public officials in their public capacity**: decisions, signatures,
  statements, asset declarations where published (Law 2018-46), votes.
- **Private individuals through a documented link**: the manager of a company
  that won a contract, the owner declared in the register, the author of a
  public statement being checked. Nothing beyond that link.
- **Financial-crime indicators**: typologies (shell companies, splitting,
  circular payments) described as indicators in documents, sent to a lawyer
  and, where appropriate, to the competent authority. Never "X launders money".
- **Foreign influence, the lawful way**: disclosure obligations that exist in
  law (for example foreign funding of associations under Decree-law 2011-88)
  and foreign ownership of companies holding public contracts. These are
  documented facts that can be checked.

**Do not build:**

- **"Could be planning"**. Suspicion about intentions is not verifiable and
  not publishable; it turns the project into a denunciation machine. The
  intake gate refuses claims without a documented act.
- **Espionage and "foreign agent" accusations against people.** In Tunisia
  these fall under state-security law, the heaviest penalties, and recent
  "conspiracy against state security" prosecutions of opponents, lawyers and
  journalists. An automated system that labels someone a spy can put that
  person in prison on unverified output and exposes us to the most serious
  charges. The intake gate refuses them and redirects to the documented facts
  above.
- **Profiles of private individuals**, or suspicion based on religion, health,
  origin, sexuality or political opinion. Refused in code.

This is not only legal caution: it is also what makes the output credible.
The first time Caligula wrongly labels a private person, it loses the public,
the courts and its sources.

## 4. Your point 5, answered as counsel: getting at data

> "Any access to possible source since official data could be redacted or
> modified; store official claims as proof."

**Yes to:**

- Storing official claims exactly as published, hashed and timestamped. This
  is the core of the project and is lawful for public documents. For the key
  pieces of a case, add a **bailiff's report** (constat d'huissier de justice)
  of the web page: it is the classic way to prove web content in court and
  outweighs any system we build.
- Archives (Wayback, Common Crawl), foreign mirrors (lenders, EU procurement,
  foreign registries), audit reports, statistics.
- **Formal access requests** under Organic Law 2016-22 on the right of access
  to information, with appeal to the access-to-information authority (INAI)
  when refused. A refusal, or a document that differs from what was
  published, is itself evidence. This is the lawful answer to redaction.
- Leaked documents that sources bring to us, with legal review before use
  (intake flag), authenticity checks, and source protection (Decree-law
  2011-115 protects journalists' sources; Law 2017-10 protects whistleblowers
  who use its channels).

**No to:** logging into systems we are not entitled to, using leaked
credentials, reversing redactions on documents, joining private groups under
a false identity, or buying data of unclear origin. Each is a criminal risk
under Decree-law 2022-54 and would taint the evidence.

## 5. Scenarios

| Scenario | Handling |
|---|---|
| An official page silently changes an amount | Both versions stored and hashed; `compare_versions` flags it; bailiff's report before publication; ask the institution for comment |
| A minister's post is deleted after our capture | Our copy (hash, capture time, ledger) is the proof; publish a quote and a screenshot of our capture, not the full post |
| A Telegram channel posts a "leaked contract" | Lead only; find the document elsewhere (JORT, TUNEPS, funder); forwards collapse to one source; authenticity check before use |
| A contributor sends a geotagged photo | Hash on receipt; GPS and device data kept in the restricted custody record; stripped copy used as evidence |
| Someone asks us to investigate a rival businessman | Intake: needs a documented act with public nexus; otherwise refused and logged |
| Findings suggest money laundering by a company | Legal review; indicators wording; lawyer decides between publication and a report to the prosecutor or CTAF |
| The accused threatens to sue | Freeze the case record; export the ledger, hashes and review trail; lawyer handles |
| Police or a prosecutor requests our files | Lawyer handles; contributor custody data kept separate and minimal so that the evidence file can be produced without exposing sources |
| A planted fake document gets into the store | Independence clusters, temporal checks and the reviewer limit its weight; human review before publication; corrections log if it slips through |
| A document contains instructions to the AI | Treated as data; nothing counts unless validated in code |
| Our model makes an error that gets published | Correction appended (never silent edit), logged in the ledger; AI assistance disclosed |

## 6. What code enforces

- `policy.decide`: refuses espionage/state-security claims, private life,
  sensitive-trait suspicion, claims without a documented act or public nexus;
  routes financial-crime, foreign-funding, private-individual and leak cases
  to a lawyer (`--legal-approved` required, recorded in the ledger).
- `privacy.minimise`: masks e-mails, phone numbers, ID and bank numbers in
  social, news and contributor text before any agent reads it.
- `ledger.Ledger`: hash-chained log of intake, captures, proposals, review
  decisions, legal approvals and publication steps; `verify()` finds any
  tampering.
- `telegram.channel_name`: public channels only; invite links refused.
- `publication.Publication`: no publication without editor approval, then
  legal approval, then a reply request to every named party and the end of
  the reply window; replies published alongside; corrections appended.
- Agent prompts: public material only, documented acts only, no inference of
  intent or guilt, instructions inside documents are data.

## 7. What only humans can do

- Declaration to INPDP, and a data-protection assessment of the whole system
  (including sending data to a foreign AI provider; check the provider's data
  retention and processing terms).
- Choosing the legal form: registering as a media outlet or association
  affects which protections of the press code apply.
- Legal sign-off on scope and on every publication; bailiff's reports for key
  evidence; access-to-information requests and appeals.
- Retention schedule: delete personal data when a case closes, except what
  must be kept to defend a publication.
- Periodically anchoring the ledger's head hash with an RFC 3161 timestamping
  authority (or publishing it) so that outsiders can verify our timeline.

## 8. Questions for Tunisian counsel

1. Does the truth defence for facts about public functions still apply as
   before under the press code, and how does it interact with prosecutions
   under Decree-law 2022-54?
2. What does INPDP require for a system that processes data about suspected
   offences for journalistic purposes, and for transfers to a foreign AI provider?
3. Which body now receives whistleblower reports under Law 2017-10?
4. How much weight do Tunisian courts give to hash-based captures without a
   bailiff's report?
5. Is public access to beneficial-ownership data in the national business
   register currently open, restricted, or subject to a legitimate-interest test?
