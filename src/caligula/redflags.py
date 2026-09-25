"""Procurement red flags: deterministic screening of award records.

This is the proactive side of "suspecting a shady case": scan published awards
(TUNEPS, JORT) and rank the ones worth opening an investigation on. The
indicators follow the integrity red-flag literature (open procurement data
projects such as DIGIWHIST / opentender): non-competitive procedure, missing
tender notice, single bidder, rushed deadlines, newly created suppliers, price
above estimate, inflating amendments, splitting under thresholds, and one
supplier dominating a buyer.

A red flag is a reason to look, not evidence of wrongdoing: emergencies,
niche markets and small towns produce flags innocently. Flags describe awards
and companies, never individuals. Thresholds are configurable because legal
thresholds change with the procurement decree in force.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field


class Procedure(StrEnum):
    OPEN = "open"
    RESTRICTED = "restricted"
    NEGOTIATED = "negotiated"  # gré à gré
    DIRECT = "direct"
    EMERGENCY = "emergency"


NON_COMPETITIVE = {Procedure.NEGOTIATED, Procedure.DIRECT, Procedure.EMERGENCY}


class Award(BaseModel):
    id: str
    buyer: str
    supplier: str
    object: str
    amount_tnd: float
    procedure: Procedure
    award_date: datetime
    notice_published_at: datetime | None = None
    submission_deadline: datetime | None = None
    estimated_value_tnd: float | None = None
    bids: int | None = None
    supplier_registered_at: datetime | None = None
    amendments_tnd: list[float] = Field(default_factory=list)
    source_doc_ids: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class Thresholds:
    min_submission_days: int = 21
    new_company_days: int = 365
    over_estimate_ratio: float = 0.10
    amendment_ratio: float = 0.20
    # Awards within this fraction below the competitive-tender threshold, repeated
    # for the same buyer and supplier within `split_window_days`, suggest splitting.
    tender_threshold_tnd: float = 200_000
    split_margin: float = 0.15
    split_window_days: int = 90
    dominance_share: float = 0.5
    dominance_min_awards: int = 3


@dataclass(frozen=True)
class Flag:
    code: str
    weight: float
    detail: str


@dataclass
class Screening:
    award_id: str
    score: float
    flags: list[Flag] = field(default_factory=list)


WEIGHTS = {
    "non_competitive_procedure": 1.0,
    "no_prior_notice": 1.5,
    "single_bidder": 1.0,
    "short_submission_period": 0.75,
    "new_supplier": 1.0,
    "price_above_estimate": 1.0,
    "inflating_amendments": 1.25,
    "possible_splitting": 1.25,
    "supplier_dominance": 0.75,
    "timeline_inconsistency": 1.5,
}


def _flag(code: str, detail: str) -> Flag:
    return Flag(code, WEIGHTS[code], detail)


def screen_award(a: Award, t: Thresholds) -> list[Flag]:
    flags = []
    if a.procedure in NON_COMPETITIVE:
        flags.append(_flag("non_competitive_procedure", f"procedure: {a.procedure}"))
    if a.notice_published_at is None and a.procedure not in {Procedure.DIRECT, Procedure.EMERGENCY}:
        flags.append(_flag("no_prior_notice", "no tender notice found before the award"))
    if a.notice_published_at and a.notice_published_at > a.award_date:
        flags.append(_flag("timeline_inconsistency", "tender notice dated after the award"))
    if a.bids == 1:
        flags.append(_flag("single_bidder", "only one bid received"))
    if a.notice_published_at and a.submission_deadline:
        days = (a.submission_deadline - a.notice_published_at).days
        if days < t.min_submission_days:
            flags.append(_flag("short_submission_period", f"{days} days to submit"))
    if a.supplier_registered_at:
        age = (a.award_date - a.supplier_registered_at).days
        if age < 0:
            flags.append(_flag("timeline_inconsistency", "supplier registered after the award"))
        elif age < t.new_company_days:
            flags.append(_flag("new_supplier", f"supplier registered {age} days before the award"))
    if a.estimated_value_tnd and a.amount_tnd > a.estimated_value_tnd * (1 + t.over_estimate_ratio):
        pct = a.amount_tnd / a.estimated_value_tnd - 1
        flags.append(_flag("price_above_estimate", f"{pct:.0%} above the estimate"))
    if a.amendments_tnd and sum(a.amendments_tnd) > a.amount_tnd * t.amendment_ratio:
        pct = sum(a.amendments_tnd) / a.amount_tnd
        flags.append(_flag("inflating_amendments", f"amendments add {pct:.0%} to the award"))
    return flags


def _splitting(awards: list[Award], t: Thresholds) -> dict[str, Flag]:
    low = t.tender_threshold_tnd * (1 - t.split_margin)
    near = [a for a in awards if low <= a.amount_tnd < t.tender_threshold_tnd]
    groups: dict[tuple[str, str], list[Award]] = defaultdict(list)
    for a in near:
        groups[(a.buyer, a.supplier)].append(a)
    out = {}
    for group in groups.values():
        group.sort(key=lambda a: a.award_date)
        for a in group:
            window = [b for b in group if abs(b.award_date - a.award_date) <= timedelta(days=t.split_window_days)]
            if len(window) >= 2:
                total = sum(b.amount_tnd for b in window)
                out[a.id] = _flag(
                    "possible_splitting",
                    f"{len(window)} awards just under the {t.tender_threshold_tnd:,.0f} TND threshold "
                    f"to the same supplier within {t.split_window_days} days (total {total:,.0f} TND)",
                )
    return out


def _dominance(awards: list[Award], t: Thresholds) -> dict[str, Flag]:
    by_buyer: dict[str, list[Award]] = defaultdict(list)
    for a in awards:
        by_buyer[a.buyer].append(a)
    out = {}
    for buyer_awards in by_buyer.values():
        total = sum(a.amount_tnd for a in buyer_awards)
        by_supplier: dict[str, list[Award]] = defaultdict(list)
        for a in buyer_awards:
            by_supplier[a.supplier].append(a)
        for supplier_awards in by_supplier.values():
            share = sum(a.amount_tnd for a in supplier_awards) / total
            if len(supplier_awards) >= t.dominance_min_awards and share > t.dominance_share:
                for a in supplier_awards:
                    out[a.id] = _flag("supplier_dominance", f"supplier holds {share:.0%} of this buyer's awarded value")
    return out


def screen(awards: list[Award], thresholds: Thresholds | None = None) -> list[Screening]:
    """Screenings with at least one flag, highest score first."""
    t = thresholds or Thresholds()
    portfolio = [_splitting(awards, t), _dominance(awards, t)]
    results = []
    for a in awards:
        flags = screen_award(a, t) + [p[a.id] for p in portfolio if a.id in p]
        if flags:
            results.append(Screening(award_id=a.id, score=round(sum(f.weight for f in flags), 2), flags=flags))
    return sorted(results, key=lambda s: (-s.score, s.award_id))
