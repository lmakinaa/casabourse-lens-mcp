"""
Cap-weighted synthetic MASI proxy from WafaBourse constituents.

WafaBourse exposes daily OHLCV for every listed issuer but does not
expose a *daily* history of the MASI index itself (INDICE-GRAPH is
intraday-only). To compute a market beta we build the benchmark here:

    - Rank issuers by Capitalisation (VALEUR-FICHE).
    - Take top-N (default 30) — this covers >90% of total market cap.
    - Cap-weight them. Weights sum to 1 after restricting to the top-N.
    - Daily synthetic return = Σ w_i × r_i, where r_i is the log return
      of member i on adjusted close. Members with no return on a given
      date contribute 0 to the sum and their weight is re-normalised
      across the present members so the total weight stays 1.

This is a proxy, not the official MASI. The tool that consumes it
discloses the composition and weights so downstream readers know
exactly what benchmark they are getting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

from ..corporate_actions import CorporateActionService
from ._returns import ReturnSeries, build_return_series


@dataclass(frozen=True)
class BasketMember:
    symbol: str
    market_cap_mad: float
    weight: float  # share of the basket, 0-1


@dataclass(frozen=True)
class SyntheticBenchmark:
    name: str                        # e.g. "synthetic_masi_top30"
    members: Tuple[BasketMember, ...]
    returns: ReturnSeries             # symbol field set to `name`


def build_basket(provider, top_n: int = 30) -> List[BasketMember]:
    """Fetch all tickers, resolve market caps, keep top-N by cap."""
    tickers = provider.get_all_tickers() or []
    caps: Dict[str, float] = {}
    for row in tickers:
        sym = row.get("Symbol")
        if not sym:
            continue
        profile = provider.get_company_profile(sym)
        if not profile:
            continue
        cap = profile.get("Capitalisation")
        if cap and cap > 0:
            caps[sym] = float(cap)

    ranked = sorted(caps.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    total = sum(cap for _, cap in ranked)
    if total <= 0:
        return []
    return [
        BasketMember(symbol=sym, market_cap_mad=cap, weight=cap / total)
        for sym, cap in ranked
    ]


def build_synthetic_returns(
    service: CorporateActionService,
    provider,
    members: List[BasketMember],
    window_days: int,
    name: str = "synthetic_masi_top30",
) -> SyntheticBenchmark:
    """Construct the cap-weighted daily log-return series for the basket.

    Dates with no member returns are omitted. On dates where only a
    subset of members have a return, the present members' weights are
    renormalised so every basket-day has weight sum = 1.
    """
    if not members:
        return SyntheticBenchmark(
            name=name,
            members=tuple(),
            returns=ReturnSeries(symbol=name, dates=tuple(), returns=tuple()),
        )

    series_by_symbol: Dict[str, ReturnSeries] = {}
    for m in members:
        s = build_return_series(service, provider, m.symbol, window_days)
        if s.dates:
            series_by_symbol[m.symbol] = s

    if not series_by_symbol:
        return SyntheticBenchmark(
            name=name,
            members=tuple(members),
            returns=ReturnSeries(symbol=name, dates=tuple(), returns=tuple()),
        )

    date_index: Dict[date, Dict[str, float]] = {}
    for sym, s in series_by_symbol.items():
        for d, r in zip(s.dates, s.returns):
            date_index.setdefault(d, {})[sym] = r

    weights = {m.symbol: m.weight for m in members}
    ordered_dates: List[date] = sorted(date_index.keys())
    basket_returns: List[float] = []
    for d in ordered_dates:
        contributors = date_index[d]
        w_sum = sum(weights[s] for s in contributors if s in weights)
        if w_sum <= 0:
            basket_returns.append(0.0)
            continue
        r = sum(weights[s] / w_sum * r_i for s, r_i in contributors.items() if s in weights)
        basket_returns.append(r)

    return SyntheticBenchmark(
        name=name,
        members=tuple(members),
        returns=ReturnSeries(
            symbol=name,
            dates=tuple(ordered_dates),
            returns=tuple(basket_returns),
        ),
    )
