"""
Reconciler — turns a set of candidate observations into a verdict.

Precedence policy (deterministic, documented):

  Authority ranking for the DIVIDEND AMOUNT field:
      manual > ammc > bourse_casablanca > wafabourse

  Authority ranking for the EX_DATE field:
      manual > bourse_casablanca > ammc > wafabourse

  Why different per field? Because AMMC publishes the legal
  declaration (amount is authoritative) but the exchange controls
  ex-date mechanics. Ignoring this distinction is how retail tools
  end up with "off by one day" errors that silently corrupt RSI.

  Disputes:
    - dividend amount diff > 1% between top-two sources → DISPUTED
    - ex_date diff > 3 days → DISPUTED
    - split ratio mismatch (any) → DISPUTED — splits are high-impact

  Defaults:
    - splits land in PENDING_REVIEW unless confirmed by >=2 sources
      OR a 'manual' confirmation exists
    - dividends from >=2 agreeing sources are CONFIRMED
    - single-source dividends default to CONFIRMED if source is
      authoritative or operational, else PENDING_REVIEW
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

from .events import (
    CandidateObservation,
    Confidence,
    CorporateAction,
    EventStatus,
    EventType,
)
from .store import CorporateActionStore

log = logging.getLogger(__name__)


# ── policy ────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReconciliationPolicy:
    """
    Per-field source priorities + dispute thresholds.

    Split into its own type so tests can instantiate non-default
    policies without monkey-patching module globals, and so the
    rules are inspectable at runtime.
    """

    amount_priority: Tuple[str, ...] = ("manual", "ammc", "bourse_casablanca", "wafabourse")
    date_priority: Tuple[str, ...] = ("manual", "bourse_casablanca", "ammc", "wafabourse")
    dividend_amount_tolerance_pct: float = 1.0    # > 1% diff → disputed
    ex_date_tolerance_days: int = 3
    split_requires_two_sources: bool = True


DEFAULT_POLICY = ReconciliationPolicy()


# ── entry point ───────────────────────────────────────────────


class Reconciler:
    """
    Re-materialises ca_events from ca_observations for a symbol.

    Idempotent: running reconcile twice with the same inputs produces
    identical rows. Cheap for single symbols; for bulk rebuilds use
    reconcile_all().
    """

    def __init__(
        self,
        store: CorporateActionStore,
        policy: ReconciliationPolicy = DEFAULT_POLICY,
    ) -> None:
        self._store = store
        self._policy = policy

    def reconcile_symbol(
        self,
        symbol: str,
        as_of: Optional[datetime] = None,
    ) -> List[CorporateAction]:
        """
        Rebuild the ca_events rows for `symbol` from its observations.
        If `as_of` is given, only observations with observed_at <= as_of
        are considered — this is the point-in-time guarantee.

        When as_of is given, results are NOT persisted (to avoid
        overwriting the current-truth view with a historical snapshot).
        When as_of is None, results are upserted into ca_events.
        """
        obs_rows = self._store.get_observations(symbol, as_of=as_of)
        grouped: Dict[Tuple[str, date], List[Tuple[int, CandidateObservation]]] = {}
        for obs_id, obs in obs_rows:
            key = (obs.event_type.value, obs.ex_date)
            grouped.setdefault(key, []).append((obs_id, obs))

        # Also group near-miss ex-dates: two observations within
        # ex_date_tolerance_days for the same event_type should be
        # considered for the same event (they might be the same event
        # with a date disagreement). We merge these buckets per
        # event_type using a simple sweep.
        merged = self._merge_near_miss_dates(grouped)

        events: List[CorporateAction] = []
        for (event_type_str, canonical_date), obs_list in merged.items():
            event = self._reconcile_bucket(
                symbol=symbol,
                event_type=EventType(event_type_str),
                canonical_date=canonical_date,
                observations=obs_list,
            )
            events.append(event)

        if as_of is None:
            for ev in events:
                self._store.upsert_event(ev)

        return sorted(events, key=lambda e: e.ex_date)

    # ── internals ──────────────────────────────────────────────

    def _merge_near_miss_dates(
        self,
        grouped: Dict[Tuple[str, date], List[Tuple[int, CandidateObservation]]],
    ) -> Dict[Tuple[str, date], List[Tuple[int, CandidateObservation]]]:
        """
        Merge buckets whose ex_dates are within ex_date_tolerance_days.

        Uses the date_priority source's date as the canonical ex_date
        for the merged bucket — so if bourse_casablanca says 2025-05-12
        and ammc says 2025-05-13, the bucket keys on 2025-05-12.
        """
        tolerance = self._policy.ex_date_tolerance_days
        if tolerance <= 0:
            return grouped

        merged: Dict[Tuple[str, date], List[Tuple[int, CandidateObservation]]] = {}

        by_type: Dict[str, List[Tuple[date, List[Tuple[int, CandidateObservation]]]]] = {}
        for (etype, ed), obs_list in grouped.items():
            by_type.setdefault(etype, []).append((ed, obs_list))

        for etype, entries in by_type.items():
            entries.sort(key=lambda x: x[0])
            i = 0
            while i < len(entries):
                base_date, base_obs = entries[i]
                bucket = list(base_obs)
                j = i + 1
                while j < len(entries) and (entries[j][0] - base_date).days <= tolerance:
                    bucket.extend(entries[j][1])
                    j += 1
                canonical = self._canonical_date(bucket)
                merged[(etype, canonical)] = bucket
                i = j

        return merged

    def _canonical_date(
        self, observations: List[Tuple[int, CandidateObservation]]
    ) -> date:
        """Pick ex_date from the highest-ranked date source present."""
        for source in self._policy.date_priority:
            for _, obs in observations:
                if obs.source == source:
                    return obs.ex_date
        return observations[0][1].ex_date

    def _reconcile_bucket(
        self,
        symbol: str,
        event_type: EventType,
        canonical_date: date,
        observations: List[Tuple[int, CandidateObservation]],
    ) -> CorporateAction:
        """Decide status + winning values for one (symbol, type, date) bucket."""
        warnings: List[str] = []
        winner_id: Optional[int] = None
        winner_source: Optional[str] = None

        # Choose the amount-side winner
        amount_winner = self._pick_by_priority(observations, self._policy.amount_priority)
        if amount_winner is None:
            # No ranked source — fall back to first observation
            winner_id, winner_obs = observations[0]
        else:
            winner_id, winner_obs = amount_winner

        winner_source = winner_obs.source

        amount = winner_obs.payload.get("amount") if event_type is EventType.DIVIDEND else None
        ratio = winner_obs.payload.get("ratio") if event_type is EventType.SPLIT else None
        subscription_price = winner_obs.payload.get("subscription_price")
        currency = winner_obs.payload.get("currency", "MAD")

        status = self._decide_status(
            event_type=event_type,
            observations=observations,
            warnings=warnings,
        )

        first_seen_at = min(obs.observed_at for _, obs in observations)
        confirmed_at = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            if status is EventStatus.CONFIRMED
            else None
        )

        return CorporateAction(
            symbol=symbol,
            event_type=event_type,
            ex_date=canonical_date,
            status=status,
            amount=amount,
            ratio=ratio,
            subscription_price=subscription_price,
            currency=currency,
            winning_observation_id=winner_id,
            winning_source=winner_source,
            first_seen_at=first_seen_at,
            confirmed_at=confirmed_at,
            warnings=tuple(warnings),
        )

    def _pick_by_priority(
        self,
        observations: List[Tuple[int, CandidateObservation]],
        priority: Tuple[str, ...],
    ) -> Optional[Tuple[int, CandidateObservation]]:
        for source in priority:
            for obs_id, obs in observations:
                if obs.source == source:
                    return obs_id, obs
        return None

    def _decide_status(
        self,
        event_type: EventType,
        observations: List[Tuple[int, CandidateObservation]],
        warnings: List[str],
    ) -> EventStatus:
        sources = {obs.source for _, obs in observations}
        has_manual = "manual" in sources
        confidences = {obs.confidence for _, obs in observations}

        if event_type is EventType.DIVIDEND:
            amounts = [
                obs.payload["amount"]
                for _, obs in observations
                if "amount" in obs.payload
            ]
            if len(amounts) >= 2:
                lo, hi = min(amounts), max(amounts)
                if hi > 0 and (hi - lo) / hi * 100 > self._policy.dividend_amount_tolerance_pct:
                    warnings.append(
                        f"dividend amount disagreement across sources: "
                        f"min={lo} max={hi} (> {self._policy.dividend_amount_tolerance_pct}%)"
                    )
                    return EventStatus.DISPUTED

            # Ex-date spread
            dates = sorted({obs.ex_date for _, obs in observations})
            if len(dates) >= 2 and (dates[-1] - dates[0]).days > self._policy.ex_date_tolerance_days:
                warnings.append(
                    f"ex_date disagreement: {dates[0]}..{dates[-1]} "
                    f"(> {self._policy.ex_date_tolerance_days} days)"
                )
                return EventStatus.DISPUTED

            if has_manual or len(sources) >= 2:
                return EventStatus.CONFIRMED

            if Confidence.AUTHORITATIVE in confidences or Confidence.OPERATIONAL in confidences:
                return EventStatus.CONFIRMED

            return EventStatus.PENDING_REVIEW

        if event_type is EventType.SPLIT:
            ratios = {obs.payload.get("ratio") for _, obs in observations}
            ratios.discard(None)
            if len(ratios) > 1:
                warnings.append(f"split ratio mismatch across sources: {sorted(ratios)}")
                return EventStatus.DISPUTED

            if has_manual:
                return EventStatus.CONFIRMED
            if self._policy.split_requires_two_sources and len(sources) < 2:
                warnings.append("split confirmation requires at least two sources")
                return EventStatus.PENDING_REVIEW
            return EventStatus.CONFIRMED

        # Capital increases / rights issues — v1 always pending
        warnings.append(f"{event_type.value} requires manual confirmation in v1")
        return EventStatus.PENDING_REVIEW
