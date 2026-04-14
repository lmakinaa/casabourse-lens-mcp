import json

from ._context import ToolContext
from ._registry import tool


@tool(
    name="get_volatility_analysis",
    description="Get volatility metrics including Average True Range (ATR), daily range analysis, and volatility classification. Critical for position sizing and stop-loss placement.",
    parameters={
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Stock symbol"},
            "period": {"type": "integer", "description": "ATR period in days (default 14)"},
        },
        "required": ["symbol"],
    },
)
def handle(ctx: ToolContext, args: dict) -> str:
    symbol = args['symbol']
    period = args.get('period', 14)

    history = ctx.provider.get_price_history(symbol)
    details = ctx.provider.get_stock_details(symbol)

    if not history or len(history) < period + 5:
        return f"Error: Insufficient historical data for {symbol}"

    highs = [float(d.get('PlusHaut', d.get('Cours', 0))) for d in history]
    lows = [float(d.get('PlusBas', d.get('Cours', 0))) for d in history]
    closes = [float(d.get('Cours', 0)) for d in history]

    atr = ctx.tech_analysis.calculate_atr(highs, lows, closes, period)
    current_price = closes[-1]

    atr_pct = (atr / current_price * 100) if atr and current_price > 0 else 0

    recent_ranges = []
    for i in range(-period, 0):
        if abs(i) <= len(highs):
            daily_range = highs[i] - lows[i]
            daily_range_pct = (daily_range / closes[i] * 100) if closes[i] > 0 else 0
            recent_ranges.append(daily_range_pct)

    avg_daily_range = sum(recent_ranges) / len(recent_ranges) if recent_ranges else 0
    max_daily_range = max(recent_ranges) if recent_ranges else 0

    if atr_pct > 4:
        volatility_class = "HIGH"
    elif atr_pct > 2:
        volatility_class = "MODERATE"
    else:
        volatility_class = "LOW"

    today_range_pct = 0
    if details:
        today_high = details.get('PlusHaut', 0)
        today_low = details.get('PlusBas', 0)
        today_range = today_high - today_low
        today_range_pct = (today_range / current_price * 100) if current_price > 0 else 0

    return json.dumps({
        "symbol": symbol,
        "current_price": current_price,
        "atr": {
            "value": round(atr, 4) if atr else None,
            "percentage": round(atr_pct, 2),
            "period": period
        },
        "daily_range": {
            "average_pct": round(avg_daily_range, 2),
            "max_pct": round(max_daily_range, 2),
            "today_pct": round(today_range_pct, 2)
        },
        "volatility_classification": volatility_class,
        "suggested_stop_loss_pct": round(atr_pct * 1.5, 2) if atr_pct else None,
        "suggested_position_sizing_note": f"With {volatility_class} volatility, consider {'smaller' if volatility_class == 'HIGH' else 'larger' if volatility_class == 'LOW' else 'standard'} position sizes"
    }, indent=2)
