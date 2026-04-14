"""
Ingestion pipeline: validate → dedupe → persist → reconcile.

Agents produce CandidateObservation rows. This module is the only
thing that writes to the store and triggers reconciliation.

The pipeline is a plain class (not a framework) — scheduling is
someone else's job (cron, systemd, ad-hoc CLI). Each call is
independent and idempotent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, List, Optional

from trading_tools.corporate_actions import (
    CandidateObservation,
    CorporateActionStore,
    Reconciler,
    ValidationError,
    validate_observation,
)

log = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    accepted: int = 0
    duplicates: int = 0
    rejected: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    reconciled_symbols: List[str] = field(default_factory=list)


class IngestionPipeline:
    """
    Validate + persist observations, then re-reconcile affected symbols.

    Usage:
        pipeline = IngestionPipeline(store)
        result = pipeline.ingest([candidate, ...])
    """

    def __init__(
        self,
        store: CorporateActionStore,
        reconciler: Optional[Reconciler] = None,
        today: Optional[date] = None,
    ) -> None:
        self._store = store
        self._reconciler = reconciler or Reconciler(store)
        self._today = today

    def ingest(
        self,
        observations: Iterable[CandidateObservation],
    ) -> IngestionResult:
        """Run the pipeline once over a batch. Reconciles each affected symbol exactly once."""
        result = IngestionResult()
        touched_symbols: set[str] = set()
        today = self._today or date.today()

        for obs in observations:
            try:
                obs_warnings = validate_observation(obs, today=today)
            except ValidationError as err:
                log.warning(
                    "ingest.rejected",
                    extra={"symbol": obs.symbol, "source": obs.source, "error": str(err)},
                )
                result.rejected.append(f"{obs.symbol} {obs.source}: {err}")
                continue

            if obs_warnings:
                result.warnings.extend(
                    f"{obs.symbol} {obs.ex_date} ({obs.source}): {w}" for w in obs_warnings
                )

            _, created = self._store.record_observation_with_status(obs)
            if created:
                result.accepted += 1
            else:
                result.duplicates += 1

            touched_symbols.add(obs.symbol)

        for sym in sorted(touched_symbols):
            self._reconciler.reconcile_symbol(sym)
            result.reconciled_symbols.append(sym)

        log.info(
            "ingest.complete",
            extra={
                "accepted": result.accepted,
                "rejected": len(result.rejected),
                "reconciled_symbols": len(result.reconciled_symbols),
            },
        )
        return result
