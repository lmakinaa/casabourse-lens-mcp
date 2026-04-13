"""
Canonical corporate-action types.

Two layers:
  - CandidateObservation: what a scraper saw, pre-reconciliation. Raw,
    tagged with source + provenance. Many can exist per (symbol, type,
    ex_date) — that's the entire point of an append-only event log.
  - CorporateAction: the reconciler's verdict — the one row per
    (symbol, type, ex_date) the rest of the system should trust.

We keep these deliberately simple (dataclasses, not pydantic) so the
core has zero dependencies. Validation is a separate, explicit step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any, Dict, Optional


class EventType(str, Enum):
    DIVIDEND = "dividend"
    SPLIT = "split"
    CAPITAL_INCREASE = "capital_increase"
    RIGHTS_ISSUE = "rights_issue"


class Confidence(str, Enum):
    """
    Trust grade assigned to a source class.

    Does NOT replace reconciliation precedence (which is per-field) —
    it's metadata used to surface provenance to the LLM.
    """

    AUTHORITATIVE = "authoritative"   # AMMC (regulator), manual from primary doc
    OPERATIONAL = "operational"       # Bourse de Casablanca
    AGGREGATOR = "aggregator"         # WafaBourse, third-party feeds
    MANUAL = "manual"                 # user-entered, unverified


class EventStatus(str, Enum):
    CONFIRMED = "confirmed"
    PENDING_REVIEW = "pending_review"  # high-impact events default here (splits)
    DISPUTED = "disputed"              # sources disagree beyond tolerance
    SUPERSEDED = "superseded"          # an earlier verdict overwritten by better data


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class CandidateObservation:
    """
    A single observation of a corporate action from one source.

    Immutable by contract — observations are the event log; we never
    mutate rows, we only append new ones or mark them superseded.
    """

    symbol: str
    event_type: EventType
    ex_date: date
    payload: Dict[str, Any]           # amount / ratio / subscription_price / currency
    source: str                       # 'ammc' | 'bourse_casablanca' | 'wafabourse' | 'manual'
    confidence: Confidence
    source_url: Optional[str] = None
    source_ref: Optional[str] = None  # notice number, press-release id
    observed_at: str = field(default_factory=_utcnow_iso)

    def observation_hash(self) -> str:
        """
        Deterministic fingerprint for dedup. Same source re-emitting
        the same observation must produce the same hash, so repeated
        scrapes are idempotent at the DB layer.
        """
        parts = [
            self.symbol,
            self.event_type.value,
            self.ex_date.isoformat(),
            _canonical_payload_repr(self.payload),
            self.source,
            self.source_ref or "",
        ]
        return sha256("|".join(parts).encode("utf-8")).hexdigest()


def _canonical_payload_repr(payload: Dict[str, Any]) -> str:
    """Stable stringification — keys sorted, floats at fixed precision."""
    items = []
    for key in sorted(payload.keys()):
        value = payload[key]
        if isinstance(value, float):
            items.append(f"{key}={value:.6f}")
        else:
            items.append(f"{key}={value}")
    return ";".join(items)


@dataclass(frozen=True)
class CorporateAction:
    """
    Post-reconciliation event — the row the rest of the system trusts.

    Exactly one per (symbol, event_type, ex_date). Carries a pointer
    back to the winning observation so provenance can be surfaced.
    """

    symbol: str
    event_type: EventType
    ex_date: date
    status: EventStatus
    amount: Optional[float] = None              # dividend cash amount (per share)
    ratio: Optional[float] = None               # split ratio: new/old (2:1 → 2.0)
    subscription_price: Optional[float] = None  # rights / capital increase
    currency: str = "MAD"
    winning_observation_id: Optional[int] = None
    winning_source: Optional[str] = None
    first_seen_at: Optional[str] = None
    confirmed_at: Optional[str] = None
    warnings: tuple = ()                        # disputed-field notes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "event_type": self.event_type.value,
            "ex_date": self.ex_date.isoformat(),
            "status": self.status.value,
            "amount": self.amount,
            "ratio": self.ratio,
            "subscription_price": self.subscription_price,
            "currency": self.currency,
            "winning_source": self.winning_source,
            "first_seen_at": self.first_seen_at,
            "confirmed_at": self.confirmed_at,
            "warnings": list(self.warnings),
        }
