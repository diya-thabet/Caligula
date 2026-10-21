"""Procurement records (awards, tenders, companies) and screening results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
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
class Flag:
    code: str
    weight: float
    detail: str


@dataclass
class Screening:
    subject_id: str  # award id or company id
    score: float
    flags: list[Flag] = field(default_factory=list)


class Company(BaseModel):
    id: str
    name: str
    registered_at: datetime | None = None
    capital_tnd: float | None = None
    address: str | None = None
    managers: list[str] = Field(default_factory=list)
    owners: list[str] = Field(default_factory=list)  # beneficial owners as declared in the register


class Tender(BaseModel):
    id: str
    buyer: str
    bidder_ids: list[str]
    award_id: str | None = None
    signatories: list[str] = Field(default_factory=list)  # officials who signed or chaired the award
