"""Claude as investigator: it decomposes allegations and reads documents.

It is never asked whether an allegation is true. Every edge and amount it
proposes goes through `validate.py` before it can affect a score.
"""

from __future__ import annotations

from typing import Literal, TypeVar

import anthropic
from pydantic import BaseModel

from caligula.models import (
    Allegation,
    AmountRole,
    Document,
    EvidenceEdge,
    FinancialFigure,
    Hypothesis,
    Relation,
    SubClaim,
)

MODEL = "claude-opus-5"
# Route policy declines to Anthropic's recommended fallback model instead of failing the call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

T = TypeVar("T", bound=BaseModel)


class RefusalError(RuntimeError):
    pass


# Output schemas. Structured outputs need explicit objects, not free-form maps,
# so these differ slightly from the domain models.
class _Prediction(BaseModel):
    subclaim_id: str
    predicted_true: bool


class _Hypothesis(BaseModel):
    id: str
    statement: str
    predictions: list[_Prediction]


class _Decomposition(BaseModel):
    subject: str
    claim_type: str
    subclaims: list[SubClaim]
    hypotheses: list[_Hypothesis]
    core_subclaims: list[str]
    financial_subclaim: str | None


class _Edge(BaseModel):
    subclaim_id: str
    relation: Literal["supports", "contradicts", "qualifies"]
    quote: str
    rationale: str


class _Amount(BaseModel):
    role: Literal["allocated", "disbursed", "benchmark", "proven_spend"]
    amount_tnd: float
    quote: str


class _Reading(BaseModel):
    edges: list[_Edge]
    amounts: list[_Amount]


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
- Propose competing hypotheses, including innocent explanations, and for each \
one say which sub-claims it predicts true or false. A good hypothesis set lets \
evidence falsify some of them.
- core_subclaims: the factual sub-claims that must all hold for the allegation \
to warrant further scrutiny. Exclude the causal inference.
- financial_subclaim: the sub-claim about an amount being inflated or \
unaccounted for, or null if there is none."""

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


class ClaudeInvestigator:
    def __init__(self, client: anthropic.Anthropic | None = None, model: str = MODEL):
        self.client = client or anthropic.Anthropic()
        self.model = model

    def _parse(self, system: str, prompt: str, schema: type[T]) -> T:
        response = self.client.beta.messages.parse(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise RefusalError(f"request declined: {response.stop_details}")
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            raise RuntimeError(f"no parsable output (stop_reason={response.stop_reason})")
        return response.parsed_output

    def decompose(self, allegation_id: str, text: str) -> Allegation:
        d = self._parse(DECOMPOSE_SYSTEM, f"<allegation>\n{text}\n</allegation>", _Decomposition)
        # Drop references to sub-claims the model did not define.
        known = {c.id for c in d.subclaims}
        return Allegation(
            id=allegation_id,
            text=text,
            subject=d.subject,
            claim_type=d.claim_type,
            subclaims=d.subclaims,
            hypotheses=[
                Hypothesis(
                    id=h.id,
                    statement=h.statement,
                    predicts={p.subclaim_id: p.predicted_true for p in h.predictions if p.subclaim_id in known},
                )
                for h in d.hypotheses
            ],
            core_subclaims=[i for i in d.core_subclaims if i in known],
            financial_subclaim=d.financial_subclaim if d.financial_subclaim in known else None,
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
        r = self._parse(READ_SYSTEM, prompt, _Reading)
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
