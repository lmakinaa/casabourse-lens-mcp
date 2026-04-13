"""
ManualAgent — produces observations from structured input (CLI, JSON file).

No scraping, no LLM. The operator is the source of truth; we record
that fact by tagging observations with source='manual' and
confidence='manual'. These will reconcile into CONFIRMED events if
the operator explicitly marks them confirmed, otherwise pending.

Useful for:
  - Seeding the store before scrapers exist
  - Overriding a disputed event after the operator has verified
    against AMMC or the issuer's press release
  - One-off corrections
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from trading_tools.corporate_actions import (
    CandidateObservation,
    Confidence,
    EventType,
)


class ManualAgent:
    """Turns structured input into CandidateObservation rows."""

    SOURCE = "manual"

    def __init__(self, operator: Optional[str] = None) -> None:
        self._operator = operator or "unknown"

    def from_dict(self, entries: Iterable[Dict[str, Any]]) -> List[CandidateObservation]:
        out: List[CandidateObservation] = []
        for raw in entries:
            out.append(self._one(raw))
        return out

    def _one(self, raw: Dict[str, Any]) -> CandidateObservation:
        symbol = str(raw["symbol"]).strip().upper()
        event_type = EventType(str(raw["event_type"]).strip().lower())
        ex_date = _to_date(raw["ex_date"])

        payload: Dict[str, Any] = {}
        if event_type is EventType.DIVIDEND:
            payload["amount"] = float(raw["amount"])
            if "currency" in raw:
                payload["currency"] = str(raw["currency"]).upper()
        elif event_type is EventType.SPLIT:
            payload["ratio"] = float(raw["ratio"])
        elif event_type in (EventType.CAPITAL_INCREASE, EventType.RIGHTS_ISSUE):
            if "subscription_price" in raw:
                payload["subscription_price"] = float(raw["subscription_price"])
            if "ratio" in raw:
                payload["ratio"] = float(raw["ratio"])

        return CandidateObservation(
            symbol=symbol,
            event_type=event_type,
            ex_date=ex_date,
            payload=payload,
            source=self.SOURCE,
            confidence=Confidence.MANUAL,
            source_ref=f"operator={self._operator}",
            source_url=raw.get("source_url"),
        )


def _to_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise TypeError(f"ex_date must be date or ISO string, got {type(value).__name__}")
