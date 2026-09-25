# Research: how professionals investigate, and what Caligula should learn

This note compares Caligula's current process with the methods of the
professions that do this work for a living: intelligence analysts, investigative
journalists, anti-fraud investigators, anti-money-laundering analysts, and
automated fact-checking researchers. Each section ends with proposals (ids
`R1`…) that feed the [roadmap](roadmap.md). Sources are listed at the end.

Nothing here is implemented yet. The point is to choose what to build with the
reasons in view.

---

## 1. The benchmark: what goes wrong with Grok-style fact-checking

A large study of 1.67 million fact-check requests to Grok and Perplexity on X
(Feb–Sep 2025) found:

- Grok agreed with professional fact-checkers on **54.5%** of posts, Perplexity
  on **57.7%**, against **64.0%** agreement between professional fact-checkers
  themselves.
- The two bots agreed with each other only **52.6%** of the time and strongly
  disagreed **13.6%** of the time.
- LLM fact-checks still shift what people believe, with effects comparable to
  professional fact-checks. Wrong answers therefore do real damage.

DFRLab's study of the Israel–Iran war found Grok inconsistent within minutes
on the same item, labelling an AI-generated video as real footage, and unable
to tell official accounts from impostors.

**What this means for Caligula.** Accuracy alone does not win. The failures
are *inconsistency*, *unverifiable reasoning*, *no source authentication* and
*no abstention*. Caligula already computes verdicts in code from stored
evidence, which is the right basis. It should measure and advertise four
properties Grok lacks:

1. **Consistency**: same evidence, same verdict, every time.
2. **Traceability**: every sentence tied to a stored quote.
3. **Source authentication**: official versus impostor, original versus copy.
4. **Honest abstention**: "not enough evidence" is a verdict.

> **R1. Benchmark protocol.** Evaluate on labelled claims with the AVeriTeC
> criterion (the verdict counts only if the evidence is also adequate), plus a
> *consistency* metric (run each claim N times, measure how much the verdict
> varies) and ALCE-style citation precision and recall. Run Grok on the same
> claims and publish the comparison.

---

## 2. Hypotheses: from "support versus contradict" to competing explanations

**What analysts do.** Heuer's *Analysis of Competing Hypotheses* (ACH) builds
a matrix: every piece of evidence is rated *consistent*, *inconsistent* or
*neutral* against **every** hypothesis. Evidence consistent with all
hypotheses has no *diagnostic* value and is set aside. The most likely
hypothesis is the one with the **least evidence against it**, not the most
for it. Two further steps: a *sensitivity analysis* (what if a key item is
wrong?) and *milestones* to watch. UNESCO's *Story-Based Inquiry* manual
applies the same logic to journalism: the story is a hypothesis until
verified, and the investigation is organised around testing it.

**What Caligula does today.** Evidence is attached to *sub-claims*, and
hypotheses only predict sub-claim truth values. So:

- Non-diagnostic evidence counts fully. "The outage happened" supports both
  the deficit and the demand-surge hypotheses, yet adds to support.
- Hypotheses are ranked only by falsification, not by weighing inconsistency.
- Nothing tells the reader which single document the conclusion rests on.
- Innocent hypotheses (emergency procedure, administrative error, market
  shock) exist only if the model thinks of them.

> **R2. ACH matrix.** Rate each accepted evidence item against every
> hypothesis (consistent / inconsistent / neutral), with the reviewer
> confirming the ratings. Compute diagnosticity in code, rank hypotheses by
> weighted inconsistency, and show the matrix in the case file.
>
> **R3. Sensitivity analysis.** For the verdict and each hypothesis, remove
> each evidence cluster in turn and recompute. Report "the conclusion depends
> on X": this tells the editor what to double-check and the accused what to
> answer.
>
> **R4. Mandatory null hypotheses.** Every case carries a code-generated set
> of innocent explanations for its claim type (procurement: legal emergency
> procedure, market price shock, administrative error, force majeure,
> legitimate sole supplier). The planner must plan tests for them. This is the
> structured version of the challenge phase.
>
> **R5. Observable implications.** Each hypothesis lists what we would expect
> to find if it were true, including documents that *should exist* (a tender
> notice, progress reports, a delivery receipt). Tasks search for them. A
> proper `not_found` then becomes scored evidence, weighted by how complete the
> searched source is. A missing tender notice on a register that lists every
> tender weighs heavily; a missing news article weighs little.

---

## 3. Weighing evidence: two axes, not one weight

**What analysts do.** The NATO Admiralty system (STANAG 2511) grades
separately the **reliability of the source** (A–F, from its track record) and
the **credibility of the item** (1–6: confirmed by independent sources,
probably true, … cannot be judged). Schum breaks credibility down further:

- for **tangible evidence** (documents): *authenticity*, *accuracy* and
  *reliability of the process that produced it*;
- for **testimony** (statements, posts): *competence* (did the source have
  access?), *veracity* (do they believe what they say?), *objectivity* (did
  they form the belief on evidence?) and *observational sensitivity*.

ICD 203 requires products to describe the quality of their sources and to
express **likelihood** (how probable a judgment is) separately from
**confidence** (how solid its basis is), and never to mix the two in one
statement.

**What Caligula does today.** One fixed weight per source *kind*, noisy-OR
across clusters, and a single "confidence" number that mixes likelihood with
evidential strength. A statement by the accused institution weighs the same
whether it admits something or defends itself.

> **R6. Two-axis grading.** Per evidence item, record source reliability (from
> publisher history, `B7`) and information credibility (from corroboration and
> consistency, computed in code). Show the grade (e.g. "B2") in reports.
>
> **R7. Interest of the source.** Record each source's relation to the claim:
> accused party, opponent, neutral, or official record. A statement *against*
> the source's own interest (an institution admitting an irregularity) is
> strong evidence. A self-serving one (the accused justifying itself) is weak.
> Courts use the same rule. It is cheap to add and changes weights a lot.
>
> **R8. Likelihood and confidence, reported separately.** The verdict gives a
> likelihood in estimative language (remote, unlikely, roughly even, likely,
> very likely, almost certain) *and* a confidence level (low, moderate, high)
> based on source quality, independence, gaps and sensitivity. Two different
> statements.
>
> **R9. Likelihood ratios instead of noisy-OR** (after D1 exists). Each graded
> item contributes a likelihood ratio per hypothesis, combined across
> *independent* clusters. This fits ACH and extends to a Bayesian inference
> network later. Calibrate on the labelled set before switching.

---

## 4. Connecting the dots: entities, networks, timelines

**What investigators do.** OCCRP's Aleph maps every dataset (company
registers, leaks, procurement, sanctions) onto one data model,
**FollowTheMoney** (people, companies, contracts, payments, ownership,
directorship, family, all as entities and dated relationships). It then
*cross-references* entities across hundreds of datasets. That is where leads
come from: the same director in a winning company and in a losing bidder, a
supplier's owner on a list of politically exposed persons. Research on
procurement networks uses **co-bidding networks** and community detection to
find cartels, and buyer–supplier networks to find favouritism. FATF's
indicators of concealed beneficial ownership include:
- mass-registration addresses and "mass" nominee directors;
- directors replaced shortly after incorporation;
- relatives acting as informal nominees;
- activity inconsistent with the company's stated business.

**What Caligula does today.** Name matching, company-level flags on supplied
records, and a timeline in the case file. There is no persistent graph, no
cross-referencing against outside lists, and no network analysis.

> **R10. Adopt FollowTheMoney as the entity model.** It is an open standard
> used by Aleph and OpenSanctions, so data imports and exports without custom
> mapping. Entities and relations are stored with provenance per edge (which
> document, which capture).
>
> **R11. Cross-referencing as a tool.** Every new entity is matched against
> the entity store and outside lists (OpenSanctions, which covers
> politically exposed persons including Tunisia via Wikidata and other
> sources). Matches become leads with a score, and people always go to human
> confirmation.
>
> **R12. Network indicators.**
> - co-bidding communities (possible cartels);
> - a buyer's concentration on one supplier network over time;
> - suppliers winning across several buyers that share signatories;
> - ownership chains ending in the same person or address.
>
> Relational red flags computed on the graph, not per record.
>
> **R13. Timeline anomalies.** Dated events extracted from documents (company
> registered, tender published, award, signature, director change, amendment,
> payment), with rules for impossible or suspicious sequences:
> - award before the tender notice;
> - company created weeks before a large award;
> - director change right after an award;
> - amendments exceeding the original value.
>
> **R14. Peer baselines instead of absolute thresholds.** A buyer's
> single-bid rate, gré-à-gré share or average decision period is compared with
> buyers of the same sector and size. An anomaly is a deviation from peers.
> This cuts false positives, which the Open Contracting guide warns about.

---

## 5. Red flags across the whole procurement lifecycle

**What the field uses.** The Open Contracting Partnership's guide defines
**73 red flags** across planning, tender, award, contract and implementation,
with formulas on the OCDS data standard. Its open-source library **Cardinal**
computes them for any OCDS publisher. Fazekas's validated indicators are
single bidding, no published call, restricted or non-open procedure, a short
advertisement period, hard-to-quantify evaluation criteria, and an abnormal
decision period (too short *or* too long). They predict proven corruption
cases in Italy. Benford's law is only a weak screen: it does not apply to
capped values, needs large samples, and says nothing about a single contract.
TUNEPS handles over 10,000 tenders a year, and HAICOP's national procurement
observatory (ONMP) collects procurement data.

**What Caligula does today.** About ten award-level flags plus four
company-level flags, with fixed thresholds.

> **R15. Map TUNEPS / ONMP data to OCDS** and reuse Cardinal's indicators
> rather than re-implementing them. Priority indicators: Fazekas's validated
> set, then implementation-phase flags (amendments, delays, payments before
> delivery), which our current screening barely covers.
>
> **R16. Composite risk score with validation.** Combine flags, weighted by
> how well each predicts confirmed cases (Cour des comptes findings,
> convictions), not equally. Benford only as a portfolio-level screen with its
> limits stated.

---

## 6. Fact-check mode: questions, reuse, and the "misleading" verdict

**What the research does.** AVeriTeC turns each claim into **questions with
evidence-backed answers**, and its verdicts include **"conflicting evidence /
cherry-picking"** besides supported, refuted and not enough evidence. Many
political claims use true numbers with a misleading frame. Fact-checkers first
look for **existing fact-checks** of the same claim: Google's Fact Check Tools
API exposes worldwide ClaimReview markup, filterable by language.

> **R17. Question–answer verification.** Sub-claims become explicit questions
> ("What was the INS unemployment rate for Q2 2026?"), each answered with a
> validated quote, or "not found". The case file shows the Q&A chain, which is
> easier to read and check than a score.
>
> **R18. "Misleading / missing context" verdict.** Distinguish *literally
> false* from *true but misleading*: cherry-picked period, wrong comparison
> base, preliminary figure later revised.
>
> **R19. Reuse before research.** Search existing fact-checks (ClaimReview,
> French and English) and Caligula's own verified fact base (roadmap `E1`)
> before planning collection. This is also the path to sub-30-second answers.
>
> **R20. Data vintage.** Statistics get revised. Record which release a
> figure comes from, and flag claims that compare a preliminary figure with a
> final one.

---

## 7. Concluding and summarising: the analytic product

**What ICD 203 and the CIA tradecraft primer require.**
- A description of source quality.
- Assumptions distinguished from judgments.
- Alternatives considered.
- Uncertainty properly expressed.
- Changes from earlier judgments noted.
- **Indicators** to watch.

The primer adds a *Key Assumptions Check* and a *Quality of Information
Check*. Wigmore charts and their modern argument maps make every inference
step explicit, including the **generalisation** each step relies on (e.g. "a
company created six months before a 120M award rarely has the capacity to
deliver it"). Those generalisations are exactly what the defence will attack.

**What citation research shows.** Even the best models leave about **half** of
their citations not fully supporting the sentence on hard long-form tasks
(ALCE). A correct answer can still have unfaithful citations.

**What Caligula does today.** The case file lists sub-claims, anomalies,
evidence and a timeline. The reviewer's summary is free text whose citations
are only checked for *existence*.

> **R21. Standard case-file structure.**
> - bottom line first;
> - key judgments, each with likelihood and confidence;
> - the evidence behind each judgment;
> - alternative hypotheses and why they are less likely;
> - key assumptions;
> - sensitivity ("depends on");
> - gaps and collection requests;
> - indicators that would change the assessment.
>
> **R22. Argument map.** Store inference links (evidence → intermediate fact
> → sub-claim → hypothesis) with the generalisation each relies on, and render
> them as a diagram in the case file. The reviewer can then attack a single
> link instead of the whole story.
>
> **R23. Sentence-level attribution check.** Every factual sentence in a
> summary must cite validated evidence ids (not just document ids). An
> entailment check (model judge, then human spot checks) verifies that the
> cited quotes support the sentence. Unsupported sentences are removed or
> flagged before anything reaches an editor.
>
> **R24. Signposts per case.** Each open case keeps indicators to watch (a
> contract amendment, a new JORT decree, an audit report). A monitor re-opens
> the case when one appears.

---

## 8. Review and challenge: make disagreement real

**What the research shows.** Multi-agent debate improves factuality, but when
all agents share the *same model and the same evidence*, debate cannot surface
what nobody retrieved. Models also tend to reinforce their first answer
(sycophancy). LLMs' *stated* confidence is inflated (on average 88% stated
against 79% correct in one study), so it must never be used as a probability.

**What Caligula does today.** One reviewer, same model, sees the specialists'
reports first. Challenge tasks are queued automatically. Confidence comes from
code, which is correct and should stay that way.

> **R25. Defence counsel agent.** A separate agent, with its own retrieval
> budget and instructions to build the strongest *innocent* account, argues
> against the case before the review closes. Its findings enter the ACH matrix
> like anything else.
>
> **R26. Blind and diverse review.** The reviewer judges proposals before
> reading the specialists' narratives, and a different model or model family
> is used for review than for collection, to decorrelate errors. Disagreements
> between two independent reviewers go to adjudication (roadmap `D5`).
>
> **R27. Premortem and key-assumptions step.** Before the case file is
> written, the reviewer answers two questions: "assume this conclusion is
> proven wrong in six months: why?" and "which assumptions, if false, flip the
> verdict?" The answers go into R21's structure.

---

## 9. Verifying media and documents

**What Bellingcat does.** Five pillars for any image or video:
- *provenance*: first appearance, found by reverse image search;
- *source*;
- *date*: chronolocation, e.g. from sun position;
- *location*: geolocation against satellite imagery;
- *motivation*.

For documents the equivalent is authenticity: metadata, producing software,
signatures, and consistency with genuine documents from the same issuer.

> **R28. Media verification tools** for the specialists: first-appearance
> search, EXIF and date checks, and geolocation support (satellite comparison
> is already in the roadmap as `C6`). All results are stored as analysis
> documents and scored like any evidence. This fills roadmap `B3`.
>
> **R29. Document authenticity profile.** Compare a document with genuine
> documents from the same issuer: layout, reference numbering scheme, dates,
> signatories. A "decree" whose number does not fit JORT's sequence for that
> date is suspect.

---

## 10. Tunisian sources and lawful access

- **TUNEPS**: all public procurement, over 10,000 tenders a year. **HAICOP /
  ONMP**: procurement data and oversight.
- **Business register (RNE)**, Law 2018-52: beneficial owners (over 20% or
  effective control) sit in a dedicated register. A ministerial order of
  13 January 2026 sets access rules: authorities through interoperability,
  the public on a **legitimate-interest** justification.
- **Asset declarations**, Law 2018-46: required of many officials. They were
  collected by INLUCC, whose suspension in 2021 leaves the current state of
  the declarations to be checked.
- **Access to information**, Organic Law 2016-22: refusals are allowed only on
  the grounds of art. 24 (security, defence, international relations, privacy,
  intellectual property) and must give reasons and appeal routes. Appeals go
  to INAI and then the administrative court.
- **Cour des comptes** reports, **JORT**, and politically exposed persons in
  **OpenSanctions**.

> **R30. Access-request workflow.** A specialist drafts access-to-information
> requests (Organic Law 2016-22) and legitimate-interest requests to the
> beneficial-ownership register when public sources run out. Code tracks
> deadlines and outcomes. A refusal outside art. 24 grounds, or a document
> that differs from what was published, becomes evidence. This is the lawful
> answer to redaction.

---

## 11. Technical enablers

| Id | Proposal | Why |
|---|---|---|
| R31 | **Two timelines per fact**: when it was true (valid time) and when a record said so (recorded time), bitemporal storage | A rewritten record is exactly a gap between "what JORT said on 1 March" and "what JORT says now". Makes retcon detection a query instead of a special case |
| R32 | **W3C PROV** vocabulary for the ledger (entity, activity, agent; `wasDerivedFrom`, `wasGeneratedBy`) | Standard, exportable provenance for courts, partners and replication |
| R33 | **Splink** (probabilistic record linkage, Fellegi–Sunter) for entity resolution at registry scale | Our hand-made similarity is fine for dozens of names, not for millions of register rows; Splink needs no training data |
| R34 | **Event-sourced workspace** (every tool effect is an event; state is a replay) | Gives resume after a crash (roadmap `A6`), exact replay of a case, and the audit trail in one mechanism |
| R35 | **Model routing**: cheaper models for readers and extractors, the strongest for planner, reviewer and defence counsel, and a different family for the second reviewer | Cost, speed, and less correlated errors |
| R36 | **Graph analytics** in Postgres (recursive queries) first, then a graph engine if the data outgrows it | Enough for ownership chains and co-bidding networks without new infrastructure |

---

## Priorities

The ranking is by value to the purpose (finding and proving anomalies) per
unit of effort, given what already exists.

| Order | Proposals | Why first |
|---|---|---|
| 1 | R4, R5, R7 | Small changes, big effect on fairness and reasoning: mandatory innocent hypotheses, expected-evidence searches (absence as scored evidence), interest of the source |
| 2 | R2, R3, R8 | ACH matrix, sensitivity, likelihood versus confidence: the core of "concluding" properly |
| 3 | R21, R23 | The case file an editor, a lawyer or a court can rely on |
| 4 | R10, R11, R13 | Connecting the dots: FollowTheMoney entities, cross-referencing, timeline anomalies |
| 5 | R1 (with D1) | Measure all of the above, and the comparison with Grok |
| 6 | R25, R26, R27 | Stronger challenge once the matrix exists to receive it |
| 7 | R12, R14, R15, R16 | Network and lifecycle red flags, once procurement data is available |
| 8 | R17–R20, R28–R30 | Fact-check-mode depth, media verification, lawful access workflow |
| - | R31–R36 | Enablers, pulled in by the items above (R31 with R13, R33 with R10, R34 with A6) |

---

## Sources

- Heuer, *Analysis of Competing Hypotheses*: [Wikipedia](https://en.wikipedia.org/wiki/Analysis_of_competing_hypotheses), [SANS ISC](https://isc.sans.edu/diary/22460), [Dhami et al. 2019](https://onlinelibrary.wiley.com/doi/full/10.1002/acp.3550)
- ICD 203 Analytic Standards: [ODNI PDF](https://www.intelligence.gov/assets/documents/intelligence-community-directives/ICD_203.pdf), [FAS copy](https://irp.fas.org/dni/icd/icd-203.pdf)
- CIA, *A Tradecraft Primer: Structured Analytic Techniques*: [CIA PDF](https://www.cia.gov/resources/csi/static/Tradecraft-Primer-apr09.pdf)
- Admiralty code / NATO STANAG 2511: [Wikipedia](https://en.wikipedia.org/wiki/Admiralty_code), [overview](https://pangearesearch.substack.com/p/the-admiralty-code-nato-6x6-system)
- Schum, *The Evidential Foundations of Probabilistic Reasoning*: [review (PMC)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3750218/); Tecuci, Schum et al., *Intelligence Analysis as Discovery of Evidence, Hypotheses and Arguments*: [review](https://www.researchgate.net/publication/320656510)
- Wigmore charts and argument mapping: [Wikipedia](https://en.wikipedia.org/wiki/Wigmore_chart), [Bex et al.](https://link.springer.com/chapter/10.1007/978-94-007-0140-3_3), [Schum, abductive reasoning in law](https://link.springer.com/content/pdf/10.1007/978-3-7908-1792-8_16.pdf)
- UNESCO, *Story-Based Inquiry* (2nd ed.): [UNESCO](https://www.unesco.org/en/articles/new-edition-story-based-inquiry-global-reference-investigative-journalists)
- OCCRP Aleph and FollowTheMoney: [data model](https://docs.aleph.occrp.org/developers/followthemoney/), [cross-referencing](https://docs.aleph.occrp.org/users/investigations/cross-referencing/), [GIJN tipsheet](https://gijn.org/resource/using-aleph/)
- Fazekas et al., procurement corruption risk indicators: [BJPolS 2020](https://ideas.repec.org/a/cup/bjposi/v50y2020i1p155-164_7.html), [IMF method](https://www.elibrary.imf.org/downloadpdf/view/journals/001/2022/094/article-A001-en.pdf), [network perspective](https://arxiv.org/pdf/1909.08664)
- Open Contracting Partnership: [Red flags guide (2024)](https://www.open-contracting.org/resources/red-flags-in-public-procurement-a-guide-to-using-data-to-detect-and-mitigate-risks/), [Cardinal library](https://www.open-contracting.org/2024/06/12/cardinal-an-open-source-library-to-calculate-public-procurement-red-flags/)
- Procurement network analysis: [systematic mapping, EPJ Data Science 2025](https://epjdatascience.springeropen.com/articles/10.1140/epjds/s13688-025-00569-3), [Guatemala longitudinal study](https://www.sciencedirect.com/science/article/pii/S037887332400039X)
- World Bank, *Fraud and Corruption Awareness Handbook*: [PDF](https://documents1.worldbank.org/curated/en/309511468156866119/pdf/877290PUB0Frau00Box382147B00PUBLIC0.pdf), [Warning signs](https://documents1.worldbank.org/curated/en/223241573576857116/pdf/Warning-Signs-of-Fraud-and-Corruption-in-Procurement.pdf)
- FATF / Egmont, concealment of beneficial ownership: [report](https://www.fatf-gafi.org/en/publications/Methodsandtrends/Concealment-beneficial-ownership.html), [indicators annex](https://www.fatf-gafi.org/content/dam/fatf-gafi/reports/FATF-Egmont-Concealment-beneficial-ownership-annex-E.pdf)
- Benford's law limits: [CAG India audit paper](https://cag.gov.in/uploads/research_paper/RES-2-Benford-05ebe241db89494-32544853.pdf), [international trade study](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6320519/)
- AVeriTeC: [dataset paper](https://arxiv.org/pdf/2305.13117), [shared task overview](https://aclanthology.org/2024.fever-1.1.pdf)
- Google Fact Check Tools API (ClaimReview): [docs](https://developers.google.com/fact-check/tools/api)
- Grok and LLM fact-checking on X: [Grok Is This True? (preprint)](https://osf.io/preprints/psyarxiv/85quw_v1), [DFRLab](https://dfrlab.org/2025/06/24/grok-struggles-with-fact-checking-amid-israel-iran-war/), [TechCrunch](https://techcrunch.com/2025/03/19/x-users-treating-grok-like-a-fact-checker-spark-concerns-over-misinformation/)
- Multi-agent debate: [Du et al.](https://www.emergentmind.com/papers/2305.14325), [limits of homogeneous debate](https://arxiv.org/pdf/2608.00243), [Tool-MAD](https://arxiv.org/pdf/2601.04742)
- Citation faithfulness (ALCE): [Gao et al. 2023](https://arxiv.org/abs/2305.14627)
- LLM confidence calibration: [verbalized confidence](https://arxiv.org/html/2412.14737v2), [inflated confidence mechanisms](https://arxiv.org/html/2604.01457v2)
- Bellingcat verification: [beginner's guide](https://www.bellingcat.com/resources/2021/11/01/a-beginners-guide-to-social-media-verification/), [five pillars of image verification](https://arxiv.org/pdf/2408.09939)
- Tunisia: [TUNEPS (APPN)](https://appn-racop.org/en/tunie-the-online-public-purchasing-system-tuneps/), [e-procurement review](https://institutdesfinances.gov.lb/sites/default/files/2024-06/improving-e-procurement-environment-tunisia-en.pdf), [Law 2018-52 (RNE)](https://legislation-securite.tn/latest-laws/loi-n-2018-52-du-29-octobre-2018-relative-au-registre-national-des-entreprises/), [beneficial-owner access rules, Jan 2026](https://www.lapresse.tn/2026/01/25/beneficiaire-effectif-la-tunisie-precise-les-regles-dacces-aux-informations/), [Law 2018-46](https://legislation-securite.tn/latest-laws/loi-n-2018-46-du-1er-aout-2018-relative-a-la-declaration-de-patrimoine-et-dinterets-et-a-la-lutte-contre-lenrichissement-illicite-et-les-conflits-dinterets/), [Organic Law 2016-22](https://legislation-securite.tn/latest-laws/loi-organique-n-2016-22-du-24-mars-2016-relative-au-droit-dacces-a-linformation/), [INAI](https://www.coe.int/fr/web/tunis/instance-nationale-d-acces-a-l-information-inai-)
- OpenSanctions PEPs: [dataset](https://www.opensanctions.org/datasets/peps/), [coverage](https://www.opensanctions.org/docs/coverage/pep/)
- Splink (Fellegi–Sunter record linkage): [docs](https://moj-analytical-services.github.io/splink/index.html)
- W3C PROV: [PROV-DM](https://www.w3.org/TR/prov-dm/), [PROV-O](https://www.w3.org/TR/prov-o/)
