import json

from ._context import ToolContext
from ._registry import tool


@tool(
    name="analyze_volume_profile",
    description="Analyze recent trading volume patterns and compare to historical averages.",
    parameters={
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Stock symbol"}
        },
        "required": ["symbol"],
    },
)
def handle(ctx: ToolContext, args: dict) -> str:
    symbol = args['symbol']
    history = ctx.provider.get_price_history(symbol)
    details = ctx.provider.get_stock_details(symbol)

    if not history or not details:
        return f"Error: Could not analyze volume for {symbol}"

    recent_volumes = [d['Volume'] for d in history[-20:]]
    avg_volume = sum(recent_volumes) / len(recent_volumes)
    current_volume = details['Volume']

    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

    return json.dumps({
        "symbol": symbol,
        "current_volume_mad": current_volume / 1e6,
        "avg_20day_volume_mad": avg_volume / 1e6,
        "volume_ratio": volume_ratio,
        "interpretation": "High" if volume_ratio > 1.5 else "Normal" if volume_ratio > 0.7 else "Low"
    }, indent=2)
