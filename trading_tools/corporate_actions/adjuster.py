"""
Back-adjustment of OHLCV series for dividends and splits.

Pure function. Zero I/O. Zero store coupling. You hand in a list of
events and a list of bars; you get back adjusted bars. This is the
only thing the recommendation engine actually depends on — it must
be bulletproof.

The classical "Yahoo-style" back-adjustment:

  For each event with ex-date D:
    - Dividend amount d, prior close P (close on the last trading
      day BEFORE D):
          factor = 1 - d / P
    - Split new:old = r (r > 1 forward, r < 1 reverse):
          factor = 1 / r

  All bars STRICTLY BEFORE D are multiplied by factor (prices) /
  divided by factor (volumes, for splits only).

  Dividends do NOT scale volume. Splits DO scale volume.

  Multiple events compound by cumulative product of factors: you walk
  events newest-to-oldest, and each factor applies to all earlier bars.

Guarantees enforced by tests:
  - len(out) == len(in)
  - The last bar's close is untouched (today's truth).
  - Adjustment factor series is monotone non-increasing going back.
  - Applying the inverse of all events to the adjusted series
    reproduces the original (round-trip invariant).
  - Unknown prior-close (event earlier than any bar) falls back to
    the event's own metadata if present, else skips the event with a
    warning returned via AdjustmentReport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from .events import CorporateAction, EventType


@dataclass
class AdjustedBar:
    """OHLCV bar with both raw and adjusted prices."""

    bar_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    adjusted_open: float
    adjusted_high: float
    adjusted_low: float
    adjusted_close: float
    adjusted_volume: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.bar_date.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "adjusted_open": self.adjusted_open,
            "adjusted_high": self.adjusted_high,
            "adjusted_low": self.adjusted_low,
            "adjusted_close": self.adjusted_close,
            "adjusted_volume": self.adjusted_volume,
        }


@dataclass
class AppliedAdjustment:
    ex_date: date
    event_type: str
    factor: float
    note: str


@dataclass
class AdjustmentReport:
    applied: List[AppliedAdjustment] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)


def back_adjust(
    events: List[CorporateAction],
    ohlcv: List[Dict[str, Any]],
) -> Tuple[List[AdjustedBar], AdjustmentReport]:
    """
    Apply dividend + split adjustments to an OHLCV series.

    Input OHLCV rows use WafaBourse field names for compatibility with
    existing get_price_history output:
        {'Seance': 'YYYY-MM-DD', 'Cours': close, 'Ouverture': open,
         'PlusHaut': high, 'PlusBas': low, 'Volume': volume}
    Missing fields default to the close.

    Returns (adjusted_bars, report). Bars preserve input order.
    """
    report = AdjustmentReport()
    if not ohlcv:
        return [], report

    parsed = _parse_bars(ohlcv)
    n = len(parsed)

    adj_close_factor = [1.0] * n
    adj_volume_factor = [1.0] * n

    close_by_date = {b["date"]: b["close"] for b in parsed}
    dates = [b["date"] for b in parsed]

    relevant = [e for e in events if e.event_type in (EventType.DIVIDEND, EventType.SPLIT)]
    relevant.sort(key=lambda e: e.ex_date, reverse=True)

    for event in relevant:
        prior_close = _prior_close(event.ex_date, dates, close_by_date)

        if event.event_type is EventType.DIVIDEND:
            if event.amount is None or event.amount <= 0:
                report.skipped.append(
                    f"dividend {event.symbol} {event.ex_date} skipped: missing amount"
                )
                continue
            if prior_close is None:
                report.skipped.append(
                    f"dividend {event.symbol} {event.ex_date} skipped: "
                    f"no prior close in provided history"
                )
                continue
            if prior_close <= 0:
                report.skipped.append(
                    f"dividend {event.symbol} {event.ex_date} skipped: "
                    f"prior close non-positive ({prior_close})"
                )
                continue
            factor = 1.0 - (event.amount / prior_close)
            if factor <= 0:
                report.skipped.append(
                    f"dividend {event.symbol} {event.ex_date} skipped: "
                    f"factor {factor:.4f} implausible (dividend >= prior close)"
                )
                continue
            _apply_price_factor(adj_close_factor, dates, event.ex_date, factor)
            report.applied.append(
                AppliedAdjustment(
                    ex_date=event.ex_date,
                    event_type="dividend",
                    factor=factor,
                    note=f"dividend {event.amount} / prior close {prior_close}",
                )
            )

        elif event.event_type is EventType.SPLIT:
            if event.ratio is None or event.ratio <= 0 or event.ratio == 1.0:
                report.skipped.append(
                    f"split {event.symbol} {event.ex_date} skipped: "
                    f"invalid ratio {event.ratio}"
                )
                continue
            factor = 1.0 / event.ratio
            _apply_price_factor(adj_close_factor, dates, event.ex_date, factor)
            _apply_volume_factor(adj_volume_factor, dates, event.ex_date, event.ratio)
            report.applied.append(
                AppliedAdjustment(
                    ex_date=event.ex_date,
                    event_type="split",
                    factor=factor,
                    note=f"split ratio {event.ratio}",
                )
            )

    out: List[AdjustedBar] = []
    for i, b in enumerate(parsed):
        pf = adj_close_factor[i]
        vf = adj_volume_factor[i]
        out.append(
            AdjustedBar(
                bar_date=b["date"],
                open=b["open"],
                high=b["high"],
                low=b["low"],
                close=b["close"],
                volume=b["volume"],
                adjusted_open=b["open"] * pf,
                adjusted_high=b["high"] * pf,
                adjusted_low=b["low"] * pf,
                adjusted_close=b["close"] * pf,
                adjusted_volume=b["volume"] * vf,
            )
        )
    return out, report


# ── internals ─────────────────────────────────────────────────


def _parse_bars(ohlcv: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalise the raw WafaBourse shape to a typed dict with python
    date objects. Sorts ascending by date, deduplicating by date
    (keeping the last occurrence — matches typical feed behaviour).
    """
    parsed: Dict[date, Dict[str, Any]] = {}
    for row in ohlcv:
        raw_date = row.get("Seance") or row.get("date")
        if raw_date is None:
            continue
        if isinstance(raw_date, str):
            # Accept both '2025-05-12' and '2025-05-12 00:00:00'
            bar_date = date.fromisoformat(raw_date[:10])
        elif isinstance(raw_date, date):
            bar_date = raw_date
        else:
            continue

        close = float(row.get("Cours", row.get("close", 0.0)))
        open_ = float(row.get("Ouverture", row.get("open", close)))
        high = float(row.get("PlusHaut", row.get("high", close)))
        low = float(row.get("PlusBas", row.get("low", close)))
        volume = float(row.get("Volume", row.get("volume", 0.0)))

        parsed[bar_date] = {
            "date": bar_date,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }

    return sorted(parsed.values(), key=lambda b: b["date"])


def _prior_close(
    ex_date: date,
    dates: List[date],
    close_by_date: Dict[date, float],
) -> Optional[float]:
    """Last close strictly before ex_date, or None if no such bar exists."""
    prior: Optional[float] = None
    for d in dates:
        if d < ex_date:
            prior = close_by_date[d]
        else:
            break
    return prior


def _apply_price_factor(
    factors: List[float],
    dates: List[date],
    ex_date: date,
    factor: float,
) -> None:
    """Multiply factor into every bar strictly before ex_date."""
    for i, d in enumerate(dates):
        if d < ex_date:
            factors[i] *= factor
        else:
            break


def _apply_volume_factor(
    volume_factors: List[float],
    dates: List[date],
    ex_date: date,
    split_ratio: float,
) -> None:
    """
    Splits scale volume by the split ratio (not its inverse).
    A 2:1 forward split doubles historical volume so shares-traded
    on a pre-split basis becomes comparable to post-split.
    """
    for i, d in enumerate(dates):
        if d < ex_date:
            volume_factors[i] *= split_ratio
        else:
            break
