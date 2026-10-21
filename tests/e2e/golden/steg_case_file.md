# Case STEG-2026-07-21-SYNTHETIC

> **PROOF OF CONCEPT — internal working document.** Not reviewed by a lawyer or an editor. Not for publication or circulation outside the project.

Generated <time> UTC · verdict **high_suspicion** · core facts: very likely (87%) · confidence: moderate

## Bottom line

**High suspicion.** The core facts (C3, C4, C5, C6) are, taken together, very likely (87%) true, with **moderate** confidence.

- Least contradicted explanation: **H3**, Expansion funds were diverted through a non-competitive award.
- Innocent explanation(s) refuted: H4.
- Innocent explanation(s) not yet settled: H5, H6, H7.
- The verdict rests on single origins: it would change without `benchmark` or without `sentinel`.
- No evidence yet on: C7, C8, C10, C11, C12.

## Claim

Synthetic scenario (all entities fictional). The 21/07/2026 outage was caused by a production deficit. A state-funded 450 MW expansion (market 2026-017) was awarded without competitive tender to Société Zeta Travaux at an inflated price, nothing was built, and funds were misappropriated through a link between the contractor and the signing official.

Parties: STEG (accused); Ministère de l'Énergie (fictif) (accused)

## Key judgments

One per sub-claim that is core or has evidence: how likely it is true, how much confidence the basis deserves, and the evidence behind it (ids refer to the annex *Evidence by sub-claim*).

### C3 (core). A funded capacity-expansion project (market 2026-017) existed before the outage.

**supported** · almost certain (98%) true · confidence **moderate**

- For: E6, E7, E8, E9, E10 (2 independent origin(s))
- Against: none
- Confidence capped by: C3 supported but never challenged

### C4 (core). No capacity has been added on the project site since the award.

**supported** · very likely (94%) true · confidence **moderate**

- For: E11, E12 (2 independent origin(s))
- Against: none
- Confidence capped by: one origin decides it: without sentinel, C4 supported → partially_supported; C4 supported but never challenged

### C5 (core). The contract was awarded without a competitive tender.

**supported** · almost certain (over 99%) true · confidence **moderate**

- For: E13, E14, E15 (3 independent origin(s))
- Against: none
- Qualifying: E16
- Confidence capped by: C5 supported but never challenged

### C6 (core). The committed amount exceeds the cost of comparable works by more than 20%.

**supported** · almost certain (95%) true · confidence **moderate**

- For: E19, E21, E22 (3 independent origin(s))
- Against: none
- Confidence capped by: one origin decides it: without benchmark, C6 supported → unverified; C6 supported but never challenged

### C1. A major power outage occurred on 21/07/2026.

**supported** · very likely (92%) true · confidence **moderate**

- For: E1, E2, E3 (2 independent origin(s))
- Against: none
- Confidence capped by: one origin decides it: without nightlights, C1 supported → partially_supported; C1 supported but never challenged

### C2. Peak electricity demand in 2026 rose significantly (more than 5%) over 2025.

**contradicted** · almost no chance (4%) true · confidence **high**

- For: none
- Against: E4, E5 (2 independent origin(s))

### C9. A documented emergency legally justified the direct award (gré à gré).

**contradicted** · very unlikely (17%) true · confidence **moderate**

- For: E17 (1 independent origin(s))
- Against: E18, E23 (2 independent origin(s))
- Confidence capped by: one origin decides it: without audit, C9 contradicted → partially_supported

## Alternatives considered

Each explanation is rated by code against its own predictions; the matrices are in the annex *Competing hypotheses*.

- **H1** (alternative) consistent, evidence against 0.00: The outage was caused by a production deficit, not a demand surge.
- **H2** (alternative) falsified, evidence against 1.40: The outage was caused by a demand surge.

- **H3** (allegation) open, evidence against 0.25: Expansion funds were diverted through a non-competitive award.
- **H4** (innocent) falsified, evidence against 1.27: The direct award was a lawful emergency procedure.
- **H5** (innocent) open, evidence against 0.00, untested: The price reflects a market price shock, not inflation of the contract.
- **H6** (innocent) open, evidence against 0.00, untested: The figures differ because of an error that was, or can be, officially corrected.
- **H7** (innocent) open, evidence against 0.00, untested: The project is delayed, not abandoned, and the money is accounted for.

- Innocent explanation *sole_supplier* ruled out: The award notice and the operator's reply invoke urgency only, never exclusivity (jort_award_v1, steg_procedure).

## Key assumptions

- Sources are weighed by how easily their publisher can silently change them: audit 0.85, foreign_mirror 0.80, archive 0.75, osint 0.70, statistics 0.70, contributor 0.60, official_live 0.50, news 0.35.
- Documents that cite, copy or derive from one another share an origin and count once (2 such group(s) here).
- A party's statement in its own favour weighs 50% of its usual weight.
- E23: Journal Officiel (JORT): decrees, orders and official notices is complete enough (prior 0.85) that a record missing from it is evidence; no capture of the empty result was stored, so it counts half.
- The allocated amount and the benchmark describe comparable works; a gap above 20% backed by 2 independent origins is an anomaly.
- The standard innocent explanations for *corruption_procurement* are the ones worth testing; others may exist.
- All weights and thresholds are uncalibrated priors until a labelled set of cases exists.

## What the conclusion depends on

Each independent origin removed in turn, and what the conclusion loses without it.

- Without `benchmark`: **changes the verdict**: verdict high_suspicion → partially_supported; C6 supported → unverified
- Without `sentinel`: **changes the verdict**: verdict high_suspicion → partially_supported; C4 supported → partially_supported
- Without `audit`: C9 contradicted → partially_supported
- Without `nightlights`: C1 supported → partially_supported

## Gaps and collection requests

- C7: Who are the contractor's managers and owners in the RNE?
- C7: Who signed the award?
- C8: Is there any documented use of the disbursed funds?
- C10: Did prices of the main inputs (equipment, materials, currency) rise over the period?
- C11: Was an erratum or rectification published?
- C11: Does the corrected figure match other records?
- C12: Is a suspension, amendment or extension of the contract documented?
- C12: Were the funds returned, frozen or kept in the project account?
- Innocent explanation H5 not settled: test C10.
- Innocent explanation H6 not settled: test C11.
- Innocent explanation H7 not settled: test C12.
- Expected record not searched yet (C3.E1, Journal Officiel (JORT)): Award notice for market 2026-017 in the JORT.
- Expected record not searched yet (C4.E1, Lenders' project documents and disbursement records): Progress reports or provisional acceptance of the works in the lender's project records.
- Expected record not searched yet (C5.E1, TUNEPS): TUNEPS tender notice for the Rades-Fictive extension, published before the award.
- Expected record not searched yet (C11.E1, Journal Officiel (JORT)): Erratum or rectification of the notice concerned.
- Expected record not searched yet (C12.E1, Lenders' project documents and disbursement records): Suspension, restructuring or extension of the project in the lender's records.
- Supported but never challenged: C1, C3, C4, C5, C6.

## Indicators that would change the assessment

Would weaken the allegation:

- Evidence for H4 (would reopen it): A documented emergency legally justified the direct award (gré à gré). For instance: Decree n° 2026-0412 declaring the emergency, in the JORT (Journal Officiel (JORT)).
- Evidence for H5: Market prices rose enough between the benchmark and the award to explain the price gap.
- Evidence for H6: The discrepancy is a clerical error or an officially published correction (erratum). For instance: Erratum or rectification of the notice concerned (Journal Officiel (JORT)).
- Evidence for H7: Delivery is delayed for documented reasons (force majeure, suspension, litigation), with the funds unspent or recoverable. For instance: Suspension, restructuring or extension of the project in the lender's records (Lenders' project documents and disbursement records).
- Anything showing `benchmark` is wrong, not comparable or not independent.
- Anything showing `sentinel` is wrong, not comparable or not independent.
- C3 would be contradicted if a proper search of Journal Officiel (JORT) finds no: Award notice for market 2026-017 in the JORT.
- C4 would be contradicted by finding: Progress reports or provisional acceptance of the works in the lender's project records (Lenders' project documents and disbursement records).
- C5 would be contradicted by finding: TUNEPS tender notice for the Rades-Fictive extension, published before the award (TUNEPS).

Would strengthen it:

- C4 would be supported if a proper search of Lenders' project documents and disbursement records finds no: Progress reports or provisional acceptance of the works in the lender's project records.
- C5 would be supported if a proper search of TUNEPS finds no: TUNEPS tender notice for the Rades-Fictive extension, published before the award.

## Limits of this assessment

- 4 proposed item(s) rejected by validation (quotes not found, dates incompatible, unknown sub-claims).
- Evidence assessment, not a finding of guilt. Scores use uncalibrated priors. No individual is named by the engine; any attribution requires human review and a right of reply.

---

# Annexes

The detail every judgment above rests on.

## Sub-claims

| | Statement | Status | Support | Against | Independent sources (for / against) |
|---|---|---|---|---|---|
| C1 | A major power outage occurred on 21/07/2026. | supported | 0.85 | 0.00 | 2 / 0 |
| C2 | Peak electricity demand in 2026 rose significantly (more than 5%) over 2025. | contradicted | 0.00 | 0.91 | 0 / 2 |
| C3 (core) | A funded capacity-expansion project (market 2026-017) existed before the outage. | supported | 0.95 | 0.00 | 2 / 0 |
| C4 (core) | No capacity has been added on the project site since the award. | supported | 0.88 | 0.00 | 2 / 0 |
| C5 (core) | The contract was awarded without a competitive tender. | supported | 0.99 | 0.00 | 3 / 0 |
| C6 (core) | The committed amount exceeds the cost of comparable works by more than 20%. | supported | 0.90 | 0.00 | 3 / 0 |
| C7 | The contractor is linked to the official who signed the award. | unverified | 0.00 | 0.00 | 0 / 0 |
| C8 | Project funds were misappropriated. | unverified | 0.00 | 0.00 | 0 / 0 |
| C9 | A documented emergency legally justified the direct award (gré à gré). | contradicted | 0.25 | 0.91 | 1 / 2 |
| C10 | Market prices rose enough between the benchmark and the award to explain the price gap. | unverified | 0.00 | 0.00 | 0 / 0 |
| C11 | The discrepancy is a clerical error or an officially published correction (erratum). | unverified | 0.00 | 0.00 | 0 / 0 |
| C12 | Delivery is delayed for documented reasons (force majeure, suspension, litigation), with the funds unspent or recoverable. | unverified | 0.00 | 0.00 | 0 / 0 |

## Competing hypotheses

Ratings are computed from each hypothesis's predictions: C consistent, **I** inconsistent, – no prediction. ◆ marks diagnostic evidence, which tells the hypotheses apart. The least contradicted hypothesis leads, not the most supported.

Hypotheses H1, H2:

| Evidence | Weight | H1 | H2 |
|---|---|---|---|
| ◆ C2 contradicts · `ins_peak` | 0.70 | C | **I** |
| ◆ C2 contradicts · `weather` | 0.70 | C | **I** |
| C1 supports · `news_outage`, `steg_communique` | 0.50 | C | C |
| C1 supports · `nightlights` | 0.70 | C | C |

Leading: **H1** (evidence against: H1 0.00 · H2 1.40)

Hypotheses H3, H4, H5, H6, H7:

| Evidence | Weight | H3 | H4 | H5 | H6 | H7 |
|---|---|---|---|---|---|---|
| ◆ C9 supports · `steg_procedure` | 0.25 | **I** | C | – | – | – |
| ◆ C9 contradicts · `audit` | 0.85 | C | **I** | – | – | – |
| ◆ C9 contradicts · `absence:jort` | 0.42 | C | **I** | – | – | – |
| C3 supports · `jort_award_v1`, `news_jort_b`, `news_jort_c`, `news_jort_d` | 0.75 | C | – | – | – | – |
| C3 supports · `worldbank` | 0.80 | C | – | – | – | – |
| C4 supports · `site_report` | 0.60 | C | – | – | – | – |
| C4 supports · `sentinel` | 0.70 | C | – | – | – | – |
| C5 supports · `jort_award_v1` | 0.75 | C | C | – | – | – |
| C5 supports · `tuneps_search` | 0.75 | C | C | – | – | – |
| C5 supports · `audit` | 0.85 | C | C | – | – | – |
| C6 supports · `financial-check` | 0.90 | C | – | – | – | – |

Leading: **H3** (evidence against: H3 0.25 · H4 1.27; untested: H5, H6, H7)

## Anomalies

- **Record rewritten**: https://jort.example.tn/2026/017 between 2026-03-01 (`jort_award_v1`) and 2026-09-20 (`jort_award_v2`): amount_tnd ['120000000'] → ['80000000']
- **Financial check** (flagged): allocated 120,000,000 TND vs proven/benchmark 60,000,000 TND, gap 60,000,000 TND (50%), 3 independent origins
  - **E19** allocated 120,000,000 TND · `jort_award_v1` Wayback Machine (archive, 2026-02-20): « pour un montant de 120 000 000 TND »
  - **E22** benchmark 60,000,000 TND · `benchmark` Wayback Machine (archive, 2024-11-05): « pour un montant de 60 000 000 TND »
  - **E21** disbursed 110,000,000 TND · `worldbank` Bailleur international (fictif) (foreign_mirror, 2026-06-30): « Montant décaissé au 30/06/2026 : 110 000 000 TND (équivalent). »
  - **E20** allocated 80,000,000 TND · `jort_award_v2` JORT (fictif) (official_live, 2026-02-20): « pour un montant de 80 000 000 TND » · *not used by the check (see the rewritten record above)*

## Evidence by sub-claim

### C1. A major power outage occurred on 21/07/2026.

- ✓ **E1** supports · `steg_communique` STEG (official_live, 2026-07-21): « une coupure d'électricité a touché plusieurs gouvernorats le 21/07/2026 » · same origin as `news_outage`
- ✓ **E2** supports · `news_outage` Le Quotidien Fictif (news, 2026-07-22): « plusieurs gouvernorats privés d'électricité le 21/07/2026 » · same origin as `steg_communique`
- ✓ **E3** supports · `nightlights` NASA Black Marble (analyse) (osint, 2026-07-23): « Baisse de radiance nocturne de 62 % sur le Grand Tunis »

### C2. Peak electricity demand in 2026 rose significantly (more than 5%) over 2025.

- ✓ **E4** contradicts · `ins_peak` INS (fictif) (statistics, 2026-09-01): « 2026 : 4 870 MW (+0,8 % par rapport à 2025) »
- ✓ **E5** contradicts · `weather` Station Tunis-Carthage (osint, 2026-07-22): « Aucun épisode de chaleur exceptionnel par rapport à l'été 2025. »

### C3. A funded capacity-expansion project (market 2026-017) existed before the outage.

- ✓ **E6** supports · `jort_award_v1` Wayback Machine (archive, 2026-02-20): « Marché n° 2026-017 : extension de 450 MW de la centrale de Rades-Fictive. » · same origin as `news_jort_b`, `news_jort_c`, `news_jort_d`
- ✓ **E7** supports · `worldbank` Bailleur international (fictif) (foreign_mirror, 2026-06-30): « Composante 2 : extension de capacité, centrale de Rades-Fictive (marché n° 2026-017). »
- ✓ **E8** supports · `news_jort_b` Média fictif b (news, 2026-03-02): « le marché n° 2026-017 de 120 000 000 TND a été attribué » · same origin as `jort_award_v1`, `news_jort_c`, `news_jort_d`
- ✓ **E9** supports · `news_jort_c` Média fictif c (news, 2026-03-02): « le marché n° 2026-017 de 120 000 000 TND a été attribué » · same origin as `jort_award_v1`, `news_jort_b`, `news_jort_d`
- ✓ **E10** supports · `news_jort_d` Média fictif d (news, 2026-03-03): « le marché n° 2026-017 de 120 000 000 TND a été attribué » · same origin as `jort_award_v1`, `news_jort_b`, `news_jort_c`

### C4. No capacity has been added on the project site since the award.

- ✓ **E11** supports · `site_report` Contributeur anonyme (contributor, 2026-08-10): « terrain nu, aucun engin de chantier, aucune fondation visible »
- ✓ **E12** supports · `sentinel` Copernicus Sentinel-2 (analyse) (osint, 2026-09-05): « aucun changement de surface bâtie détecté »

### C5. The contract was awarded without a competitive tender.

- ✓ **E13** supports · `jort_award_v1` Wayback Machine (archive, 2026-02-20): « par procédure de gré à gré »
- ✓ **E14** supports · `tuneps_search` Wayback Machine (archive, 2026-02-15): « Aucun avis d'appel d'offres publié entre le 01/01/2025 et le 15/02/2026 pour cet objet. »
- ✓ **E15** supports · `audit` Cour des comptes (fictif) (audit, 2026-09-15): « Le recours au gré à gré pour le marché n° 2026-017 n'est pas justifié par une situation d'urgence documentée. »
- ✓ **E16** qualifies · `steg_procedure` STEG (official_live, 2026-09-18): « attribué conformément à la procédure d'urgence prévue par le décret n° 2026-0412 » · *self-serving: the publisher is a party and this helps it*

### C9. A documented emergency legally justified the direct award (gré à gré).

- ✓ **E17** supports · `steg_procedure` STEG (official_live, 2026-09-18): « attribué conformément à la procédure d'urgence prévue par le décret n° 2026-0412 » · *self-serving: the publisher is a party and this helps it*
- ✓ **E18** contradicts · `audit` Cour des comptes (fictif) (audit, 2026-09-15): « n'est pas justifié par une situation d'urgence documentée »
- ✓ **E23** absence (contradicts) · Journal Officiel (JORT): decrees, orders and official notices: nothing found for « décret n° 2026-0412 (all 2026 issues, decrees section) » (no capture stored)

## Expected records

What should exist in a register if the sub-claim were false (or true), and what the search found.

| Record | Register | If absent | Searches | Absence counted |
|---|---|---|---|---|
| C3.E1 Award notice for market 2026-017 in the JORT | jort | contradicts C3 | none | no |
| C4.E1 Progress reports or provisional acceptance of the works in the lender's project records | funder_records | supports C4 | none | no |
| C5.E1 TUNEPS tender notice for the Rades-Fictive extension, published before the award | tuneps | supports C5 | none | no |
| C9.E1 Decree n° 2026-0412 declaring the emergency, in the JORT | jort | contradicts C9 | none | yes |
| C11.E1 Erratum or rectification of the notice concerned | jort | contradicts C11 | none | no |
| C12.E1 Suspension, restructuring or extension of the project in the lender's records | funder_records | contradicts C12 | none | no |

## Timeline

- 2024-11-05 `benchmark` Wayback Machine (archive, 2024-11-05)
- 2026-02-15 `tuneps_search` Wayback Machine (archive, 2026-02-15)
- 2026-02-20 `jort_award_v1` Wayback Machine (archive, 2026-02-20) (first seen 2026-03-01)
- 2026-02-20 `jort_award_v2` JORT (fictif) (official_live, 2026-02-20) (first seen 2026-09-20)
- 2026-03-02 `news_jort_b` Média fictif b (news, 2026-03-02)
- 2026-03-02 `news_jort_c` Média fictif c (news, 2026-03-02)
- 2026-03-03 `news_jort_d` Média fictif d (news, 2026-03-03)
- 2026-06-30 `worldbank` Bailleur international (fictif) (foreign_mirror, 2026-06-30) (first seen 2026-09-10)
- 2026-07-21 **event** (C1): A major power outage occurred on 21/07/2026.
- 2026-07-21 `steg_communique` STEG (official_live, 2026-07-21)
- 2026-07-22 `weather` Station Tunis-Carthage (osint, 2026-07-22)
- 2026-07-22 `news_outage` Le Quotidien Fictif (news, 2026-07-22)
- 2026-07-23 `nightlights` NASA Black Marble (analyse) (osint, 2026-07-23)
- 2026-08-10 `site_report` Contributeur anonyme (contributor, 2026-08-10)
- 2026-09-01 `ins_peak` INS (fictif) (statistics, 2026-09-01)
- 2026-09-05 `sentinel` Copernicus Sentinel-2 (analyse) (osint, 2026-09-05)
- 2026-09-15 `audit` Cour des comptes (fictif) (audit, 2026-09-15)
- 2026-09-18 `steg_procedure` STEG (official_live, 2026-09-18)
- 2026-09-20 **rewritten version observed**: `jort_award_v2` differs from `jort_award_v1`

## Integrity

- Documents in store: 17; ledger entries: 27; head `<hash>`; chain intact.
