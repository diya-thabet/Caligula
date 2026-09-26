"""What every analyst adapter shares, whatever the model provider: the prompts,
the output schemas, and the conversion of outputs into domain objects.

An adapter only implements `_parse(system, prompt, schema)`: one call that
returns an instance of `schema`. The analyst is never asked whether an
allegation is true; every edge and amount it proposes is validated in code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypeVar

from pydantic import BaseModel

from caligula.domain.model.attribution import JudgeRating
from caligula.domain.model.claims import Allegation, Hypothesis, HypothesisKind, Party, RuledOut, SubClaim
from caligula.domain.model.documents import Document
from caligula.domain.model.evidence import AmountRole, EvidenceEdge, FinancialFigure, Relation
from caligula.domain.model.intake import ClaimType, Intake
from caligula.domain.model.registers import REGISTERS
from caligula.domain.services.innocent import CATALOGUE

if TYPE_CHECKING:
    from caligula.application.investigation.plan import PlanDraft

T = TypeVar("T", bound=BaseModel)


class RefusalError(RuntimeError):
    """The model declined the request."""


# Output schemas. Structured outputs need explicit objects, not free-form maps,
# so these differ slightly from the domain models.
class Prediction(BaseModel):
    subclaim_id: str
    predicted_true: bool


class HypothesisOut(BaseModel):
    id: str
    statement: str
    predictions: list[Prediction]
    kind: Literal["allegation", "innocent", "alternative"]
    explains: str | None  # standard innocent explanation id, for kind "innocent"


class Decomposition(BaseModel):
    subject: str
    claim_type: ClaimType
    subclaims: list[SubClaim]
    hypotheses: list[HypothesisOut]
    core_subclaims: list[str]
    financial_subclaim: str | None
    parties: list[Party]
    ruled_out: list[RuledOut]


class EdgeOut(BaseModel):
    subclaim_id: str
    relation: Literal["supports", "contradicts", "qualifies"]
    quote: str
    rationale: str


class AmountOut(BaseModel):
    role: Literal["allocated", "disbursed", "benchmark", "proven_spend"]
    amount_tnd: float
    quote: str


class Reading(BaseModel):
    edges: list[EdgeOut]
    amounts: list[AmountOut]


DECOMPOSE_SYSTEM = """\
You plan investigations of public-interest allegations (procurement, public \
funds, official statements). You never judge whether an allegation is true. \
Your job is to break it into atomic, independently checkable sub-claims and \
to state what evidence would settle each one.

Rules:
- Each sub-claim is one factual proposition with ids C1, C2, ...
- Separate facts (an award happened, an amount was paid) from inferences \
(funds were misappropriated). The causal inference is its own sub-claim.
- For each sub-claim, write verification questions that name concrete record \
types (JORT issue, TUNEPS notice, funder disbursement record, audit report, \
statistics series, satellite imagery, field photo).
- Propose competing hypotheses and for each one say which sub-claims it \
predicts true or false. A good hypothesis set lets evidence falsify some of \
them. kind: "allegation" for the wrongdoing as alleged, "innocent" for a \
lawful or benign explanation of the same facts, "alternative" for other \
explanations of a fact (such as the cause of an outage).
- Standard innocent explanations for the claim type (listed below) are \
mandatory: cover each one with an innocent hypothesis (explains = its id) \
tested by a sub-claim that is true when the explanation holds, or rule it \
out in ruled_out with a concrete reason. Code adds any you skip.
- core_subclaims: the factual sub-claims that must all hold for the allegation \
to warrant further scrutiny. Exclude the causal inference.
- financial_subclaim: the sub-claim about an amount being inflated or \
unaccounted for, or null if there is none.
- expected_records: for each sub-claim, the records that should exist if it \
were false (or true), in a register that would list them: a tender notice, \
an emergency decree, a disbursement record, a company registration. \
register_id is one of: {registers}. absence_means says what finding \
nothing would mean for the sub-claim (supports or contradicts). Only \
registers where absence is informative; skip the rest.
- bearing of each sub-claim: "against" if its truth incriminates the party \
whose conduct is at issue, "for" if it would clear them (an innocent \
explanation), "neutral" for context.
- parties: the bodies, companies or offices whose conduct is at issue (role \
accused) and whoever makes the allegation, if known (role complainant), with \
every name they publish under (acronyms, French and English forms). What they \
publish is weighed as an interested statement.

Standard innocent explanations (claim type: id: explanation):
{innocent}""".replace(
    "{registers}", ", ".join(f"{k} ({r.name})" for k, r in REGISTERS.items())
).replace(
    "{innocent}", "\n".join(f"- {t}: {e.id}: {e.test}" for t, exps in CATALOGUE.items() for e in exps))

READ_SYSTEM = """\
You read one document for an investigation. For each listed sub-claim, decide \
whether this document supports it, contradicts it, or qualifies it (adds a \
condition or innocent explanation). Skip sub-claims the document does not \
address; returning no edges is a valid answer.

Rules:
- quote must be copied exactly from the document, long enough to be \
unambiguous. Code checks every quote; paraphrases are rejected.
- Absence counts only when the document is a search result or register that \
would list the item if it existed.
- amounts: extract monetary amounts in Tunisian dinars relevant to the \
allegation, with the exact quote containing the number and its role: \
allocated (awarded or budgeted), disbursed (paid out), benchmark (market or \
comparable price), proven_spend (documented actual cost).
- Do not infer intent or name culprits."""


CLASSIFY_SYSTEM = """\
You triage requests sent to Caligula, a Tunisian public-interest fact-checking \
and investigation project. Describe the request; do not judge it or decide \
whether to accept it.

- claim_type: the closest category. Use espionage_or_state_security for any \
accusation of spying, treason, foreign agency or threats to state security, \
and private_life for claims about someone's private conduct.
- subject_types: everyone and everything the claim is about.
- public_nexus: true only if the claim involves public money, a public office \
or body acting in that capacity, a public contract, or a public statement.
- documented_act: true only if the claim refers to a specific act that \
happened or is happening (a contract, payment, decision, statement), false \
for predictions, suspicions about intentions, or general profiles.
- relies_on_sensitive_traits: true if suspicion rests on religion, health, \
ethnicity, sexuality, origin or political opinion.
- involves_leaked_or_classified_material: true if the request relies on or \
offers leaked, confidential or classified documents."""

DECOMPOSE_LANGUAGE = """

Write sub-claims, hypotheses and questions in the language of the allegation \
(French or English)."""


PLAN_SYSTEM = """\
You are the lead investigator of a Caligula case. Sub-claims and hypotheses \
are settled; now plan the evidence collection for a team of source \
specialists who work in parallel:

- official: Journal Officiel (JORT), TUNEPS procurement notices, ministry and \
state-company sites, and archived versions of all of these
- funders_audit: World Bank and other lenders' records, audit reports, statistics
- web_news: news articles and investigative reports (French and English)
- social: public posts by officials, institutions and companies
- telegram: public Telegram channels (leads and first appearances only)

Produce:
- entities: every company, public body, project, document reference and \
person central to the claim, with the spellings and aliases to search under \
(French and English forms, acronyms, reference numbers). Persons only in \
their public role or documented link.
- window_start / window_end: ISO dates bounding the relevant period.
- tasks: concrete, checkable assignments. Each task names its sub-claims, \
says exactly what to find, and gives search queries and known URLs. Cover \
every core sub-claim from at least two different kinds of source. Include \
at least one task that looks for the innocent explanation (purpose \
"challenge") of the central allegation. Prefer sources the accused cannot \
edit for amounts and dates.
- For every expected record listed under a sub-claim, one task that searches \
the named register for it, with expectation_id set to the record's id \
(e.g. "C5.E1"); code adds any you leave out.
- budget_weights: relative effort per specialist for this kind of case."""


JUDGE_SYSTEM = """\
You check one sentence of an investigation summary against the evidence it \
cites. The summary may be published about a public body, so a sentence that \
says more than its evidence is a legal risk. Be strict.

- supported: every factual element of the sentence (who, what, when, how \
much, how many, the procedure, the causal link) is stated in the quotes, \
possibly in other words or another language.
- partial: some elements are in the quotes, others are not (a stronger \
word, an added cause, a number or date the quotes do not give).
- unsupported: the quotes do not state the claim, or say something else.
- support_span: copy, exactly and in its original language, the words of \
one quote that carry the claim. Leave it empty unless supported or partial.
- missing: what the sentence asserts that no quote establishes, briefly; \
empty if nothing.

Use only the quotes, not what you know about the case or the world. \
Intentions, motives and blame are never in a quote unless it states them."""


class StructuredAnalyst:
    """`ClaimAnalyst` and `AttributionJudge` on top of one structured call, `_parse`,
    supplied by each provider adapter."""

    def _parse(self, system: str, prompt: str, schema: type[T]) -> T:
        raise NotImplementedError

    def classify(self, text: str) -> Intake:
        return self._parse(CLASSIFY_SYSTEM, f"<request>\n{text}\n</request>", Intake)

    def judge(self, sentence: str, evidence: list[tuple[str, str]]) -> JudgeRating:
        quotes = "\n".join(f'<quote id="{eid}">{text}</quote>' for eid, text in evidence)
        return self._parse(JUDGE_SYSTEM, f"<sentence>\n{sentence}\n</sentence>\n\n<evidence>\n{quotes}\n</evidence>",
                           JudgeRating)

    def plan(self, allegation: Allegation) -> PlanDraft:
        from caligula.application.investigation.plan import PlanDraft

        claims = "\n".join(
            f"{c.id}{' (core)' if c.id in allegation.core_subclaims else ''}: {c.statement} "
            f"| questions: {'; '.join(c.verification_questions)}"
            for c in allegation.subclaims
        )
        expected = "\n".join(f"{eid} ({cid}): {r.description} [register {r.register_id}, "
                             f"absence {r.absence_means} {cid}]" for eid, (cid, r) in allegation.expected().items())
        hyps = "\n".join(f"{h.id}: {h.statement} predicts {h.predicts}" for h in allegation.hypotheses)
        prompt = (f"<claim>\n{allegation.text}\n</claim>\n\n<subclaims>\n{claims}\n</subclaims>\n\n"
                  f"<hypotheses>\n{hyps}\n</hypotheses>\n\n<expected_records>\n{expected}\n</expected_records>")
        return self._parse(PLAN_SYSTEM, prompt, PlanDraft)

    def decompose(self, allegation_id: str, text: str) -> Allegation:
        d = self._parse(DECOMPOSE_SYSTEM + DECOMPOSE_LANGUAGE, f"<allegation>\n{text}\n</allegation>", Decomposition)
        # Drop references to sub-claims the model did not define, and unknown registers.
        known = {c.id for c in d.subclaims}
        for c in d.subclaims:
            c.expected_records = [r for r in c.expected_records if r.register_id in REGISTERS]
        return Allegation(
            id=allegation_id,
            text=text,
            subject=d.subject,
            claim_type=d.claim_type.value,
            subclaims=d.subclaims,
            hypotheses=[
                Hypothesis(
                    id=h.id,
                    statement=h.statement,
                    predicts={p.subclaim_id: p.predicted_true for p in h.predictions if p.subclaim_id in known},
                    kind=HypothesisKind(h.kind),
                    explains=h.explains if h.kind == "innocent" else None,
                )
                for h in d.hypotheses
            ],
            core_subclaims=[i for i in d.core_subclaims if i in known],
            financial_subclaim=d.financial_subclaim if d.financial_subclaim in known else None,
            parties=d.parties,
            ruled_out=d.ruled_out,
        )

    def read(self, allegation: Allegation, doc: Document) -> tuple[list[EvidenceEdge], list[FinancialFigure]]:
        claims = "\n".join(f"{c.id}: {c.statement}" for c in allegation.subclaims)
        published = doc.published_at.date().isoformat() if doc.published_at else "unknown"
        prompt = (
            f"<subclaims>\n{claims}\n</subclaims>\n\n"
            f'<document id="{doc.id}" publisher="{doc.publisher}" kind="{doc.source_kind}" '
            f'published="{published}" observed="{doc.observed_at.date().isoformat()}">\n'
            f"{doc.text}\n</document>"
        )
        r = self._parse(READ_SYSTEM, prompt, Reading)
        edges = [
            EvidenceEdge(
                doc_id=doc.id,
                subclaim_id=e.subclaim_id,
                relation=Relation(e.relation),
                quote=e.quote,
                rationale=e.rationale,
            )
            for e in r.edges
        ]
        figures = [
            FinancialFigure(doc_id=doc.id, role=AmountRole(a.role), amount_tnd=a.amount_tnd, quote=a.quote)
            for a in r.amounts
        ]
        return edges, figures
