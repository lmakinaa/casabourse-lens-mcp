"""
CorporateActionService — the read-side service TradingTools consumes.

Composes: CorporateActionStore (persistence) + Reconciler (policy) +
back_adjust (pure math). The MCP tools depend on this class, not on
the store directly — so we can swap storage backends without touching
tool handlers.

Point-in-time semantics:
  - `get_events(as_of=T)` returns what we believed at time T,
    computed by re-reconciling the observations filtered by
    observed_at <= T. Does not mutate ca_events.
  - `get_events(as_of=None)` returns current truth from ca_events.

Stale reads:
  - If current truth exists and as_of is None, reads are O(events).
  - If as_of is given, reads re-run reconciliation. Still fast for
    single symbols (SQLite handles tens of thousands of observations
    per symbol trivially).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .adjuster import AdjustedBar, AdjustmentReport, back_adjust
from .events import CorporateAction, EventType
from .reconciler import Reconciler
from .store import CorporateActionStore

log = logging.getLogger(__name__)


class CorporateActionService:
    """Read-path service for corporate-action-aware tools."""

    def __init__(
        self,
        store: CorporateActionStore,
        reconciler: Optional[Reconciler] = None,
    ) -> None:
        self._store = store
        self._reconciler = reconciler or Reconciler(store)

    def get_events(
        self,
        symbol: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        event_types: Optional[Iterable[EventType]] = None,
        as_of: Optional[datetime] = None,
        include_pending: bool = False,
    ) -> Tuple[List[CorporateAction], Dict[str, Any]]:
        """
        Returns (events, metadata). Metadata carries coverage +
        as_of + warnings, so callers can surface provenance.
        """
        symbol = symbol.strip().upper()
        if as_of is None:
            events = self._store.get_events(
                symbol,
                from_date=from_date,
                to_date=to_date,
                event_types=event_types,
                include_pending=include_pending,
            )
            as_of_label = "current"
        else:
            reconciled = self._reconciler.reconcile_symbol(symbol, as_of=as_of)
            events = [
                e
                for e in reconciled
                if (from_date is None or e.ex_date >= from_date)
                and (to_date is None or e.ex_date <= to_date)
                and (event_types is None or e.event_type in set(event_types))
                and (include_pending or e.status.value == "confirmed")
            ]
            as_of_label = as_of.isoformat()

        coverage = self._store.coverage(symbol)
        warnings = [w for e in events for w in e.warnings]

        metadata = {
            "symbol": symbol,
            "as_of": as_of_label,
            "coverage": coverage,
            "warnings": warnings,
            "event_count": len(events),
        }
        return events, metadata

    def adjust_history(
        self,
        symbol: str,
        ohlcv: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
        include_pending: bool = False,
    ) -> Tuple[List[AdjustedBar], AdjustmentReport, Dict[str, Any]]:
        """Fetch events, apply back-adjustment, return (bars, report, metadata)."""
        events, metadata = self.get_events(
            symbol,
            as_of=as_of,
            include_pending=include_pending,
        )
        bars, report = back_adjust(events, ohlcv)
        metadata = {
            **metadata,
            "adjustments_applied": len(report.applied),
            "adjustments_skipped": len(report.skipped),
        }
        return bars, report, metadata
