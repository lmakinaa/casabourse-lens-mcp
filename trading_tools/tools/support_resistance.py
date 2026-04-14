import json

from ._context import ToolContext
from ._registry import tool


@tool(
    name="get_support_resistance",
    description="Calculate key support and resistance levels based on swing highs/lows, period highs/lows, and price action analysis. Essential for identifying entry/exit points.",
    parameters={
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Stock symbol"},
            "lookback": {"type": "integer", "description": "Number of days to analyze (default 30)"},
        },
        "required": ["symbol"],
    },
)
def handle(ctx: ToolContext, args: dict) -> str:
    symbol = args['symbol']
    lookback = args.get('lookback', 30)

    history = ctx.provider.get_price_history(symbol)

    if not history or len(history) < lookback:
        return f"Error: Insufficient historical data for {symbol} (need {lookback} days)"

    highs = [float(d.get('PlusHaut', d.get('Cours', 0))) for d in history]
    lows = [float(d.get('PlusBas', d.get('Cours', 0))) for d in history]
    closes = [float(d.get('Cours', 0)) for d in history]

    levels = ctx.tech_analysis.calculate_support_resistance(highs, lows, closes, lookback)

    if not levels:
        return f"Error: Could not calculate levels for {symbol}"

    current = levels['current_price']

    nearest_resistance = levels['resistance_levels'][0] if levels['resistance_levels'] else None
    nearest_support = levels['support_levels'][0] if levels['support_levels'] else None

    if nearest_resistance and nearest_support:
        range_size = nearest_resistance - nearest_support
        position_in_range = ((current - nearest_support) / range_size * 100) if range_size > 0 else 50
    else:
        position_in_range = 50

    return json.dumps({
        "symbol": symbol,
        "current_price": current,
        "resistance_levels": levels['resistance_levels'],
        "support_levels": levels['support_levels'],
        "period_high": levels['period_high'],
        "period_low": levels['period_low'],
        "key_metrics": {
            "distance_to_resistance_pct": levels['distance_to_resistance_pct'],
            "distance_to_support_pct": levels['distance_to_support_pct'],
            "position_in_range_pct": round(position_in_range, 1)
        },
        "trading_zones": {
            "buy_zone": f"Near {nearest_support:.2f}" if nearest_support else "N/A",
            "sell_zone": f"Near {nearest_resistance:.2f}" if nearest_resistance else "N/A",
            "current_zone": "NEAR_RESISTANCE" if position_in_range > 80 else "NEAR_SUPPORT" if position_in_range < 20 else "MID_RANGE"
        }
    }, indent=2)
