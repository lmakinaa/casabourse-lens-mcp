"""
Aligned log-return series for cross-ticker analytics.

Used by correlation, beta, and backtesting tools. Centralises three
concerns that every caller would otherwise re-implement inconsistently:

    1. Input: adjusted OHLCV series from CorporateActionService. Unadjusted
       closes would produce spurious returns across ex-div / split dates.
    2. Log returns, not simple returns: additive across time, symmetric,
       and the standard input for OLS beta and Pearson correlation.
    3. Calendar alignment: different tickers trade on different days (halts,
       IPO, suspension). Aligning on the intersection of trading dates is
       the only honest way to compute pairwise statistics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Sequence, Tuple

from ..corporate_actions import CorporateActionService


@dataclass(frozen=True)
class ReturnSeries:
    symbol: str
    dates: Tuple[date, ...]   # trading dates for which we have a return
    returns: Tuple[float, ...]  # log returns, same length as dates


def build_return_series(
    service: CorporateActionService,
    provider,
    symbol: str,
    window_days: int,
) -> ReturnSeries:
    """Fetch adjusted history and convert to a log-return series.

    window_days is the number of *returns* we target. We pull
    window_days + 1 closes so the first return is well-defined.
    """
    if window_days <= 1:
        raise ValueError(f"window_days must be > 1, got {window_days}")

    raw = provider.get_price_history(symbol)
    if not raw:
        return ReturnSeries(symbol=symbol, dates=(), returns=())

    bars, _report, _meta = service.adjust_history(symbol, raw)
    if len(bars) < 2:
        return ReturnSeries(symbol=symbol, dates=(), returns=())

    # Keep only the tail we need, plus one extra for the first diff.
    needed = min(window_days + 1, len(bars))
    tail = bars[-needed:]

    dates: List[date] = []
    returns: List[float] = []
    for prev, cur in zip(tail[:-1], tail[1:]):
        if prev.adjusted_close <= 0 or cur.adjusted_close <= 0:
            continue
        dates.append(cur.bar_date)
        returns.append(math.log(cur.adjusted_close / prev.adjusted_close))

    return ReturnSeries(
        symbol=symbol,
        dates=tuple(dates),
        returns=tuple(returns),
    )


def align_series(series: Sequence[ReturnSeries]) -> Dict[str, List[float]]:
    """Restrict every series to the intersection of trading dates.

    Returns a dict mapping symbol → returns, all lists the same length,
    ordered by the common date axis. Symbols with zero overlap return
    empty lists.
    """
    if not series:
        return {}

    common = set(series[0].dates)
    for s in series[1:]:
        common.intersection_update(s.dates)
    if not common:
        return {s.symbol: [] for s in series}

    ordered_dates = sorted(common)
    index = {d: i for i, d in enumerate(ordered_dates)}

    aligned: Dict[str, List[float]] = {}
    for s in series:
        bucket = [0.0] * len(ordered_dates)
        for d, r in zip(s.dates, s.returns):
            if d in index:
                bucket[index[d]] = r
        aligned[s.symbol] = bucket
    return aligned
