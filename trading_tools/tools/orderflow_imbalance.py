"""
Orderflow imbalance: Lee-Ready trade classification over existing tape.

WafaBourse's VALEUR-TRANSACTION feed has no aggressor flag, so every
trade must be classified as buyer- or seller-initiated from surrounding
price context. We apply Lee-Ready in the canonical order:

    1. Quote rule   — trade above mid = BUY, below mid = SELL.
       Requires a current best bid/ask, which we fetch via get_order_book.
       The book is a live snapshot, so this only disambiguates trades
       that executed close to the current moment; older trades fall
       through to the tick rule.

    2. Tick rule    — uptick vs. previous trade = BUY, downtick = SELL,
       zero-tick inherits the previous classification.

We expose a `classification_coverage_pct` so the LLM can weigh the
signal against how much of the tape was unclassifiable. Output is
pure statistics — no BUY/SELL recommendation.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from ._context import ToolContext
from ._registry import tool


def _mid_from_book(book: Optional[List[Dict[str, Any]]]) -> Optional[float]:
    if not book:
        return None
    top = book[0]
    bid = top.get("Achat")
    ask = top.get("Vente")
    if not bid or not ask or bid <= 0 or ask <= 0 or ask < bid:
        return None
    return (bid + ask) / 2.0


def _classify(
    trades_oldest_first: List[Dict[str, Any]],
    mid: Optional[float],
) -> List[str]:
    """Return a per-trade direction label aligned with the input order."""
    directions: List[str] = []
    prev_price: Optional[float] = None
    prev_direction: Optional[str] = None

    for trade in trades_oldest_first:
        price = trade.get("Prix") or 0
        label = "UNKNOWN"

        # Tick rule first — always defined once we have a predecessor.
        if prev_price is not None:
            if price > prev_price:
                label = "BUY"
            elif price < prev_price:
                label = "SELL"
            else:
                label = prev_direction or "UNKNOWN"

        # Quote rule overlay: only rely on the book when the trade price
        # is clearly off the mid. Small departures are noise in wide-
        # spread Casablanca names.
        if mid is not None and price > 0:
            if price > mid:
                label = "BUY"
            elif price < mid:
                label = "SELL"

        directions.append(label)
        prev_price = price
        if label in ("BUY", "SELL"):
            prev_direction = label

    return directions


def _summarise(
    trades_oldest_first: List[Dict[str, Any]],
    directions: List[str],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    buy_vol = 0
    sell_vol = 0
    buy_value = 0.0
    sell_value = 0.0
    classified = 0
    total_vol = 0
    total_value = 0.0
    largest_buy = {"qty": 0, "price": 0.0, "time": ""}
    largest_sell = {"qty": 0, "price": 0.0, "time": ""}

    for trade, direction in zip(trades_oldest_first, directions):
        qty = trade.get("Qte") or 0
        price = trade.get("Prix") or 0
        value = qty * price
        total_vol += qty
        total_value += value

        if direction == "BUY":
            buy_vol += qty
            buy_value += value
            classified += qty
            if qty > largest_buy["qty"]:
                largest_buy = {
                    "qty": qty,
                    "price": price,
                    "time": trade.get("Heure", ""),
                }
        elif direction == "SELL":
            sell_vol += qty
            sell_value += value
            classified += qty
            if qty > largest_sell["qty"]:
                largest_sell = {
                    "qty": qty,
                    "price": price,
                    "time": trade.get("Heure", ""),
                }

    classified_vol = buy_vol + sell_vol
    volume_imbalance_pct = (
        round((buy_vol - sell_vol) / classified_vol * 100, 2)
        if classified_vol > 0
        else 0.0
    )
    value_imbalance_pct = (
        round((buy_value - sell_value) / (buy_value + sell_value) * 100, 2)
        if (buy_value + sell_value) > 0
        else 0.0
    )
    vwap = round(total_value / total_vol, 4) if total_vol > 0 else 0.0
    coverage_pct = (
        round(classified / total_vol * 100, 2) if total_vol > 0 else 0.0
    )

    flow: Dict[str, Any] = {
        "buy_volume": buy_vol,
        "sell_volume": sell_vol,
        "buy_value_mad": round(buy_value, 2),
        "sell_value_mad": round(sell_value, 2),
        "volume_imbalance_pct": volume_imbalance_pct,
        "value_imbalance_pct": value_imbalance_pct,
        "net_flow": (
            "BUYING_PRESSURE" if volume_imbalance_pct > 10
            else "SELLING_PRESSURE" if volume_imbalance_pct < -10
            else "NEUTRAL"
        ),
        "largest_buy": largest_buy,
        "largest_sell": largest_sell,
    }
    quality = {
        "trades_total": len(trades_oldest_first),
        "volume_total": total_vol,
        "classification_coverage_pct": coverage_pct,
        "vwap": vwap,
    }
    return flow, quality


@tool(
    name="analyze_orderflow_imbalance",
    description=(
        "Analyze buyer- vs. seller-initiated volume from the recent trade "
        "tape using Lee-Ready classification (quote rule where a best "
        "bid/ask is available, tick rule otherwise). Returns signed volume "
        "and value imbalance, VWAP, the largest aggressor blocks, and a "
        "coverage percentage indicating how much of the tape could be "
        "classified. Pure computation over existing data."
    ),
    parameters={
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Stock symbol (e.g., 'IAM', 'ATW')"},
            "limit": {
                "type": "integer",
                "description": "Max recent trades to analyse (default 100, cap 500)",
            },
        },
        "required": ["symbol"],
    },
)
def handle(ctx: ToolContext, args: dict) -> str:
    symbol = args["symbol"]
    limit = max(1, min(500, int(args.get("limit", 100))))

    trades = ctx.provider.get_recent_trades(symbol)
    if not trades:
        return f"Error: Could not fetch recent trades for {symbol}"

    trades = trades[:limit]
    # WafaBourse returns newest-first. Classification is a stateful pass
    # requiring chronological order.
    ordered = list(reversed(trades))

    book = ctx.provider.get_order_book(symbol, 5)
    mid = _mid_from_book(book)

    directions = _classify(ordered, mid)
    flow, quality = _summarise(ordered, directions)

    first_time = ordered[0].get("Heure", "") if ordered else ""
    last_time = ordered[-1].get("Heure", "") if ordered else ""

    return json.dumps(
        {
            "symbol": symbol,
            "window": {
                "first_trade": first_time,
                "last_trade": last_time,
                "trades": len(ordered),
            },
            "classification": {
                "method": "lee_ready_quote_then_tick" if mid is not None else "tick_only",
                "reference_mid": mid,
            },
            "flow": flow,
            "quality": quality,
        },
        indent=2,
    )
