"""
Rolling beta vs. a market benchmark.

We regress stock log-returns on benchmark log-returns:

    r_i = α + β · r_m + ε

Benchmark is either:
  - a synthetic cap-weighted basket of the top-N Casablanca issuers
    (default when no `benchmark` argument is provided — WafaBourse
    does not publish daily MASI history), or
  - another listed ticker (pass `benchmark="BCP"` for e.g. bank-sector
    beta). Useful for peer/sector hedging analysis.

Output is raw statistics only: β, intercept α, standard error of β,
R², sample size, and the basket composition if synthetic. The LLM
composes the interpretation; the tool does not.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Tuple

from ._context import ToolContext
from ._helpers import require_ca_service
from ._registry import tool
from ._returns import ReturnSeries, align_series, build_return_series
from ._synthetic_masi import (
    BasketMember,
    SyntheticBenchmark,
    build_basket,
    build_synthetic_returns,
)


SUPPORTED_WINDOWS = (30, 90, 180, 365)
DEFAULT_BASKET_SIZE = 30


def _ols_beta(
    stock_r: List[float],
    market_r: List[float],
) -> Dict[str, float]:
    """Return beta, alpha, standard error of beta, R^2, n."""
    n = len(stock_r)
    if n < 3:
        return {"beta": 0.0, "alpha": 0.0, "std_error": 0.0, "r_squared": 0.0, "n": n}

    mean_x = sum(market_r) / n
    mean_y = sum(stock_r) / n

    ss_xx = sum((x - mean_x) ** 2 for x in market_r)
    ss_yy = sum((y - mean_y) ** 2 for y in stock_r)
    ss_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(market_r, stock_r))

    if ss_xx == 0:
        return {"beta": 0.0, "alpha": 0.0, "std_error": 0.0, "r_squared": 0.0, "n": n}

    beta = ss_xy / ss_xx
    alpha = mean_y - beta * mean_x

    # Residual sum of squares, degrees of freedom n-2 for OLS simple reg.
    residuals = [y - (alpha + beta * x) for x, y in zip(market_r, stock_r)]
    rss = sum(r * r for r in residuals)
    df = n - 2
    if df <= 0:
        return {"beta": beta, "alpha": alpha, "std_error": 0.0, "r_squared": 0.0, "n": n}

    sigma2 = rss / df
    se_beta = math.sqrt(sigma2 / ss_xx) if ss_xx > 0 else 0.0
    r_squared = 1.0 - (rss / ss_yy) if ss_yy > 0 else 0.0

    return {
        "beta": beta,
        "alpha": alpha,
        "std_error": se_beta,
        "r_squared": r_squared,
        "n": n,
    }


def _resolve_benchmark(
    ctx: ToolContext,
    benchmark: str,
    window_days: int,
) -> Tuple[ReturnSeries, Dict[str, Any]]:
    """Return (benchmark_returns, metadata) for either a synthetic or a ticker."""
    if benchmark.lower().startswith("synthetic_masi"):
        basket = build_basket(ctx.provider, top_n=DEFAULT_BASKET_SIZE)
        synth = build_synthetic_returns(
            ctx.corporate_actions,
            ctx.provider,
            basket,
            window_days=window_days,
        )
        meta: Dict[str, Any] = {
            "benchmark": synth.name,
            "kind": "synthetic_basket",
            "basket_size": len(synth.members),
            "cap_total_mad": sum(m.market_cap_mad for m in synth.members),
            "members": [
                {
                    "symbol": m.symbol,
                    "market_cap_mad": m.market_cap_mad,
                    "weight": round(m.weight, 6),
                }
                for m in synth.members
            ],
        }
        return synth.returns, meta

    series = build_return_series(
        ctx.corporate_actions,
        ctx.provider,
        benchmark,
        window_days=window_days,
    )
    meta = {"benchmark": benchmark, "kind": "ticker"}
    return series, meta


@tool(
    name="get_beta",
    description=(
        "Compute rolling OLS beta of a stock against a benchmark using "
        "log returns from adjusted closes. Benchmark defaults to a "
        "cap-weighted synthetic MASI (top-30 constituents); pass "
        "`benchmark` with a ticker symbol to get peer/sector beta. "
        "Returns beta, standard error, R^2, sample size, and — for the "
        "synthetic benchmark — the basket composition with weights."
    ),
    parameters={
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Stock symbol (e.g., 'ATW')"},
            "window_days": {
                "type": "integer",
                "description": f"Lookback window in trading days. Supported: {list(SUPPORTED_WINDOWS)}. Default 90.",
            },
            "benchmark": {
                "type": "string",
                "description": "Benchmark: omit for 'synthetic_masi_top30', or pass a ticker symbol.",
            },
        },
        "required": ["symbol"],
    },
)
def handle(ctx: ToolContext, args: dict) -> str:
    err = require_ca_service(ctx)
    if err:
        return err

    symbol = args["symbol"]
    window_days = int(args.get("window_days", 90))
    benchmark = args.get("benchmark", "synthetic_masi_top30")

    if window_days not in SUPPORTED_WINDOWS:
        return (
            f"Error: window_days must be one of {list(SUPPORTED_WINDOWS)}, "
            f"got {window_days}"
        )

    stock = build_return_series(
        ctx.corporate_actions,
        ctx.provider,
        symbol,
        window_days=window_days,
    )
    if not stock.dates:
        return f"Error: insufficient adjusted history for {symbol}"

    benchmark_series, benchmark_meta = _resolve_benchmark(ctx, benchmark, window_days)
    if not benchmark_series.dates:
        return f"Error: insufficient benchmark history for {benchmark}"

    aligned = align_series([stock, benchmark_series])
    stock_r = aligned[stock.symbol]
    market_r = aligned[benchmark_series.symbol]

    if len(stock_r) < 10:
        return (
            f"Error: only {len(stock_r)} overlapping observations between "
            f"{symbol} and {benchmark} — window too short or histories do not overlap"
        )

    stats = _ols_beta(stock_r, market_r)

    return json.dumps(
        {
            "symbol": symbol,
            "window_days": window_days,
            "observations": stats["n"],
            "beta": round(stats["beta"], 4),
            "alpha": round(stats["alpha"], 6),
            "std_error": round(stats["std_error"], 4),
            "r_squared": round(stats["r_squared"], 4),
            "confidence_interval_95": {
                "lower": round(stats["beta"] - 1.96 * stats["std_error"], 4),
                "upper": round(stats["beta"] + 1.96 * stats["std_error"], 4),
            },
            "benchmark": benchmark_meta,
        },
        indent=2,
    )
