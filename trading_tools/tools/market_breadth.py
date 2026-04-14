import json

from ._context import ToolContext
from ._registry import tool


@tool(
    name="get_market_breadth",
    description="Get market breadth indicators showing overall market health: advance/decline ratio, new highs/lows, percent above moving averages. Use for market timing decisions.",
    parameters={"type": "object", "properties": {}, "required": []},
)
def handle(ctx: ToolContext, args: dict) -> str:
    all_tickers = ctx.provider.get_all_tickers()
    index = ctx.provider.get_market_index()

    if not all_tickers:
        return "Error: Could not fetch market data"

    advances = 0
    declines = 0
    unchanged = 0
    new_highs = 0
    new_lows = 0
    above_avg_volume = 0
    total_volume = 0

    for stock in all_tickers:
        change_pct = stock.get('VariationP', 0)
        volume = stock.get('Volume', 0)
        current = stock.get('Cours', 0)
        year_high = stock.get('PlusHautDAnnee', 0)
        year_low = stock.get('PlusBasDAnnee', 0)

        if change_pct > 0:
            advances += 1
        elif change_pct < 0:
            declines += 1
        else:
            unchanged += 1

        if current and year_high and current >= year_high * 0.99:
            new_highs += 1
        if current and year_low and current <= year_low * 1.01:
            new_lows += 1

        total_volume += volume

    total_stocks = advances + declines + unchanged

    ad_ratio = advances / declines if declines > 0 else float('inf') if advances > 0 else 1

    if ad_ratio > 2:
        sentiment = "STRONGLY_BULLISH"
    elif ad_ratio > 1.2:
        sentiment = "BULLISH"
    elif ad_ratio > 0.8:
        sentiment = "NEUTRAL"
    elif ad_ratio > 0.5:
        sentiment = "BEARISH"
    else:
        sentiment = "STRONGLY_BEARISH"

    return json.dumps({
        "market_index": {
            "value": index.get('Cours') if index else None,
            "change_pct": index.get('VariationP') if index else None
        },
        "breadth_indicators": {
            "advances": advances,
            "declines": declines,
            "unchanged": unchanged,
            "advance_decline_ratio": round(ad_ratio, 2) if ad_ratio != float('inf') else "INF",
            "advance_pct": round(advances / total_stocks * 100, 1) if total_stocks > 0 else 0
        },
        "extreme_movers": {
            "new_52w_highs": new_highs,
            "new_52w_lows": new_lows,
            "net_new_highs": new_highs - new_lows
        },
        "market_sentiment": sentiment,
        "interpretation": f"{'Broad buying' if sentiment.endswith('BULLISH') else 'Broad selling' if sentiment.endswith('BEARISH') else 'Mixed'} pressure with {advances} stocks up vs {declines} down"
    }, indent=2)
