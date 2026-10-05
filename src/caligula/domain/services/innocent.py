"""Mandatory innocent explanations, per claim type.

An investigation that only looks for what incriminates finds it. Analysts
(Heuer's competing hypotheses) and courts alike require the lawful or benign
explanation of the same facts to be tested, and a publication that ignored
an obvious one is hard to defend. So every case carries, for its claim type,
the standard innocent explanations below. The analyst covers each with a
hypothesis or rules it out with a reason; code adds any it left out, as a
sub-claim to test (true = the innocent explanation holds) and a hypothesis
of kind `innocent`. Allegation hypotheses predict those sub-claims false.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from caligula.domain.model.claims import (
    Allegation,
    Bearing,
    ExpectedRecord,
    Hypothesis,
    HypothesisKind,
    SubClaim,
)
from caligula.domain.model.evidence import Relation


@dataclass(frozen=True)
class Explanation:
    id: str
    test: str  # the sub-claim to test, true when the innocent explanation holds
    hypothesis: str
    questions: tuple[str, ...]
    expected: tuple[ExpectedRecord, ...] = field(default=())


def _in(register: str, description: str) -> ExpectedRecord:
    """A record that should exist if the explanation were true: its absence contradicts it."""
    return ExpectedRecord(description=description, register_id=register, absence_means=Relation.CONTRADICTS)


EMERGENCY = Explanation(
    "emergency", "A documented emergency legally justified the non-competitive procedure.",
    "The direct award was a lawful emergency procedure.",
    ("Was an emergency decree or order published before the award?",
     "Did the procurement control body approve the derogation?"),
    (_in("jort", "Decree or order declaring the emergency, published before the award"),),
)
SOLE_SUPPLIER = Explanation(
    "sole_supplier", "Only one supplier could lawfully or technically deliver (exclusive rights, compatibility).",
    "The award went to the only possible supplier.",
    ("Is an exclusive right, licence or technical compatibility requirement documented?",),
)
PRICE_SHOCK = Explanation(
    "price_shock", "Market prices rose enough between the benchmark and the award to explain the price gap.",
    "The price reflects a market price shock, not inflation of the contract.",
    ("Did prices of the main inputs (equipment, materials, currency) rise over the period?",),
)
CLERICAL = Explanation(
    "clerical_error", "The discrepancy is a clerical error or an officially published correction (erratum).",
    "The figures differ because of an error that was, or can be, officially corrected.",
    ("Was an erratum or rectification published?", "Does the corrected figure match other records?"),
    (_in("jort", "Erratum or rectification of the notice concerned"),),
)
DELAY = Explanation(
    "documented_delay", "Delivery is delayed for documented reasons (force majeure, suspension, litigation), "
    "with the funds unspent or recoverable.",
    "The project is delayed, not abandoned, and the money is accounted for.",
    ("Is a suspension, amendment or extension of the contract documented?",
     "Were the funds returned, frozen or kept in the project account?"),
    (_in("funder_records", "Suspension, restructuring or extension of the project in the lender's records"),),
)
NOT_DISBURSED = Explanation(
    "not_disbursed", "The funds were never disbursed, or were returned.",
    "The money was not spent, so it could not be diverted.",
    ("Do the lender's or treasury's records show disbursements?",),
)
REALLOCATED = Explanation(
    "lawful_reallocation", "The funds were reallocated by a published decision (budget amendment, decree).",
    "The money was lawfully moved to another use.",
    ("Is there a published decision moving the funds?",),
    (_in("jort", "Decision or budget amendment reallocating the funds"),),
)
HOMONYM = Explanation(
    "homonym", "The matching names refer to different people or companies.",
    "The link rests on a name coincidence.",
    ("Do identifiers differ (registration number, address, dates, role)?",),
)
DECLARED = Explanation(
    "declared_interest", "The interest was declared and the official did not take part in the decision.",
    "The conflict was managed as the rules require.",
    ("Was the interest declared?", "Do the minutes show the official stepping aside?"),
)
LEGITIMATE_PURPOSE = Explanation(
    "legitimate_purpose", "The transactions have a documented, ordinary business purpose.",
    "The pattern has an ordinary commercial explanation.",
    ("Are the counterparties, goods and prices consistent with the declared activity?",),
)
FUNDING_DECLARED = Explanation(
    "funding_declared", "The foreign funding was declared and published as the law requires.",
    "The funding was lawful and disclosed.",
    ("Was the funding published and notified as required?",),
    (_in("official_site", "Publication of the funding by the recipient"),),
)
DEFINITION = Explanation(
    "different_definition", "The statement is accurate under another definition, period or source.",
    "The claim is true as its author meant it.",
    ("Which definition, period and source did the author use?",),
)
CONTEXT = Explanation(
    "out_of_context", "The quote was truncated or taken out of context.",
    "The full statement says something else.",
    ("What does the full original statement say?",),
)

# Matched on the claim type's name, so "corruption_procurement" gets the procurement set.
CATALOGUE: dict[str, tuple[Explanation, ...]] = {
    "procurement": (EMERGENCY, SOLE_SUPPLIER, PRICE_SHOCK, CLERICAL, DELAY),
    "public_funds": (NOT_DISBURSED, REALLOCATED, DELAY, CLERICAL),
    "conflict_of_interest": (HOMONYM, DECLARED),
    "financial_crime": (LEGITIMATE_PURPOSE, HOMONYM),
    "record_tampering": (CLERICAL,),
    "foreign_funding": (FUNDING_DECLARED, HOMONYM),
    "factual_statement": (DEFINITION, CONTEXT),
}


def explanations_for(claim_type: str) -> list[Explanation]:
    out: list[Explanation] = []
    for key, explanations in CATALOGUE.items():
        if key in claim_type:
            out += [e for e in explanations if e not in out]
    return out


def _next_id(prefix: str, taken: set[str]) -> str:
    n = 1
    while f"{prefix}{n}" in taken:
        n += 1
    return f"{prefix}{n}"


def ensure_innocent_explanations(allegation: Allegation) -> tuple[Allegation, list[str]]:
    """Add every standard innocent explanation the case neither covers nor rules out.

    Returns the completed allegation (a copy) and one note per explanation added."""
    a = allegation.model_copy(deep=True)
    handled = {h.explains for h in a.hypotheses} | {r.explanation_id for r in a.ruled_out if r.reason.strip()}
    notes = []
    for exp in explanations_for(a.claim_type):
        if exp.id in handled:
            continue
        cid = _next_id("C", {c.id for c in a.subclaims})
        hid = _next_id("H", {h.id for h in a.hypotheses})
        a.subclaims.append(SubClaim(id=cid, statement=exp.test, verification_questions=list(exp.questions),
                                    bearing=Bearing.FOR, expected_records=list(exp.expected)))
        for h in a.hypotheses:
            if h.kind == HypothesisKind.ALLEGATION:
                h.predicts[cid] = False
        a.hypotheses.append(Hypothesis(id=hid, statement=exp.hypothesis, predicts={cid: True},
                                       kind=HypothesisKind.INNOCENT, explains=exp.id))
        notes.append(f"added innocent explanation {exp.id} as {hid} (tested by {cid})")
    return a, notes
